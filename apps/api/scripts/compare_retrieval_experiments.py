"""Compare two generic retrieval EvalRun records and enforce the PR gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tropos.evals.regression_gate import compare_retrieval_runs
from tropos.evals.run_io import eval_run_from_dict


def _load(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("evaluation run JSON must be an object")
    return eval_run_from_dict(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    arguments = parser.parse_args()

    decision = compare_retrieval_runs(
        _load(arguments.baseline),
        _load(arguments.candidate),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(decision.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if arguments.summary is not None:
        arguments.summary.parent.mkdir(parents=True, exist_ok=True)
        with arguments.summary.open("a", encoding="utf-8") as handle:
            handle.write(decision.markdown())

    return 0 if decision.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
