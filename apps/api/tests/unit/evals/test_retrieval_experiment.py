from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.catalogue import Catalogue
from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalOrigin,
    EvalRunProvenance,
    EvalScope,
    EvalSplit,
    EvalSubject,
)
from tropos.evals.experiments import ExperimentRunner
from tropos.evals.retrieval_experiment import (
    RETRIEVAL_HARD_INVARIANTS,
    RetrievalExperimentExecutor,
    catalogue_retrieval_dataset,
    hard_invariant_failures,
)
from tropos.evals.run_io import eval_run_from_dict, eval_run_to_dict


def _chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="chunk-1",
        knowledge_id="kb-1",
        source_system="fixture",
        source_record_id="kb-1.md",
        source_version="1",
        document_title="Reset a locked account",
        sequence_number=1,
        text="Unlock the account after verifying the identity.",
        start_offset=0,
        end_offset=48,
        content_fingerprint="content",
        ingestion_fingerprint="ingestion",
        normalized_content_fingerprint="normalized",
        normalization_strategy_version="norm-v1",
        access_policy=AccessPolicy("tenant-a", AccessScope.TENANT),
        strategy_version="chunk-v1",
    )


class _Retriever:
    strategy_version = "fixture-retriever-v1"

    def __init__(self, results: tuple[RetrievedKnowledgeChunk, ...]) -> None:
        self.results = results

    def search(
        self,
        request: KnowledgeSearchRequest,
    ) -> tuple[RetrievedKnowledgeChunk, ...]:
        return self.results


def _case(*, relevant: tuple[str, ...] = ("kb-1",)) -> EvalCase:
    return EvalCase(
        case_id="case-1",
        purpose="Find the expected current authorized knowledge.",
        scope=EvalScope.COMPONENT,
        approval=EvalApproval.APPROVED,
        origin=EvalOrigin.SYNTHETIC,
        inputs={
            "query": "account locked",
            "tenant_id": "tenant-a",
            "groups": [],
            "max_rank": 5,
        },
        expected={"relevant_knowledge_ids": list(relevant)},
        tags=("identity",),
    )


def _dataset(case: EvalCase) -> EvalDataset:
    return EvalDataset(
        dataset_id="retrieval-fixture",
        version="v1",
        capability="retrieval",
        split=EvalSplit.DEVELOPMENT,
        cases=(case,),
    )


def test_generic_retrieval_executor_emits_shared_invariants_and_metrics() -> None:
    chunk = _chunk()
    retriever = _Retriever(
        (
            RetrievedKnowledgeChunk(
                chunk=chunk,
                rank=1,
                score=2.5,
                strategy_version=_Retriever.strategy_version,
            ),
        )
    )
    observation = RetrievalExperimentExecutor(
        retriever=retriever,
        current_chunks={chunk.chunk_id: chunk},
    ).execute(_case())

    assert observation.state.value == "passed"
    by_metric = {score.metric: score for score in observation.scores}
    assert all(by_metric[metric].passed is True for metric in RETRIEVAL_HARD_INVARIANTS)
    assert by_metric["expected_evidence"].passed is True
    assert by_metric["recall_at_1"].value == 1.0
    assert by_metric["reciprocal_rank"].value == 1.0


def test_quality_miss_does_not_become_a_hard_invariant_failure() -> None:
    chunk = _chunk()
    retriever = _Retriever(
        (
            RetrievedKnowledgeChunk(
                chunk=chunk,
                rank=1,
                score=1.0,
                strategy_version=_Retriever.strategy_version,
            ),
        )
    )
    no_answer_case = _case(relevant=())
    observation = RetrievalExperimentExecutor(
        retriever=retriever,
        current_chunks={chunk.chunk_id: chunk},
    ).execute(no_answer_case)

    run = ExperimentRunner(
        run_id_factory=lambda: "run-1",
        clock=iter(
            (
                datetime(2026, 10, 11, 0, 0, tzinfo=UTC),
                datetime(2026, 10, 11, 0, 0, 1, tzinfo=UTC),
            )
        ).__next__,
    ).run(
        dataset=_dataset(no_answer_case),
        subject=EvalSubject(
            subject_id="retrieval",
            version=_Retriever.strategy_version,
            configuration={},
        ),
        provenance=EvalRunProvenance(
            code_revision="abc",
            dependency_digest="lock",
            runtime={},
        ),
        executor=RetrievalExperimentExecutor(
            retriever=retriever,
            current_chunks={chunk.chunk_id: chunk},
        ),
    )

    assert observation.state.value == "failed"
    assert hard_invariant_failures(run) == ()
    no_answer = next(score for score in observation.scores if score.metric == "no_answer_accuracy")
    assert no_answer.value == 0.0


def test_integrity_failure_blocks_metrics_and_is_a_hard_invariant() -> None:
    chunk = _chunk()
    forged = replace(chunk, document_title="Forged title")
    retriever = _Retriever(
        (
            RetrievedKnowledgeChunk(
                chunk=forged,
                rank=1,
                score=1.0,
                strategy_version=_Retriever.strategy_version,
            ),
        )
    )
    case = _case()
    run = ExperimentRunner(
        run_id_factory=lambda: "run-integrity",
    ).run(
        dataset=_dataset(case),
        subject=EvalSubject(
            subject_id="retrieval",
            version=_Retriever.strategy_version,
            configuration={},
        ),
        provenance=EvalRunProvenance(
            code_revision="abc",
            dependency_digest="lock",
            runtime={},
        ),
        executor=RetrievalExperimentExecutor(
            retriever=retriever,
            current_chunks={chunk.chunk_id: chunk},
        ),
    )

    assert ("case-1", "evidence_integrity") in hard_invariant_failures(run)
    assert not any(score.metric == "recall_at_5" for score in run.observations[0].scores)


def test_generic_eval_run_json_round_trip_preserves_scores_and_provenance() -> None:
    chunk = _chunk()
    retriever = _Retriever(
        (
            RetrievedKnowledgeChunk(
                chunk=chunk,
                rank=1,
                score=1.0,
                strategy_version=_Retriever.strategy_version,
            ),
        )
    )
    case = _case()
    run = ExperimentRunner(run_id_factory=lambda: "round-trip").run(
        dataset=_dataset(case),
        subject=EvalSubject(
            subject_id="retrieval",
            version=_Retriever.strategy_version,
            configuration={"limit": 5},
        ),
        provenance=EvalRunProvenance(
            code_revision="abc",
            dependency_digest="lock",
            runtime={"python_version": "3.14"},
        ),
        executor=RetrievalExperimentExecutor(
            retriever=retriever,
            current_chunks={chunk.chunk_id: chunk},
        ),
    )

    assert eval_run_from_dict(eval_run_to_dict(run)) == run


def test_catalogue_projection_binds_generic_dataset_to_full_catalogue_snapshot() -> None:
    path = Path(__file__).parents[3] / "evals" / "retrieval" / "catalogue_v2.json"
    catalogue = Catalogue.load(path)
    projected = catalogue_retrieval_dataset(catalogue)

    assert len(projected.cases) == 17
    assert all(
        case.inputs["catalogue_fingerprint"] == catalogue.fingerprint for case in projected.cases
    )
    assert all(
        case.inputs["corpus_fingerprint"] == catalogue.corpus_fingerprint
        for case in projected.cases
    )
