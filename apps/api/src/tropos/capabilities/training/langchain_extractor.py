"""Optional LangChain adapter; no framework types leak into capability contracts."""

from typing import Any

from pydantic import BaseModel, Field

from tropos.capabilities.training.procedure import (
    EvidenceExcerpt,
    ProcedureDraft,
    ProcedureStep,
)


class _Step(BaseModel):
    instruction: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class _Draft(BaseModel):
    title: str = Field(min_length=1)
    steps: list[_Step]
    exceptions: list[str]
    gaps: list[str]


_INSTRUCTIONS = """Extract an end-user procedure from the supplied evidence.
Only include supported normal-path actions as steps. Treat negative UAT scenarios
as exceptions, not normal steps. Record missing navigation, prerequisites or
conflicts as gaps; never invent them. Every step must cite evidence IDs supplied
in the input. Return the requested structured schema.
"""


class LangChainProcedureExtractor:
    """Accept an injected LangChain chat model; caller controls provider and credentials."""

    def __init__(self, model: Any) -> None:
        self._structured_model = model.with_structured_output(_Draft)

    def extract(self, evidence: tuple[EvidenceExcerpt, ...]) -> ProcedureDraft:
        if not evidence:
            raise ValueError("At least one evidence excerpt is required")
        from langchain_core.messages import HumanMessage, SystemMessage

        payload = "\n\n".join(
            f"[{index}] source={item.source_id} locator={item.locator}\n{item.text}"
            for index, item in enumerate(evidence, start=1)
        )
        result = self._structured_model.invoke(
            [SystemMessage(content=_INSTRUCTIONS), HumanMessage(content=payload)]
        )
        if not isinstance(result, _Draft):
            result = _Draft.model_validate(result)
        valid_ids = {str(i) for i in range(1, len(evidence) + 1)}
        for step in result.steps:
            if any(ref not in valid_ids for ref in step.evidence_ids):
                raise ValueError("Model cited an unknown evidence ID")
        return ProcedureDraft(
            title=result.title,
            steps=tuple(
                ProcedureStep(instruction=s.instruction, evidence_ids=tuple(s.evidence_ids))
                for s in result.steps
            ),
            exceptions=tuple(result.exceptions),
            gaps=tuple(result.gaps),
        )
