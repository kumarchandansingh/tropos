from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"


def run(*args: str) -> None:
    subprocess.run(args, cwd=API_DIR, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Tropos API Ruff checks using the same commands locally and in automation."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check formatting/lint without modifying files.",
    )
    args = parser.parse_args()

    if args.check:
        run("uv", "run", "ruff", "format", "--check", ".")
        run("uv", "run", "ruff", "check", ".")
        return

    run("uv", "run", "ruff", "check", "--fix", ".")
    run("uv", "run", "ruff", "format", ".")


if __name__ == "__main__":
    main()
