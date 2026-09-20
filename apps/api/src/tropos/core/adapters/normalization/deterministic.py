import json
import re
import unicodedata
from hashlib import sha256

from tropos.core.application.ingestion.normalization import (
    ExtractedKnowledgeText,
    NormalizedKnowledge,
    StructuralBlock,
    StructuralBlockKind,
    TextFormat,
)

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_UNORDERED_LIST = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_ORDERED_LIST = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")


class DeterministicKnowledgeNormalizer:
    """Normalize text and structure without semantic rewriting or model calls."""

    def __init__(self, *, strategy_version: str = "canonical-text-v1") -> None:
        if not strategy_version.strip():
            raise ValueError("strategy_version must not be blank")
        self._strategy_version = strategy_version

    def normalize(self, source: ExtractedKnowledgeText) -> NormalizedKnowledge:
        title = self._normalize_inline(source.title)
        normalized_source_text = self._normalize_text(source.text)
        blocks = self._extract_blocks(
            text=normalized_source_text,
            text_format=source.text_format,
        )
        canonical_text = self._render_canonical_text(blocks)

        canonical_payload = {
            "blocks": [
                {
                    "kind": block.kind.value,
                    "level": block.level,
                    "text": block.text,
                }
                for block in blocks
            ],
            "title": title,
        }
        canonical_serialization = json.dumps(
            canonical_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        content_fingerprint = sha256(canonical_serialization.encode("utf-8")).hexdigest()

        return NormalizedKnowledge(
            source=source,
            title=title,
            normalized_source_text=normalized_source_text,
            canonical_text=canonical_text,
            blocks=blocks,
            canonical_serialization=canonical_serialization,
            content_fingerprint=content_fingerprint,
            strategy_version=self._strategy_version,
        )

    def _normalize_inline(self, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value.replace("\ufeff", ""))
        return " ".join(normalized.split())

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value.replace("\ufeff", ""))
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

        cleaned_lines = [line.rstrip(" \t") for line in normalized.split("\n")]

        compacted: list[str] = []
        previous_blank = False
        for line in cleaned_lines:
            is_blank = not line.strip()
            if is_blank and previous_blank:
                continue
            compacted.append("" if is_blank else line)
            previous_blank = is_blank

        text = "\n".join(compacted).strip()
        if not text:
            raise ValueError("normalization produced empty text")
        return text

    def _render_canonical_text(
        self,
        blocks: tuple[StructuralBlock, ...],
    ) -> str:
        rendered: list[str] = []
        for block in blocks:
            if block.kind is StructuralBlockKind.HEADING:
                assert block.level is not None
                rendered.append(f"{'#' * block.level} {block.text}")
            elif block.kind is StructuralBlockKind.UNORDERED_LIST_ITEM:
                rendered.append(f"- {block.text}")
            elif block.kind is StructuralBlockKind.ORDERED_LIST_ITEM:
                rendered.append(f"1. {block.text}")
            else:
                rendered.append(block.text)
        return "\n\n".join(rendered)

    def _extract_blocks(
        self,
        *,
        text: str,
        text_format: TextFormat,
    ) -> tuple[StructuralBlock, ...]:
        blocks: list[StructuralBlock] = []
        paragraph_lines: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph_lines:
                return
            paragraph = self._normalize_inline(" ".join(paragraph_lines))
            blocks.append(
                StructuralBlock(
                    kind=StructuralBlockKind.PARAGRAPH,
                    text=paragraph,
                )
            )
            paragraph_lines.clear()

        for line in text.split("\n"):
            if not line.strip():
                flush_paragraph()
                continue

            heading = _MARKDOWN_HEADING.match(line) if text_format is TextFormat.MARKDOWN else None
            if heading is not None:
                flush_paragraph()
                blocks.append(
                    StructuralBlock(
                        kind=StructuralBlockKind.HEADING,
                        text=self._normalize_inline(heading.group(2)),
                        level=len(heading.group(1)),
                    )
                )
                continue

            unordered = _UNORDERED_LIST.match(line)
            ordered = _ORDERED_LIST.match(line)
            list_match = unordered or ordered
            if list_match is not None:
                flush_paragraph()
                kind = (
                    StructuralBlockKind.UNORDERED_LIST_ITEM
                    if unordered is not None
                    else StructuralBlockKind.ORDERED_LIST_ITEM
                )
                blocks.append(
                    StructuralBlock(
                        kind=kind,
                        text=self._normalize_inline(list_match.group(1)),
                    )
                )
                continue

            paragraph_lines.append(line)

        flush_paragraph()

        if not blocks:
            raise ValueError("structural extraction produced no blocks")
        return tuple(blocks)
