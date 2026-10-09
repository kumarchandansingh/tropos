"""Training application service tests using Tropos retrieval contracts."""

from hashlib import sha256

import pytest

from tropos.capabilities.training.generate_procedure import GenerateProcedure, GenerateProcedureRequest
from tropos.capabilities.training.procedure import EvidenceExcerpt, ProcedureDraft
from tropos.core.application.retrieval.models import RetrievedKnowledgeChunk
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk, text_fingerprint


class FakeRetriever:
    strategy_version = "fake-retriever-v1"

    def __init__(self, results: tuple[RetrievedKnowledgeChunk, ...]) -> None:
        self.results = results
        self.request = None

    def search(self, request):
        self.request = request
        return self.results


class RecordingExtractor:
    def __init__(self) -> None:
        self.evidence: tuple[EvidenceExcerpt, ...] | None = None

    def extract(self, evidence: tuple[EvidenceExcerpt, ...]) -> ProcedureDraft:
        self.evidence = evidence
        return ProcedureDraft("Draft", (), (), ())


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _retrieved(text: str = "Submit an eligible requisition") -> RetrievedKnowledgeChunk:
    access = AccessPolicy("tenant-a", AccessScope.TENANT)
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        knowledge_id="knowledge-1",
        source_system="local-file",
        source_record_id="uat.xlsx",
        source_version="2",
        document_title="UAT Cases",
        sequence_number=0,
        text=text,
        start_offset=20,
        end_offset=20 + len(text),
        content_fingerprint=text_fingerprint(text),
        ingestion_fingerprint=_digest("ingestion"),
        normalized_content_fingerprint=_digest("normalized"),
        normalization_strategy_version="normalize-v1",
        access_policy=access,
        strategy_version="chunk-v1",
    )
    return RetrievedKnowledgeChunk(chunk, rank=1, score=1.5, strategy_version="fts-v1")


def test_retrieves_authorized_evidence_and_preserves_provenance() -> None:
    retriever = FakeRetriever((_retrieved(),))
    extractor = RecordingExtractor()

    result = GenerateProcedure(retriever, extractor).execute(
        GenerateProcedureRequest(
            query="How do I submit a requisition?",
            tenant_id="tenant-a",
            groups=("buyers",),
            retrieval_limit=4,
        )
    )

    assert result.title == "Draft"
    assert retriever.request.access.tenant_id == "tenant-a"
    assert retriever.request.access.groups == ("buyers",)
    assert retriever.request.limit == 4
    assert extractor.evidence is not None
    assert extractor.evidence[0].source_id == "chunk-1"
    assert extractor.evidence[0].locator == "local-file:uat.xlsx@v2#chars=20-50"
    assert extractor.evidence[0].text == "Submit an eligible requisition"


def test_does_not_call_extractor_without_authorized_evidence() -> None:
    retriever = FakeRetriever(())
    extractor = RecordingExtractor()

    with pytest.raises(LookupError, match="No authorized evidence"):
        GenerateProcedure(retriever, extractor).execute(
            GenerateProcedureRequest(query="Submit requisition", tenant_id="tenant-a")
        )

    assert extractor.evidence is None
