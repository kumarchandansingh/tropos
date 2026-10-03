"""Filesystem adapter. Links and protected roots never enter a cleanup plan."""

import hashlib
import os
import stat
from pathlib import Path

from katharo.domain import Observation, ReviewError

CHUNK = 1024 * 1024


def is_link(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def guarded_path(path: Path, root: Path | None = None) -> Path:
    path = Path(os.path.abspath(path))
    for part in [path, *path.parents]:
        if part.exists() and is_link(part):
            raise ReviewError("Links and junctions are excluded: " + str(part))
    if root and not path.is_relative_to(root):
        raise ReviewError("File is outside the approved folder.")
    return path


def protected(path: Path) -> bool:
    parts = {p.casefold() for p in path.parts}
    return bool(
        parts
        & {
            "windows",
            "program files",
            "program files (x86)",
            "programdata",
            "$recycle.bin",
            "system volume information",
        }
    )


def validate_root(value: str) -> Path:
    if not value.strip():
        raise ReviewError("Choose a folder first.")
    root = guarded_path(Path(value).expanduser())
    if not root.is_dir() or root == Path(root.anchor) or protected(root):
        raise ReviewError("Choose a personal folder, not a drive root or system folder.")
    return root


def signature(info: os.stat_result) -> tuple:
    # Windows creation/change-time semantics differ between path and handle queries.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def hash_file(path: Path) -> str:
    guarded_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ReviewError("Expected a regular file.")
    if getattr(before, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000):
        raise ReviewError("Cloud placeholder skipped; make it available offline first.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if signature(os.fstat(stream.fileno())) != signature(before):
            raise ReviewError("File changed before reading.")
        while block := stream.read(CHUNK):
            digest.update(block)
        if signature(os.fstat(stream.fileno())) != signature(before):
            raise ReviewError("File changed while reading.")
    if signature(path.stat()) != signature(before):
        raise ReviewError("File changed during hashing.")
    return digest.hexdigest()


def observe(path: Path) -> Observation:
    digest = hash_file(path)
    info = path.stat()
    return Observation(
        hashlib.sha256(str(path).encode()).hexdigest()[:24],
        str(path),
        info.st_size,
        info.st_mtime_ns,
        info.st_dev,
        info.st_ino,
        digest,
    )


def revalidate(record: dict, root: Path) -> Path:
    path = guarded_path(Path(record["path"]), root)
    info = path.stat()
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
        record["device"],
        record["inode"],
        record["size"],
        record["modified_ns"],
    ):
        raise ReviewError("File changed since review: " + str(path))
    if hash_file(path) != record["digest"]:
        raise ReviewError("File content changed since review: " + str(path))
    return path


def equal_bytes(left: Path, right: Path) -> bool:
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            x, y = a.read(CHUNK), b.read(CHUNK)
            if x != y:
                return False
            if not x:
                return True
