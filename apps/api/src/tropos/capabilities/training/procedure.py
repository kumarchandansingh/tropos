"""Framework-independent contracts for a training procedure draft."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EvidenceExcerpt:
    source_id: str
    locator: str
    text: str

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.locator.strip() or not self.text.strip():
            raise ValueError("Evidence excerpts require source, locator and text")


@dataclass(frozen=True)
class ProcedureStep:
    instruction: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProcedureDraft:
    title: str
    steps: tuple[ProcedureStep, ...]
    exceptions: tuple[str, ...]
    gaps: tuple[str, ...]


class ProcedureExtractor(Protocol):
    def extract(self, evidence: tuple[EvidenceExcerpt, ...]) -> ProcedureDraft: ...
