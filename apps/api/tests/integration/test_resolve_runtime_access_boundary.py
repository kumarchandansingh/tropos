from __future__ import annotations

from pathlib import Path

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import (
    JudgedSufficiency,
)
from tropos.capabilities.resolve.application.generate_grounded_answer import (
    GeneratedGroundedAnswer,
)
from tropos.capabilities.resolve.application.resolve_question import ResolveQuestion
from tropos.capabilities.resolve.domain.evidence_sufficiency import EvidenceSet
from tropos.capabilities.resolve.domain.runtime import ResolveOutcome, RuntimeRequest
from tropos.cli import ingest_local_file
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.observability.trace import InMemoryTraceSink
from tropos.core.application.retrieval.models import RetrievalAccessContext


class MustNotJudge:
    def judge(self, evidence_set: EvidenceSet) -> JudgedSufficiency:
        raise AssertionError("unauthorized evidence must not reach sufficiency")


class MustNotGenerate:
    def generate(self, evidence_set: EvidenceSet) -> GeneratedGroundedAnswer:
        raise AssertionError("unauthorized evidence must not reach generation")


def test_restricted_evidence_is_excluded_before_model_stages(tmp_path: Path) -> None:
    source = tmp_path / "restricted-runbook.txt"
    source.write_text(
        "Certificate rotation recovery requires a privileged restart.",
        encoding="utf-8",
    )
    database = tmp_path / "tropos.db"
    ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
        groups=("support-l3",),
    )

    sink = InMemoryTraceSink()
    runtime = ResolveQuestion(
        retriever=SQLiteFtsKnowledgeRetriever(database),
        sufficiency_judge=MustNotJudge()
        answer_generator=MustNotGenerate(),
        trace_sink=sink,
    )
    request = RuntimeRequest(
        request_id="request-denied",
        query="certificate rotation recovery",
        access=RetrievalAccessContext(
            tenant_id="tenant-a",
            groups=("support-l2",),
        ),
    )

    result = runtime.execute(request)

    assert result.outcome is ResolveOutcome.RETRIEVAL_ABSTAINED
    assert result.abstention_reason == "no_eligible_evidence"
    assert sink.traces[0].spans[1].attributes["result_count"] == 0
