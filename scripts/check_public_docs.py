#!/usr/bin/env python3
"""Validate Tropos public documentation governance.

This check is intentionally deterministic. It enforces structural controls that
CI can evaluate reliably and leaves semantic quality to review.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PUBLIC_MARKDOWN_ROOTS = (
    Path("README.md"),
    Path("docs"),
)

AUTHORITATIVE_DOC_PREFIXES = (
    "docs/product/",
    "docs/architecture/",
    "docs/quality/",
    "docs/delivery/",
    "docs/decisions/",
    "docs/standards/",
)

PRODUCT_DOC_PREFIXES = (
    "README.md",
    "docs/product/",
    "docs/architecture/",
    "docs/decisions/",
)

EVAL_DOC_PREFIXES = (
    "docs/architecture/EVALUATION",
    "docs/quality/",
    "docs/decisions/",
)

DELIVERY_DOC_PREFIXES = (
    "docs/delivery/",
    "docs/product/delivery-governance.md",
    "docs/decisions/",
    "docs/standards/",
)

PRIVATE_META_PATTERNS = (
    re.compile(r"\binterview(?:er|ers|ing|s)?\b", re.IGNORECASE),
    re.compile(r"\brecruiter(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bhiring manager(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bresume bullet(?:s)?\b", re.IGNORECASE),
    re.compile(r"\binterview[- ]ready\b", re.IGNORECASE),
    re.compile(r"\binterview playbook\b", re.IGNORECASE),
    re.compile(r"\bsample answer(?:s)?\b", re.IGNORECASE),
)

ADR_REQUIRED_SECTIONS = (
    "## Context",
    "## Decision drivers and constraints",
    "## Options considered",
    "## Decision",
    "## Consequences",
    "## Evidence",
    "## Revisit when",
)


def _run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _changed_files(base: str | None, head: str | None) -> tuple[str, ...]:
    if base and head:
        output = _run_git("diff", "--name-only", f"{base}..{head}")
        return tuple(line for line in output.splitlines() if line)

    event_path = os.getenv("GITHUB_EVENT_PATH")
    event_name = os.getenv("GITHUB_EVENT_NAME")
    if event_path and Path(event_path).exists():
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        if event_name == "pull_request":
            base_sha = event["pull_request"]["base"]["sha"]
            head_sha = event["pull_request"]["head"]["sha"]
            output = _run_git("diff", "--name-only", f"{base_sha}..{head_sha}")
            return tuple(line for line in output.splitlines() if line)
        if event_name == "push":
            before = event.get("before")
            after = event.get("after")
            if before and after and before != "0" * 40:
                output = _run_git("diff", "--name-only", f"{before}..{after}")
                return tuple(line for line in output.splitlines() if line)

    output = _run_git("diff", "--name-only", "HEAD~1..HEAD")
    return tuple(line for line in output.splitlines() if line)


def _public_markdown_files() -> tuple[Path, ...]:
    files: list[Path] = []
    root_readme = REPO_ROOT / "README.md"
    if root_readme.exists():
        files.append(root_readme)

    docs_root = REPO_ROOT / "docs"
    if docs_root.exists():
        files.extend(sorted(path for path in docs_root.rglob("*.md") if path.is_file()))
    return tuple(files)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _has_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _is_authoritative_doc(path: str) -> bool:
    return path == "README.md" or _has_prefix(path, AUTHORITATIVE_DOC_PREFIXES)


def _is_material_product_change(path: str) -> bool:
    return (
        path.startswith("apps/api/src/tropos/core/")
        or path.startswith("apps/api/src/tropos/capabilities/")
    )


def _is_eval_change(path: str) -> bool:
    return (
        path.startswith("apps/api/src/tropos/evals/")
        or path.startswith("apps/api/evals/")
        or path.startswith("apps/api/scripts/evaluate")
        or path.endswith("retrieval-regression-gate.yml")
        or path.endswith("hybrid-real-eval.yml")
    )


def _is_delivery_change(path: str) -> bool:
    return (
        path.startswith(".github/workflows/")
        or path == ".github/pull_request_template.md"
        or path.startswith(".githooks/")
        or path.startswith("scripts/")
    )


def _pr_body() -> str:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        return ""
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return ""
    body = pull_request.get("body")
    return body if isinstance(body, str) else ""


def _documentation_na_has_rationale(body: str) -> bool:
    if not re.search(
        r"-\s*\[[xX]\]\s*Documentation impact is N/A",
        body,
    ):
        return False

    match = re.search(
        r"## Documentation rationale\s*(.*?)(?=\n##\s|\Z)",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return False

    rationale = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL).strip()
    return len(rationale) >= 40


def _check_public_language(errors: list[str]) -> None:
    for path in _public_markdown_files():
        text = path.read_text(encoding="utf-8")
        first_non_blank = next((line for line in text.splitlines() if line.strip()), "")
        if not first_non_blank.startswith("# "):
            errors.append(f"{_relative(path)}: public Markdown must start with one H1 title")

        for pattern in PRIVATE_META_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text[: match.start()].count("\n") + 1
                errors.append(
                    f"{_relative(path)}:{line}: public docs contain private/interview meta-language "
                    f"({match.group(0)!r})"
                )


def _check_changed_adrs(changed: tuple[str, ...], errors: list[str]) -> None:
    for relative in changed:
        if not (
            relative.startswith("docs/decisions/ADR-")
            and relative.endswith(".md")
            and (REPO_ROOT / relative).exists()
        ):
            continue

        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        missing = [section for section in ADR_REQUIRED_SECTIONS if section not in text]
        if missing:
            errors.append(
                f"{relative}: changed ADR is missing required section(s): "
                + ", ".join(missing)
            )


def _check_documentation_impact(changed: tuple[str, ...], errors: list[str]) -> None:
    if os.getenv("GITHUB_EVENT_NAME") != "pull_request":
        return

    changed_docs = tuple(path for path in changed if _is_authoritative_doc(path))
    body = _pr_body()
    na_ok = _documentation_na_has_rationale(body)

    def require_docs(
        impacted: bool,
        accepted_prefixes: tuple[str, ...],
        label: str,
    ) -> None:
        if not impacted:
            return
        if any(_has_prefix(path, accepted_prefixes) for path in changed_docs):
            return
        if na_ok:
            return
        errors.append(
            f"{label}: material change requires an authoritative documentation update "
            "or a checked 'Documentation impact is N/A' with at least 40 characters "
            "of rationale in the PR body"
        )

    require_docs(
        any(_is_material_product_change(path) for path in changed),
        PRODUCT_DOC_PREFIXES,
        "product/architecture documentation",
    )
    require_docs(
        any(_is_eval_change(path) for path in changed),
        EVAL_DOC_PREFIXES,
        "evaluation documentation",
    )
    require_docs(
        any(_is_delivery_change(path) for path in changed),
        DELIVERY_DOC_PREFIXES,
        "delivery documentation",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()

    changed = _changed_files(args.base, args.head)
    errors: list[str] = []

    _check_public_language(errors)
    _check_changed_adrs(changed, errors)
    _check_documentation_impact(changed, errors)

    if errors:
        print("Documentation governance failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Documentation governance passed "
        f"({len(changed)} changed file(s), {len(_public_markdown_files())} public Markdown file(s))."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
