"""Catalogue, execution and export commands over the same saved evaluation records."""

import argparse
import json
import platform
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

from tropos.evals.catalogue import Catalogue, Json
from tropos.evals.execution import execute_catalogue
from tropos.evals.fixtures import prepare_fixture
from tropos.evals.reporting import markdown
from tropos.evals.run_store import EvaluationStore


def write_output(value: dict[str, Json], output: Path | None, format_name: str = "json") -> None:
    content = (
        markdown(value)
        if format_name == "markdown"
        else json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tropos synthetic retrieval evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    catalogue_parser = commands.add_parser("catalogue", help="Show planned cases; never executes")
    run_parser = commands.add_parser("run", help="Execute approved cases using real BM25")
    report_parser = commands.add_parser("report", help="Read a saved run without executing")
    for command in (catalogue_parser, run_parser):
        command.add_argument("--dataset", type=Path, required=True)
    for command in (run_parser, report_parser):
        command.add_argument("--database", type=Path, required=True)
    for command in (catalogue_parser, run_parser, report_parser):
        command.add_argument("--output", type=Path)
        command.add_argument("--format", choices=("json", "markdown"), default="json")
    run_parser.add_argument("--lockfile", type=Path, required=True)
    report_parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "report":
            if not arguments.database.is_file():
                raise ValueError("evaluation database not found")
            write_output(
                EvaluationStore(arguments.database).report(arguments.run_id),
                arguments.output,
                arguments.format,
            )
            return 0
        catalogue = Catalogue.load(arguments.dataset)
        if arguments.command == "catalogue":
            write_output(
                {
                    "dataset_id": catalogue.dataset_id,
                    "version": catalogue.version,
                    "digest": catalogue.fingerprint,
                    "definition": json.loads(catalogue.snapshot),
                },
                arguments.output,
                arguments.format,
            )
            return 0
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
            ).stdout.strip()
        )
        provenance: dict[str, Json] = {
            "code_revision": revision,
            "working_tree_dirty": dirty,
            "dependency_digest": sha256(arguments.lockfile.read_bytes()).hexdigest(),
            "python_version": platform.python_version(),
            "evaluator": "saved-retrieval-v1",
            "retrieval_strategy": "sqlite-fts5-bm25-v1",
            "max_characters": 2000,
            "gate_policy": "all-expectations-and-invariants-v1",
            "limit": 5,
        }
        store = EvaluationStore(arguments.database)
        with tempfile.TemporaryDirectory(prefix="tropos-eval-") as folder:
            run_id = execute_catalogue(
                catalogue,
                store,
                lambda case: prepare_fixture(catalogue, case, Path(folder)),
                provenance,
            )
        report = store.report(run_id)
        write_output(report, arguments.output, arguments.format)
        print(f"Saved evaluation run: {run_id}", file=__import__("sys").stderr)
        return 0 if report["outcome"] == "passed" else 1
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"Evaluation could not start: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
