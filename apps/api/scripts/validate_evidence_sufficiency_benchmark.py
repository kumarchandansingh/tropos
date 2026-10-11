"""Validate and summarize the evidence-sufficiency benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tropos.evals.evidence_sufficiency import load_evidence_sufficiency_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate evidence-sufficiency cases and report candidate/approved human-label status."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=(
            Path(__file__).parents[1]
            / "evals"
            / "resolve"
            / "evidence_sufficiency_candidates_v1.json"
        ),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    benchmark = load_evidence_sufficiency_benchmark(arguments.dataset)
    summary = benchmark.summary()
    rendered = json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
