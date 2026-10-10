from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=ROOT,
        check=True,
    )
    print("Tropos Git hooks enabled via core.hooksPath=.githooks")


if __name__ == "__main__":
    main()
