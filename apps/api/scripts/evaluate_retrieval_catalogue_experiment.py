"""Run the saved retrieval catalogue through the generic experiment runtime."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from tropos.evals.catalogue import Catalogue
from tropos.evals.contracts import EvalSubject
from tropos.evals.experiment_store import SQLiteExperimentStore
from tropos.evals.experiments import ExperimentRunner
from tropos.evals.provenance import build_eval_provenance
from tropos.evals.retrieval_experiment import (
    RETRIEVAL_EVALUATOR_VERSION,
    CatalogueRetrievalExperimentExecutor,
    catalogue_retrieval_dataset,
)
from tropos.evals.run_io import eval_run_to_dict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a retrieval catalogue through the generic EvalRun runtime"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    arguments = parser.parse_args()

    catalogue = Catalogue.load(arguments.dataset)
    dataset = catalogue_retrieval_dataset(catalogue)
    repository_root = Path(__file__).parents[2]
    provenance = build_eval_provenance(
        repository_root=repository_root,
        lockfile=arguments.lockfile,
        runtime={
            "evaluator": RETRIEVAL_EVALUATOR_VERSION,
            "retrieval_strategy": "sqlite-fts5-bm25-v1",
            "dataset_kind": "saved-catalogue",
            "limit": 5,
        },
    )
    subject = EvalSubject(
        subject_id="retrieval",
        version="sqlite-fts5-bm25-v1",
        configuration={
            "retrieval_strategy": "sqlite-fts5-bm25-v1",
            "evaluator": RETRIEVAL_EVALUATOR_VERSION,
            "limit": 5,
        },
    )

    sink = None if arguments.database is None else SQLiteExperimentStore(arguments.database)
    with tempfile.TemporaryDirectory(prefix="tropos-retrieval-experiment-") as temp:
        run = ExperimentRunner(sink=sink).run(
            dataset=dataset,
            subject=subject,
            provenance=provenance,
            executor=CatalogueRetrievalExperimentExecutor(
                catalogue=catalogue,
                directory=Path(temp),
            ),
        )

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            eval_run_to_dict(run),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(run.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
