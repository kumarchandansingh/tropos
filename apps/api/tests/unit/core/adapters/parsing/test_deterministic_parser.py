from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import pytest

from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.application.ingestion.normalization import StructuralBlockKind, TextFormat
from tropos.core.application.ingestion.parsing import KnowledgeParseError, UnsupportedContentTypeError
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.domain.access import AccessPolicy, AccessScope


def _raw(payload: bytes, *, content_type: str, record_id: str = "kb-42") -> RawKnowledgeRecord:
    return RawKnowledgeRecord(
        source_system="test",
        source_record_id=record_id,
        source_version="1",
        content_type=content_type,
        payload=payload,
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
        captured_at=datetime(2026, 9, 26, tzinfo=UTC),
    )


def _docx_payload() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Password Reset</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>Verify the caller before resetting credentials.</w:t></w:r></w:p>
    <w:p>
      <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr>
      <w:r><w:t>Verify identity</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Role</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Approval</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""
    numbering_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>
"""
    core_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Support Runbook</dc:title>
</cp:coreProperties>
"""
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/numbering.xml", numbering_xml)
        archive.writestr("docProps/core.xml", core_xml)
    return output.getvalue()


def test_markdown_parser_preserves_explicit_structure() -> None:
    parser = DeterministicKnowledgeParser()
    source = parser.parse(
        _raw(
            b"# Password Reset\n\nUse the runbook.\n\n- Verify identity\n- Reset password",
            content_type="text/markdown; charset=utf-8",
        )
    )

    assert source.title == "Password Reset"
    assert source.text_format is TextFormat.MARKDOWN
    assert "- Verify identity" in source.text

    normalized = DeterministicKnowledgeNormalizer().normalize(source)
    assert [block.kind for block in normalized.blocks] == [
        StructuralBlockKind.HEADING,
        StructuralBlockKind.PARAGRAPH,
        StructuralBlockKind.UNORDERED_LIST_ITEM,
        StructuralBlockKind.UNORDERED_LIST_ITEM,
    ]


def test_html_parser_removes_executable_noise_and_preserves_blocks() -> None:
    parser = DeterministicKnowledgeParser()
    html = b"""
<html><head><title>Account Recovery</title><style>.x{display:none}</style></head>
<body><h1>Reset Procedure</h1><p>Verify <strong>identity</strong>.</p>
<ol><li>Open the account</li><li>Force reauthentication</li></ol>
<script>alert('ignore')</script></body></html>
"""

    source = parser.parse(_raw(html, content_type="text/html"))

    assert source.title == "Account Recovery"
    assert source.text_format is TextFormat.MARKDOWN
    assert "# Reset Procedure" in source.text
    assert "1. Open the account" in source.text
    assert "alert" not in source.text
    assert "display:none" not in source.text


def test_docx_parser_preserves_heading_list_table_text_and_core_title() -> None:
    parser = DeterministicKnowledgeParser()
    source = parser.parse(
        _raw(
            _docx_payload(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
    )

    assert source.title == "Support Runbook"
    assert source.text_format is TextFormat.MARKDOWN
    assert "# Password Reset" in source.text
    assert "1. Verify identity" in source.text
    assert "Role | Approval" in source.text


def test_plain_text_uses_source_identity_as_title() -> None:
    source = DeterministicKnowledgeParser().parse(
        _raw(b"Simple article text", content_type="text/plain", record_id="article-7")
    )

    assert source.title == "article-7"
    assert source.text == "Simple article text"
    assert source.text_format is TextFormat.PLAIN


def test_unsupported_content_type_fails_closed() -> None:
    with pytest.raises(UnsupportedContentTypeError, match="application/pdf"):
        DeterministicKnowledgeParser().parse(
            _raw(b"%PDF-1.7", content_type="application/pdf")
        )


def test_invalid_utf8_is_rejected_instead_of_silently_replaced() -> None:
    with pytest.raises(KnowledgeParseError, match="valid UTF-8"):
        DeterministicKnowledgeParser().parse(
            _raw(b"\xff\xfe", content_type="text/plain")
        )


def test_invalid_docx_package_is_rejected() -> None:
    with pytest.raises(KnowledgeParseError, match="valid ZIP"):
        DeterministicKnowledgeParser().parse(
            _raw(
                b"not-a-zip",
                content_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
            )
        )
