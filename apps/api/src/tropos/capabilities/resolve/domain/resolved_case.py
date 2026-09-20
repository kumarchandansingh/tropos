from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ResolvedCase:
    """Canonical resolved-case data accepted by the Tropos core."""

    case_id: str
    source_system: str
    source_record_id: str
    title: str
    problem_summary: str
    resolution_summary: str
    resolved_at: datetime

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be blank")

        if not self.source_system.strip():
            raise ValueError("source_system must not be blank")

        if not self.source_record_id.strip():
            raise ValueError("source_record_id must not be blank")

        if self.resolved_at.tzinfo is None or self.resolved_at.utcoffset() is None:
            raise ValueError("resolved_at must include timezone information")
