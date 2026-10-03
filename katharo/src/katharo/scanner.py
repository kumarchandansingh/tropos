"""Scan orchestration. Exact and document evidence follow separate paths."""

import hashlib
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from katharo.documents import extract_bounded, similarity
from katharo.filesystem import is_link, observe, protected, validate_root


def scan(
    value: str, recursive: bool, documents: bool, progress, cancelled, excluded: list[Path]
) -> dict:
    root = validate_root(value)
    result: dict[str, Any] = {
        "id": uuid4().hex,
        "root": str(root),
        "started": time.time(),
        "status": "scanning",
        "files": [],
        "groups": [],
        "warnings": [],
        "total_bytes": 0,
        "file_count": 0,
        "document_count": 0,
        "by_type": {},
    }
    paths: list[Path] = []
    identities = set()
    stack = [root]
    while stack:
        if cancelled():
            result["status"] = "cancelled"
            return result
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    try:
                        if (
                            any(path.is_relative_to(x) for x in excluded)
                            or protected(path)
                            or is_link(path)
                        ):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                stack.append(path)
                        elif entry.is_file(follow_symlinks=False):
                            # DirEntry.stat() can return inode=0 on Windows; query the path.
                            info = path.stat(follow_symlinks=False)
                            identity = (info.st_dev, info.st_ino)
                            if info.st_ino and identity in identities:
                                result["warnings"].append(
                                    {
                                        "path": str(path),
                                        "reason": "Hard-link alias excluded from duplicate accounting.",
                                    }
                                )
                                continue
                            identities.add(identity)
                            if getattr(info, "st_file_attributes", 0) & (
                                0x1000 | 0x40000 | 0x400000
                            ):
                                result["warnings"].append(
                                    {"path": str(path), "reason": "Cloud placeholder skipped."}
                                )
                                continue
                            paths.append(path)
                            result["total_bytes"] += info.st_size
                            result["file_count"] += 1
                            ext = path.suffix.lower() or "Other"
                            result["by_type"][ext] = result["by_type"].get(ext, 0) + info.st_size
                    except OSError as exc:
                        result["warnings"].append({"path": str(path), "reason": str(exc)})
        except OSError as exc:
            result["warnings"].append({"path": str(folder), "reason": str(exc)})
        progress("Discovering files", result["file_count"])
    sizes: dict[int, list[Path]] = defaultdict(list)
    for path in paths:
        try:
            if path.stat().st_size:
                sizes[path.stat().st_size].append(path)
        except OSError:
            pass
    candidates = {p for batch in sizes.values() if len(batch) > 1 for p in batch}
    doc_paths = (
        [p for p in paths if p.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}][:300]
        if documents
        else []
    )
    if (
        documents
        and len([p for p in paths if p.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]) > 300
    ):
        result["warnings"].append(
            {
                "path": str(root),
                "reason": "Document review limited to the first 300 documents; exact matching is unaffected.",
            }
        )
    observations = {}
    for index, path in enumerate(sorted(candidates | set(doc_paths))):
        if cancelled():
            result["status"] = "cancelled"
            return result
        progress("Hashing candidates", index + 1)
        try:
            record = observe(path).to_dict()
            observations[path] = record
            result["files"].append(record)
        except (OSError, ValueError) as exc:
            result["warnings"].append({"path": str(path), "reason": str(exc)})
    hashes: dict[str, list[dict]] = defaultdict(list)
    for record in result["files"]:
        hashes[record["digest"]].append(record)
    for digest, batch in hashes.items():
        if len(batch) > 1:
            batch.sort(
                key=lambda f: (
                    bool(__import__("re").search(r"\(\d+\)", Path(f["path"]).stem)),
                    len(f["path"]),
                    f["path"],
                )
            )
            result["groups"].append(
                {
                    "id": "exact-" + digest,
                    "kind": "exact",
                    "files": batch,
                    "evidence": "Same size and SHA-256. Byte equality is checked again before quarantine.",
                    "recoverable": sum(f["size"] for f in batch[1:]),
                }
            )
    extracted = []
    seen_hashes = set()
    for index, path in enumerate(doc_paths):
        if cancelled():
            result["status"] = "cancelled"
            return result
        document_record = observations.get(path)
        if not document_record or document_record["digest"] in seen_hashes:
            continue
        seen_hashes.add(document_record["digest"])
        progress("Comparing documents", index + 1)
        parsed = extract_bounded(path)
        if parsed.status != "ready":
            result["warnings"].append(
                {"path": str(path), "reason": parsed.warning or parsed.status}
            )
            continue
        result["document_count"] += 1
        fingerprint = hashlib.sha256((parsed.strategy + "\0" + parsed.text).encode()).hexdigest()
        extracted.append((document_record, parsed, fingerprint))
    for i, (left, a, ah) in enumerate(extracted):
        for right, b, bh in extracted[i + 1 :]:
            if cancelled():
                result["status"] = "cancelled"
                return result
            score = 1.0 if ah == bh else similarity(a.text, b.text)
            if ah == bh or score >= 0.72:
                result["groups"].append(
                    {
                        "id": "doc-" + left["id"] + right["id"],
                        "kind": "content" if ah == bh else "revision",
                        "files": [left, right],
                        "evidence": "Matching normalized extracted text"
                        if ah == bh
                        else f"Word-shingle overlap: {score:.0%}. This is not a probability of equivalence.",
                        "warning": a.warning,
                        "texts": [a.text, b.text],
                        "strategy": a.strategy,
                        "recoverable": 0,
                    }
                )
    result["recoverable"] = sum(g["recoverable"] for g in result["groups"] if g["kind"] == "exact")
    result["status"] = "complete"
    return result
