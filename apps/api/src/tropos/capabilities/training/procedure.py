"""Framework-independent contracts for a grounded training procedure draft."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from tropos.core.domain.evidence import EvidenceRef


@dataclass(frozen=True, slots=True)
class EvidenceExcerpt:
    reference: EvidenceRef
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Evidence excerpts require non-empty text")


@dataclass(frozen=True, slots=True)
class ProcedureStep:
    instruction: str
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.instruction.strip() or not self.evidence_refs:
            raise ValueError("Procedure steps require text and supporting evidence")


@dataclass(frozen=True, slots=True)
class ProcedureException:
    description: str
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.description.strip() or not self.evidence_refs:
            raise ValueError("Procedure exceptions require text and supporting evidence")


class GapKind(StrEnum):
    MISSING_INFORMATION = "missing_information"
    CONFLICT = "conflict"
    AMBIGUITY = "ambiguity"


@dataclass(frozen=True, slots=True)
class ProcedureGap:
    description: str
    kind: GapKind
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.description.strip() or not self.evidence_refs:
            raise ValueError("Procedure gaps require text and contextual evidence")


@dataclass(frozen=True, slots=True)
class ProcedureDraft:
    title: str
    steps: tuple[ProcedureStep, ...]
    exceptions: tuple[ProcedureException, ...]
    gaps: tuple[ProcedureGap, ...]

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Procedure draft title must not be blank")


class ProcedureExtractor(Protocol):
    def extract(self, evidence: tuple[EvidenceExcerpt, ...]) -> ProcedureDraft: ...
