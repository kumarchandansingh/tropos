"""Reproducible provenance helpers for evaluation runs."""

from __future__ import annotations

import platform
import subprocess
from hashlib import sha256
from pathlib import Path

from tropos.evals.contracts import EvalRunProvenance, JsonObject


def build_eval_provenance(
    *,
    repository_root: Path,
    lockfile: Path,
    runtime: JsonObject,
) -> EvalRunProvenance:
    """Capture code/dependency/runtime identity without provider-specific coupling."""

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not revision:
        raise RuntimeError("git revision was blank")

    digest = sha256(lockfile.read_bytes()).hexdigest()
    resolved_runtime: JsonObject = {
        "python_version": platform.python_version(),
        **runtime,
    }
    return EvalRunProvenance(
        code_revision=revision,
        dependency_digest=digest,
        runtime=resolved_runtime,
    )
