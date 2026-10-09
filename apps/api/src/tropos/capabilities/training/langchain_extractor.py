"""LangChain adapter with prompt-local aliases resolved to stable Tropos evidence."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from tropos.capabilities.training.procedure import (
    EvidenceExcerpt,
    GapKind,
    ProcedureDraft,
    ProcedureException,
    ProcedureGap,
    ProcedureStep,
)
from tropos.core.domain.evidence import EvidenceRef


class _Step(BaseModel):
    instruction: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class _Exception(BaseModel):
    description: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class _Gap(BaseModel):
    description: str = Field(min_length=1)
    kind: Literal["missing_information", "conflict", "ambiguity"]
    evidence_ids: list[str] = Field(min_length=1)


class _Draft(BaseModel):
    title: str = Field(min_length=1)
    steps: list[_Step]
    exceptions: list[_Exception]
    gaps: list[_Gap]


_INSTRUCTIONS = """Extract an end-user procedure from the supplied evidence.
Only include supported normal-path actions as steps. Treat negative UAT scenarios
as exceptions, not normal steps. Record missing information, conflicts, or
ambiguity as gaps; never invent missing details. Every step, exception, and gap
must cite one or more supplied evidence aliases such as E1 or E2. Return only the
requested structured schema.
"""


def _resolve(
    evidence_ids: list[str],
    aliases: dict[str, EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    try:
        return tuple(aliases[evidence_id] for evidence_id in evidence_ids)
    except KeyError as exc:
        raise ValueError("Model cited an unknown evidence ID") from exc


class LangChainProcedureExtractor:
    """Accept an injected chat model while keeping LangChain outside domain contracts."""

    def __init__(self, model: Any) -> None:
        self._structured_model = model.with_structured_output(_Draft)

    def extract(self, evidence: tuple[EvidenceExcerpt, ...]) -> ProcedureDraft:
        if not evidence:
            raise ValueError("At least one evidence excerpt is required")

        from langchain_core.messages import HumanMessage, SystemMessage

        aliases = {
            f"E{index}": item.reference for index, item in enumerate(evidence, start=1)
        }
        payload = "\n\n".join(
            (
                f"[E{index}] source={item.reference.source_system}:"
                f"{item.reference.source_record_id}@v{item.reference.source_version} "
                f"locator={item.reference.locator}\n{item.text}"
            )
            for index, item in enumerate(evidence, start=1)
        )
        result = self._structured_model.invoke(
            [SystemMessage(content=_INSTRUCTIONS), HumanMessage(content=payload)]
        )
        if not isinstance(result, _Draft):
            result = _Draft.model_validate(result)

        return ProcedureDraft(
            title=result.title,
            steps=tuple(
                ProcedureStep(
                    instruction=step.instruction,
                    evidence_refs=_resolve(step.evidence_ids, aliases),
                )
                for step in result.steps
            ),
            exceptions=tuple(
                ProcedureException(
                    description=exception.description,
                    evidence_refs=_resolve(exception.evidence_ids, aliases),
                )
                for exception in result.exceptions
            ),
            gaps=tuple(
                ProcedureGap(
                    description=gap.description,
                    kind=GapKind(gap.kind),
                    evidence_refs=_resolve(gap.evidence_ids, aliases),
                )
                for gap in result.gaps
            ),
        )
