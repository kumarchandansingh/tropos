"""Validate every Mermaid fence under docs/ by rendering it with Mermaid CLI.

The script requires Node.js and npx. It extracts each Mermaid block to a temporary
file and asks the same Mermaid parser used by mermaid-cli to render it. Any parse
or render failure is reported with the source Markdown file and block number.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MERMAID_FENCE = re.compile(r"```mermaid\s*\n([\s\S]*?)```", re.MULTILINE)


def main() -> None:
    failures: list[str] = []
    blocks_checked = 0

    with tempfile.TemporaryDirectory() as temporary_directory:
        temp = Path(temporary_directory)

        for markdown_path in sorted(DOCS.rglob("*.md")):
            content = markdown_path.read_text(encoding="utf-8")
            relative = markdown_path.relative_to(ROOT)

            for index, match in enumerate(MERMAID_FENCE.finditer(content), start=1):
                blocks_checked += 1
                input_path = temp / f"diagram-{blocks_checked}.mmd"
                output_path = temp / f"diagram-{blocks_checked}.svg"
                input_path.write_text(match.group(1), encoding="utf-8")

                result = subprocess.run(
                    [
                        "npx",
                        "--yes",
                        "@mermaid-js/mermaid-cli@11.12.0",
                        "--input",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--quiet",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    details = (result.stderr or result.stdout).strip()
                    failures.append(
                        f"{relative} Mermaid block {index}\n{details}"
                    )

    if failures:
        joined = "\n\n".join(failures)
        raise SystemExit(
            f"Mermaid validation failed for {len(failures)} block(s):\n\n{joined}"
        )

    print(f"Validated {blocks_checked} Mermaid diagram(s) under docs/.")


if __name__ == "__main__":
    main()
