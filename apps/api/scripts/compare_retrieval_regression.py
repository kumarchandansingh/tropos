"""Compare baseline and candidate saved retrieval runs and enforce regression policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from tropos.evals.contracts import JsonObject
from tropos.evals.regression_gate import compare_retrieval_reports


def _load(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(JsonObject, value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tropos retrieval regression gate")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    arguments = parser.parse_args()

    decision = compare_retrieval_reports(
        _load(arguments.baseline),
        _load(arguments.candidate),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(decision.as_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    summary = decision.markdown()
    if arguments.summary is not None:
        arguments.summary.parent.mkdir(parents=True, exist_ok=True)
        with arguments.summary.open("a", encoding="utf-8") as handle:
            handle.write(summary)
    print(summary)
    return 0 if decision.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
