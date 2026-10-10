from __future__ import annotations

import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT = ROOT / ".githooks" / "pre-commit"


def main() -> None:
    PRE_COMMIT.chmod(
        PRE_COMMIT.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=ROOT,
        check=True,
    )
    print("Tropos Git hooks enabled via core.hooksPath=.githooks")


if __name__ == "__main__":
    main()
