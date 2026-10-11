"""Manage human review and adjudication for the evidence-sufficiency benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tropos.evals.evidence_sufficiency import load_evidence_sufficiency_benchmark
from tropos.evals.evidence_sufficiency_review_workflow import (
    agreement_summary,
    export_adjudication_packet,
    export_review_packet,
    import_adjudication_packet,
    import_review_packet,
    write_benchmark,
)


def _default_dataset() -> Path:
    return (
        Path(__file__).parents[1] / "evals" / "resolve" / "evidence_sufficiency_candidates_v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export/import human review packets without weakening benchmark governance."
    )
    parser.add_argument("--dataset", type=Path, default=_default_dataset())
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_review = subparsers.add_parser("export-review")
    export_review.add_argument("--output", type=Path, required=True)
    export_review.add_argument("--reviewer", default="")

    import_review = subparsers.add_parser("import-review")
    import_review.add_argument("--packet", type=Path, required=True)
    import_review.add_argument("--output", type=Path, required=True)

    report = subparsers.add_parser("report")
    report.add_argument("--output", type=Path)

    export_adj = subparsers.add_parser("export-adjudication")
    export_adj.add_argument("--output", type=Path, required=True)

    import_adj = subparsers.add_parser("import-adjudication")
    import_adj.add_argument("--packet", type=Path, required=True)
    import_adj.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    benchmark = load_evidence_sufficiency_benchmark(args.dataset)

    if args.command == "export-review":
        export_review_packet(benchmark, args.output, reviewer=args.reviewer)
        return 0

    if args.command == "import-review":
        updated = import_review_packet(benchmark, args.packet)
        write_benchmark(updated, args.output)
        return 0

    if args.command == "report":
        rendered = (
            json.dumps(
                agreement_summary(benchmark),
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        return 0

    if args.command == "export-adjudication":
        export_adjudication_packet(benchmark, args.output)
        return 0

    if args.command == "import-adjudication":
        updated = import_adjudication_packet(benchmark, args.packet)
        write_benchmark(updated, args.output)
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
