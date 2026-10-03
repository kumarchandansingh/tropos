"""Domain vocabulary. No UI, database, or filesystem dependencies."""

from dataclasses import asdict, dataclass


class ReviewError(ValueError):
    """A review or filesystem precondition was not satisfied."""


@dataclass(frozen=True)
class Observation:
    id: str
    path: str
    size: int
    modified_ns: int
    device: int
    inode: int
    digest: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Extraction:
    text: str
    strategy: str
    status: str
    warning: str = ""


def validate_selection(groups: list[dict], selected: set[str]) -> None:
    """Only exact extras are actionable; every affected group retains a copy."""
    if not selected:
        raise ReviewError("Select at least one extra copy.")
    allowed = {f["id"] for g in groups if g["kind"] == "exact" for f in g["files"]}
    if not selected <= allowed:
        raise ReviewError("Only verified exact duplicates can enter this cleanup plan.")
    for group in groups:
        ids = {f["id"] for f in group["files"]}
        if ids & selected and ids <= selected:
            raise ReviewError("Keep at least one copy in every group.")
