"""Run BM25, dense MPNet, and hybrid RRF through one generic EvalRun path."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

import sentence_transformers

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.embeddings.materialize import MaterializeEmbeddings
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.evals.contracts import (
    EvalRun,
    EvalScore,
    EvalSplit,
    EvalSubject,
    JsonObject,
)
from tropos.evals.enterprise_support import load_enterprise_support_benchmark
from tropos.evals.experiment_store import SQLiteExperimentStore
from tropos.evals.experiments import ExperimentRunner, compare_runs
from tropos.evals.fixtures import load_current_chunks
from tropos.evals.provenance import build_eval_provenance
from tropos.evals.retrieval_experiment import (
    RETRIEVAL_DECISION_METRICS,
    RETRIEVAL_EVALUATOR_VERSION,
    RetrievalExperimentExecutor,
    hard_invariant_failures,
)
from tropos.evals.run_io import eval_run_to_dict
from tropos.evals.sentence_transformer_provider import (
    MODEL_IDENTIFIER,
    MODEL_REVISION,
    SentenceTransformerEmbeddingProvider,
)


def _orchestrator(store: SQLiteIngestionStore) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=2000),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def _metric_scores(run: EvalRun, metric: str) -> tuple[EvalScore, ...]:
    return tuple(
        score
        for observation in run.observations
        for score in observation.scores
        if score.metric == metric
    )


def _summary(run: EvalRun) -> JsonObject:
    metrics: JsonObject = {}
    for metric in RETRIEVAL_DECISION_METRICS:
        values = tuple(
            float(score.value)
            for score in _metric_scores(run, metric)
            if not isinstance(score.value, bool)
        )
        metrics[metric] = fmean(values) if values else None
        metrics[f"{metric}_case_count"] = len(values)

    return {
        "subject_version": run.subject.version,
        "case_count": len(run.observations),
        "passed_case_count": sum(
            observation.state.value == "passed" for observation in run.observations
        ),
        "failed_case_count": sum(
            observation.state.value == "failed" for observation in run.observations
        ),
        "error_case_count": sum(
            observation.state.value == "error" for observation in run.observations
        ),
        "hard_invariant_failures": [
            {"case_id": case_id, "metric": metric}
            for case_id, metric in hard_invariant_failures(run)
        ],
        "metrics": metrics,
    }


def _comparison(baseline: EvalRun, candidate: EvalRun) -> JsonObject:
    comparison = compare_runs(baseline, candidate)
    return {
        "baseline_run_id": baseline.run_id,
        "candidate_run_id": candidate.run_id,
        "regressed_cases": [item.case_id for item in comparison.regressions],
        "improved_cases": [item.case_id for item in comparison.improvements],
        "metric_comparisons": [
            {
                "metric": item.metric,
                "pair_count": item.pair_count,
                "baseline_mean": item.baseline_mean,
                "candidate_mean": item.candidate_mean,
                "mean_delta": item.mean_delta,
                "confidence_low": item.confidence_low,
                "confidence_high": item.confidence_high,
            }
            for item in comparison.metric_comparisons
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate BM25, dense MPNet and hybrid RRF through the same "
            "enterprise-support EvalRun contract"
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=(
            Path(__file__).parents[1] / "evals" / "resolve" / "enterprise_support_benchmark_v1.json"
        ),
    )
    parser.add_argument(
        "--split",
        choices=tuple(split.value for split in EvalSplit),
        default=EvalSplit.DEVELOPMENT.value,
    )
    parser.add_argument("--lockfile", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    arguments = parser.parse_args()

    benchmark = load_enterprise_support_benchmark(arguments.dataset)
    split = EvalSplit(arguments.split)
    dataset = benchmark.retrieval_dataset(split)

    repository_root = Path(__file__).parents[2]
    sink = None if arguments.database is None else SQLiteExperimentStore(arguments.database)

    with tempfile.TemporaryDirectory(prefix="tropos-enterprise-retrieval-") as temp:
        database = Path(temp) / "tropos.db"
        store = SQLiteIngestionStore(database)
        ingestion = _orchestrator(store)

        for document in benchmark.knowledge_documents:
            raw = RawKnowledgeRecord(
                source_system="eval:enterprise-support-v1",
                source_record_id=f"{document.knowledge_id}.md",
                source_version=document.source_version,
                content_type="text/markdown",
                payload=document.text.encode("utf-8"),
                access_policy=document.access,
                captured_at=datetime(2026, 10, 11, tzinfo=UTC),
            )
            ingestion.execute(
                IngestKnowledgeCommand(
                    knowledge_id=document.knowledge_id,
                    raw_record=raw,
                )
            )

        current_chunks = load_current_chunks(database)
        provider = SentenceTransformerEmbeddingProvider()
        repository = SQLiteEmbeddingRepository(database)
        materialization = MaterializeEmbeddings(
            provider=provider,
            repository=repository,
        ).execute()

        lexical = SQLiteFtsKnowledgeRetriever(database)
        dense = ExactVectorKnowledgeRetriever(
            provider=provider,
            repository=repository,
        )
        hybrid = HybridRrfKnowledgeRetriever(
            lexical=lexical,
            dense=dense,
        )
        retrievers = {
            "bm25": lexical,
            "dense": dense,
            "hybrid": hybrid,
        }

        runs: dict[str, EvalRun] = {}
        for name, retriever in retrievers.items():
            provenance = build_eval_provenance(
                repository_root=repository_root,
                lockfile=arguments.lockfile,
                runtime={
                    "evaluator": RETRIEVAL_EVALUATOR_VERSION,
                    "retrieval_strategy": retriever.strategy_version,
                    "dataset_kind": "enterprise-support",
                    "dataset_split": split.value,
                    "embedding_model": MODEL_IDENTIFIER,
                    "embedding_model_revision": MODEL_REVISION,
                    "sentence_transformers_version": sentence_transformers.__version__,
                    "limit": 5,
                },
            )
            subject = EvalSubject(
                subject_id="retrieval",
                version=retriever.strategy_version,
                configuration={
                    "strategy_name": name,
                    "retrieval_strategy": retriever.strategy_version,
                    "embedding_model": MODEL_IDENTIFIER,
                    "embedding_model_revision": MODEL_REVISION,
                    "limit": 5,
                },
            )
            runs[name] = ExperimentRunner(sink=sink).run(
                dataset=dataset,
                subject=subject,
                provenance=provenance,
                executor=RetrievalExperimentExecutor(
                    retriever=retriever,
                    current_chunks=current_chunks,
                ),
            )

    output: JsonObject = {
        "schema_version": 2,
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "version": dataset.version,
            "fingerprint": dataset.fingerprint,
            "split": split.value,
            "case_count": len(dataset.cases),
        },
        "embedding_materialization": {
            "embedded_count": materialization.embedded_count,
            "strategy_version": materialization.strategy_version,
            "model_identifier": materialization.model_identifier,
        },
        "runs": {name: eval_run_to_dict(run) for name, run in runs.items()},
        "summaries": {name: _summary(run) for name, run in runs.items()},
        "comparisons": {
            "bm25_to_dense": _comparison(runs["bm25"], runs["dense"]),
            "bm25_to_hybrid": _comparison(runs["bm25"], runs["hybrid"]),
        },
        "gate": {
            "policy": "retrieval-hard-invariants-v2",
            "passed": all(not hard_invariant_failures(run) for run in runs.values()),
            "note": (
                "Expected-evidence and no-answer misses remain benchmark outcomes. "
                "Authorization, currentness, evidence integrity, and result-contract "
                "failures are blocking invariants."
            ),
        },
    }

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if output["gate"]["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
