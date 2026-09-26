from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from tropos.core.application.ingestion.normalization import ExtractedKnowledgeText, TextFormat
from tropos.core.application.ingestion.parsing import (
    KnowledgeParseError,
    UnsupportedContentTypeError,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord

_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_MARKDOWN_CONTENT_TYPES = frozenset({"text/markdown", "text/x-markdown"})
_PLAIN_CONTENT_TYPES = frozenset({"text/plain"})
_MAX_DOCX_PART_BYTES = 8_000_000

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_NS = {"w": _W_NS, "dc": _DC_NS}

_HEADING_STYLE = re.compile(r"^heading\s*([1-6])$", re.IGNORECASE)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _decode_utf8(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise KnowledgeParseError("text payload must be valid UTF-8") from exc


def _collapse_inline(value: str) -> str:
    return " ".join(value.split())


def _markdown_title(text: str, fallback: str) -> str:
    first_heading: str | None = None
    for line in text.splitlines():
        match = _MARKDOWN_HEADING.match(line)
        if match is None:
            continue
        title = _collapse_inline(match.group(2))
        if len(match.group(1)) == 1:
            return title
        if first_heading is None:
            first_heading = title
    return first_heading or fallback


class _HTMLToMarkdown(HTMLParser):
    _BOUNDARY_TAGS = frozenset(
        {"article", "aside", "div", "footer", "header", "main", "nav", "section"}
    )
    _SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.title_parts: list[str] = []
        self.first_heading: str | None = None
        self._buffer: list[str] = []
        self._active_block: str | None = None
        self._heading_level: int | None = None
        self._list_stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    @property
    def document_title(self) -> str | None:
        title = _collapse_inline(" ".join(self.title_parts))
        return title or self.first_heading

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in {"ul", "ol"}:
            self._flush_generic()
            self._list_stack.append(tag)
            return
        if tag in self._BOUNDARY_TAGS:
            self._flush_generic()
            return
        if tag == "br":
            self._buffer.append("\n")
            return
        if tag == "p" or tag == "li" or (len(tag) == 2 and tag[0] == "h" and tag[1].isdigit()):
            self._start_block(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            return
        if self._active_block == tag:
            self._finish_block()
            return
        if tag in {"ul", "ol"}:
            self._flush_generic()
            if self._list_stack:
                self._list_stack.pop()
            return
        if tag in self._BOUNDARY_TAGS:
            self._flush_generic()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        self._buffer.append(data)

    def close(self) -> None:
        super().close()
        if self._active_block is not None:
            self._finish_block()
        self._flush_generic()

    def _start_block(self, tag: str) -> None:
        if self._active_block is not None:
            self._finish_block()
        else:
            self._flush_generic()
        self._active_block = tag
        self._heading_level = int(tag[1]) if tag.startswith("h") and len(tag) == 2 else None

    def _finish_block(self) -> None:
        text = _collapse_inline(" ".join(self._buffer))
        self._buffer.clear()
        tag = self._active_block
        level = self._heading_level
        self._active_block = None
        self._heading_level = None
        if not text or tag is None:
            return
        if level is not None:
            self.blocks.append(f"{'#' * level} {text}")
            if self.first_heading is None:
                self.first_heading = text
            return
        if tag == "li":
            marker = "1." if self._list_stack and self._list_stack[-1] == "ol" else "-"
            self.blocks.append(f"{marker} {text}")
            return
        self.blocks.append(text)

    def _flush_generic(self) -> None:
        if self._active_block is not None:
            return
        text = _collapse_inline(" ".join(self._buffer))
        self._buffer.clear()
        if text:
            self.blocks.append(text)


def _qname(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _read_zip_part(archive: ZipFile, name: str, *, required: bool) -> bytes | None:
    try:
        info = archive.getinfo(name)
    except KeyError:
        if required:
            raise KnowledgeParseError(f"DOCX is missing required part: {name}") from None
        return None
    if info.file_size > _MAX_DOCX_PART_BYTES:
        raise KnowledgeParseError(f"DOCX part exceeds safety limit: {name}")
    return archive.read(info)


def _xml_root(payload: bytes, *, part_name: str) -> ET.Element:
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise KnowledgeParseError(f"DOCX part is not valid XML: {part_name}") from exc


def _docx_paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag == _qname(_W_NS, "t") and node.text:
            pieces.append(node.text)
        elif node.tag == _qname(_W_NS, "tab"):
            pieces.append("\t")
        elif node.tag == _qname(_W_NS, "br"):
            pieces.append("\n")
    return _collapse_inline("".join(pieces))


def _docx_numbering_formats(archive: ZipFile) -> dict[str, str]:
    raw = _read_zip_part(archive, "word/numbering.xml", required=False)
    if raw is None:
        return {}
    root = _xml_root(raw, part_name="word/numbering.xml")
    abstract_formats: dict[str, str] = {}
    for abstract in root.findall("w:abstractNum", _NS):
        abstract_id = abstract.get(_qname(_W_NS, "abstractNumId"))
        level = abstract.find("w:lvl", _NS)
        number_format = level.find("w:numFmt", _NS) if level is not None else None
        value = number_format.get(_qname(_W_NS, "val")) if number_format is not None else None
        if abstract_id is not None and value is not None:
            abstract_formats[abstract_id] = value

    formats: dict[str, str] = {}
    for number in root.findall("w:num", _NS):
        num_id = number.get(_qname(_W_NS, "numId"))
        abstract_ref = number.find("w:abstractNumId", _NS)
        abstract_id = abstract_ref.get(_qname(_W_NS, "val")) if abstract_ref is not None else None
        if num_id is not None and abstract_id in abstract_formats:
            formats[num_id] = abstract_formats[abstract_id]
    return formats


def _docx_paragraph_markdown(paragraph: ET.Element, numbering: dict[str, str]) -> str | None:
    text = _docx_paragraph_text(paragraph)
    if not text:
        return None
    properties = paragraph.find("w:pPr", _NS)
    if properties is None:
        return text

    style = properties.find("w:pStyle", _NS)
    style_id = style.get(_qname(_W_NS, "val")) if style is not None else None
    if style_id:
        match = _HEADING_STYLE.match(style_id.replace("_", " "))
        if match is not None:
            return f"{'#' * int(match.group(1))} {text}"

    numbering_properties = properties.find("w:numPr", _NS)
    if numbering_properties is not None:
        num_id_node = numbering_properties.find("w:numId", _NS)
        num_id = num_id_node.get(_qname(_W_NS, "val")) if num_id_node is not None else None
        number_format = numbering.get(num_id or "", "bullet")
        marker = "-" if number_format == "bullet" else "1."
        return f"{marker} {text}"
    return text


def _docx_table_markdown(table: ET.Element) -> list[str]:
    rows: list[str] = []
    for row in table.findall("w:tr", _NS):
        cells: list[str] = []
        for cell in row.findall("w:tc", _NS):
            text = _collapse_inline(
                " ".join(filter(None, (_docx_paragraph_text(p) for p in cell.findall("w:p", _NS))))
            )
            cells.append(text)
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def _docx_title(archive: ZipFile, blocks: list[str], fallback: str) -> str:
    core = _read_zip_part(archive, "docProps/core.xml", required=False)
    if core is not None:
        root = _xml_root(core, part_name="docProps/core.xml")
        title = root.find("dc:title", _NS)
        if title is not None and title.text and title.text.strip():
            return _collapse_inline(title.text)
    for block in blocks:
        match = _MARKDOWN_HEADING.match(block)
        if match is not None:
            return _collapse_inline(match.group(2))
    return fallback


class DeterministicKnowledgeParser:
    """Route supported source formats through deterministic, non-LLM parsing."""

    def parse(
        self,
        raw_record: RawKnowledgeRecord,
        *,
        source_uri: str | None = None,
        source_updated_at: datetime | None = None,
    ) -> ExtractedKnowledgeText:
        content_type = _content_type(raw_record.content_type)
        if content_type in _PLAIN_CONTENT_TYPES:
            return self._parse_plain(raw_record, source_uri, source_updated_at)
        if content_type in _MARKDOWN_CONTENT_TYPES:
            return self._parse_markdown(raw_record, source_uri, source_updated_at)
        if content_type in _HTML_CONTENT_TYPES:
            return self._parse_html(raw_record, source_uri, source_updated_at)
        if content_type == _DOCX_CONTENT_TYPE:
            return self._parse_docx(raw_record, source_uri, source_updated_at)
        raise UnsupportedContentTypeError(f"unsupported content type: {content_type}")

    def _parse_plain(
        self,
        raw_record: RawKnowledgeRecord,
        source_uri: str | None,
        source_updated_at: datetime | None,
    ) -> ExtractedKnowledgeText:
        return ExtractedKnowledgeText(
            raw_record=raw_record,
            title=raw_record.source_record_id,
            text=_decode_utf8(raw_record.payload),
            text_format=TextFormat.PLAIN,
            source_uri=source_uri,
            source_updated_at=source_updated_at,
        )

    def _parse_markdown(
        self,
        raw_record: RawKnowledgeRecord,
        source_uri: str | None,
        source_updated_at: datetime | None,
    ) -> ExtractedKnowledgeText:
        text = _decode_utf8(raw_record.payload)
        return ExtractedKnowledgeText(
            raw_record=raw_record,
            title=_markdown_title(text, raw_record.source_record_id),
            text=text,
            text_format=TextFormat.MARKDOWN,
            source_uri=source_uri,
            source_updated_at=source_updated_at,
        )

    def _parse_html(
        self,
        raw_record: RawKnowledgeRecord,
        source_uri: str | None,
        source_updated_at: datetime | None,
    ) -> ExtractedKnowledgeText:
        parser = _HTMLToMarkdown()
        try:
            parser.feed(_decode_utf8(raw_record.payload))
            parser.close()
        except (ValueError, AssertionError) as exc:
            raise KnowledgeParseError("HTML payload could not be parsed") from exc
        text = "\n\n".join(parser.blocks).strip()
        if not text:
            raise KnowledgeParseError("HTML parsing produced no usable text")
        return ExtractedKnowledgeText(
            raw_record=raw_record,
            title=parser.document_title or raw_record.source_record_id,
            text=text,
            text_format=TextFormat.MARKDOWN,
            source_uri=source_uri,
            source_updated_at=source_updated_at,
        )

    def _parse_docx(
        self,
        raw_record: RawKnowledgeRecord,
        source_uri: str | None,
        source_updated_at: datetime | None,
    ) -> ExtractedKnowledgeText:
        try:
            with ZipFile(BytesIO(raw_record.payload)) as archive:
                document_bytes = _read_zip_part(archive, "word/document.xml", required=True)
                assert document_bytes is not None
                root = _xml_root(document_bytes, part_name="word/document.xml")
                body = root.find("w:body", _NS)
                if body is None:
                    raise KnowledgeParseError("DOCX document has no body")
                numbering = _docx_numbering_formats(archive)
                blocks: list[str] = []
                for child in body:
                    if child.tag == _qname(_W_NS, "p"):
                        block = _docx_paragraph_markdown(child, numbering)
                        if block:
                            blocks.append(block)
                    elif child.tag == _qname(_W_NS, "tbl"):
                        blocks.extend(_docx_table_markdown(child))
                text = "\n\n".join(blocks).strip()
                if not text:
                    raise KnowledgeParseError("DOCX parsing produced no usable text")
                title = _docx_title(archive, blocks, raw_record.source_record_id)
        except BadZipFile as exc:
            raise KnowledgeParseError("DOCX payload is not a valid ZIP package") from exc

        return ExtractedKnowledgeText(
            raw_record=raw_record,
            title=title,
            text=text,
            text_format=TextFormat.MARKDOWN,
            source_uri=source_uri,
            source_updated_at=source_updated_at,
        )
