"""Run BM25, dense MPNet, and hybrid RRF through one generic EvalRun path."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import sentence_transformers
from sentence_transformers import SentenceTransformer

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.embeddings.materialize import MaterializeEmbeddings
from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric
from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.evals.abstention import (
    TopScoreAbstentionPolicy,
    TopScoreThresholdRetriever,
    calibrate_top_score_threshold,
)
from tropos.evals.contracts import (
    EvalDataset,
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

MODEL_IDENTIFIER = "sentence-transformers/all-mpnet-base-v2"
MODEL_REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"
EMBEDDING_STRATEGY_VERSION = "sentence-transformers-all-mpnet-base-v2-normalized-v1"


class SentenceTransformerEmbeddingProvider:
    """Pinned local model used only by the expensive real-model eval workflow."""

    def __init__(self) -> None:
        self._model = SentenceTransformer(
            MODEL_IDENTIFIER,
            revision=MODEL_REVISION,
        )

    @property
    def strategy_version(self) -> str:
        return EMBEDDING_STRATEGY_VERSION

    @property
    def model_identifier(self) -> str:
        return MODEL_IDENTIFIER

    @property
    def model_revision(self) -> str:
        return MODEL_REVISION

    @property
    def dimensions(self) -> int:
        dimensions = self._model.get_embedding_dimension()
        if dimensions is None:
            raise RuntimeError("sentence-transformer did not report embedding dimensions")
        return int(dimensions)

    @property
    def similarity_metric(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE

    def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[EmbeddingVector, ...]:
        return self._encode(texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._encode((text,))[0]

    def _encode(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        vectors: Any = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return tuple(
            EmbeddingVector(tuple(float(value) for value in row.tolist())) for row in vectors
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


def _run_retrievers(
    *,
    dataset: EvalDataset,
    split: EvalSplit,
    retrievers: dict[str, KnowledgeChunkRetriever],
    current_chunks: dict[str, object],
    repository_root: Path,
    lockfile: Path,
    sink: SQLiteExperimentStore | None,
    abstention_policies: dict[str, TopScoreAbstentionPolicy] | None = None,
) -> dict[str, EvalRun]:
    runs: dict[str, EvalRun] = {}
    for name, base_retriever in retrievers.items():
        policy = None if abstention_policies is None else abstention_policies[name]
        retriever: KnowledgeChunkRetriever = (
            base_retriever
            if policy is None
            else TopScoreThresholdRetriever(
                retriever=base_retriever,
                policy=policy,
            )
        )
        runtime: JsonObject = {
            "evaluator": RETRIEVAL_EVALUATOR_VERSION,
            "retrieval_strategy": retriever.strategy_version,
            "base_retrieval_strategy": base_retriever.strategy_version,
            "dataset_kind": "enterprise-support",
            "dataset_split": split.value,
            "embedding_model": MODEL_IDENTIFIER,
            "embedding_model_revision": MODEL_REVISION,
            "sentence_transformers_version": sentence_transformers.__version__,
            "limit": 5,
        }
        configuration: JsonObject = {
            "strategy_name": name,
            "retrieval_strategy": retriever.strategy_version,
            "base_retrieval_strategy": base_retriever.strategy_version,
            "embedding_model": MODEL_IDENTIFIER,
            "embedding_model_revision": MODEL_REVISION,
            "limit": 5,
        }
        if policy is not None:
            runtime["abstention_policy"] = policy.as_dict()
            configuration["abstention_policy"] = policy.as_dict()

        provenance = build_eval_provenance(
            repository_root=repository_root,
            lockfile=lockfile,
            runtime=runtime,
        )
        subject = EvalSubject(
            subject_id="retrieval",
            version=retriever.strategy_version,
            configuration=configuration,
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
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate BM25, dense MPNet and hybrid RRF, calibrate top-score "
            "abstention on development data, then verify the selected policy "
            "without recalibration on holdout and challenge splits"
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=(
            Path(__file__).parents[1]
            / "evals"
            / "resolve"
            / "enterprise_support_benchmark_v1.json"
        ),
    )
    parser.add_argument(
        "--minimum-answerable-recall",
        type=float,
        required=True,
        help=(
            "Development-set Recall@5 floor that calibration must preserve. "
            "This is an explicit evaluation operating point, not a production default."
        ),
    )
    parser.add_argument("--lockfile", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    arguments = parser.parse_args()

    if not 0.0 <= arguments.minimum_answerable_recall <= 1.0:
        parser.error("--minimum-answerable-recall must be between 0 and 1")

    benchmark = load_enterprise_support_benchmark(arguments.dataset)
    datasets = {
        split: benchmark.retrieval_dataset(split)
        for split in EvalSplit
    }

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
        retrievers: dict[str, KnowledgeChunkRetriever] = {
            "bm25": lexical,
            "dense": dense,
            "hybrid": hybrid,
        }

        raw_runs = {
            split.value: _run_retrievers(
                dataset=datasets[split],
                split=split,
                retrievers=retrievers,
                current_chunks=current_chunks,
                repository_root=repository_root,
                lockfile=arguments.lockfile,
                sink=sink,
            )
            for split in EvalSplit
        }

        development_runs = raw_runs[EvalSplit.DEVELOPMENT.value]
        calibrations = {
            name: calibrate_top_score_threshold(
                development_runs[name],
                minimum_answerable_recall=arguments.minimum_answerable_recall,
            )
            for name in retrievers
        }
        policies = {
            name: calibration.policy
            for name, calibration in calibrations.items()
        }

        abstained_runs = {
            split.value: _run_retrievers(
                dataset=datasets[split],
                split=split,
                retrievers=retrievers,
                current_chunks=current_chunks,
                repository_root=repository_root,
                lockfile=arguments.lockfile,
                sink=sink,
                abstention_policies=policies,
            )
            for split in EvalSplit
        }

    all_runs = tuple(
        run
        for split_runs in (*raw_runs.values(), *abstained_runs.values())
        for run in split_runs.values()
    )
    gate_passed = all(not hard_invariant_failures(run) for run in all_runs)

    output: JsonObject = {
        "schema_version": 3,
        "datasets": {
            split.value: {
                "dataset_id": datasets[split].dataset_id,
                "version": datasets[split].version,
                "fingerprint": datasets[split].fingerprint,
                "split": split.value,
                "case_count": len(datasets[split].cases),
            }
            for split in EvalSplit
        },
        "embedding_materialization": {
            "embedded_count": materialization.embedded_count,
            "strategy_version": materialization.strategy_version,
            "model_identifier": materialization.model_identifier,
        },
        "raw_runs": {
            split: {
                name: eval_run_to_dict(run)
                for name, run in split_runs.items()
            }
            for split, split_runs in raw_runs.items()
        },
        "raw_summaries": {
            split: {
                name: _summary(run)
                for name, run in split_runs.items()
            }
            for split, split_runs in raw_runs.items()
        },
        "development_comparisons": {
            "bm25_to_dense": _comparison(
                development_runs["bm25"],
                development_runs["dense"],
            ),
            "bm25_to_hybrid": _comparison(
                development_runs["bm25"],
                development_runs["hybrid"],
            ),
        },
        "abstention": {
            "policy_family": "top-score-threshold-v1",
            "signal": "strategy-native top retrieval score",
            "calibration_split": EvalSplit.DEVELOPMENT.value,
            "validation_splits": [
                EvalSplit.HOLDOUT.value,
                EvalSplit.CHALLENGE.value,
            ],
            "minimum_answerable_recall": arguments.minimum_answerable_recall,
            "selection_objective": (
                "Preserve the requested development Recall@5 floor, then minimize "
                "expected-empty false-answer rate. Holdout/challenge never select "
                "the threshold."
            ),
            "strategies": {
                name: {
                    "calibration": calibrations[name].as_dict(),
                    "applied_run_summaries": {
                        split: _summary(abstained_runs[split][name])
                        for split in abstained_runs
                    },
                }
                for name in retrievers
            },
        },
        "abstained_runs": {
            split: {
                name: eval_run_to_dict(run)
                for name, run in split_runs.items()
            }
            for split, split_runs in abstained_runs.items()
        },
        "gate": {
            "policy": "retrieval-hard-invariants-v2",
            "passed": gate_passed,
            "note": (
                "Abstention calibration changes relevance selection, not access "
                "control. Authorization, currentness, evidence integrity, and "
                "result-contract failures remain blocking invariants on raw and "
                "abstention-applied runs."
            ),
        },
    }

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
