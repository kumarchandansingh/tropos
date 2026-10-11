"""Human-labelled evidence-sufficiency benchmark contracts.

Retrieval relevance and evidence sufficiency are deliberately separate. Candidate
cases may be prepared from synthetic/public-source research, but only
human-adjudicated approved cases can project into the generic evaluation model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalOrigin,
    EvalScope,
    EvalSplit,
    JsonObject,
    JsonValue,
)


class EvidenceSufficiencyLabel(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class EvidenceSufficiencyReason(StrEnum):
    NONE = "NONE"
    MISSING_CRITICAL_FACT = "MISSING_CRITICAL_FACT"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    UNAUTHORIZED_EVIDENCE = "UNAUTHORIZED_EVIDENCE"
    WEAK_SUPPORT = "WEAK_SUPPORT"
    NO_ANSWER_BEARING_PASSAGE = "NO_ANSWER_BEARING_PASSAGE"
    OTHER = "OTHER"


class EvidenceSourceRole(StrEnum):
    PRIMARY = "primary"
    CORROBORATION = "corroboration"
    CHALLENGE = "challenge"


@dataclass(frozen=True, slots=True)
class EvidenceSnippet:
    evidence_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be blank")
        if not self.text.strip():
            raise ValueError("evidence text must not be blank")

    def snapshot(self) -> JsonObject:
        return {
            "evidence_id": self.evidence_id,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSourceReference:
    source_id: str
    role: EvidenceSourceRole
    title: str
    url: str

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be blank")
        if not self.title.strip():
            raise ValueError("source title must not be blank")
        if not self.url.startswith(("https://", "http://")):
            raise ValueError("source url must be public http(s) provenance")

    def snapshot(self) -> JsonObject:
        return {
            "source_id": self.source_id,
            "role": self.role.value,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class HumanSufficiencyReview:
    reviewer: str
    reviewed_at: datetime
    label: EvidenceSufficiencyLabel
    reason: EvidenceSufficiencyReason
    required_facts: tuple[str, ...]
    missing_facts: tuple[str, ...]
    confidence: int
    would_answer: bool
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.reviewer.strip():
            raise ValueError("human review requires reviewer identity")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must include timezone information")
        if not self.required_facts:
            raise ValueError("human review requires at least one required fact")
        if any(not fact.strip() for fact in self.required_facts):
            raise ValueError("required_facts must not contain blanks")
        if len(self.required_facts) != len(set(self.required_facts)):
            raise ValueError("required_facts must not contain duplicates")
        if any(not fact.strip() for fact in self.missing_facts):
            raise ValueError("missing_facts must not contain blanks")
        if len(self.missing_facts) != len(set(self.missing_facts)):
            raise ValueError("missing_facts must not contain duplicates")
        if not 1 <= self.confidence <= 5:
            raise ValueError("confidence must be between 1 and 5")

        if self.label is EvidenceSufficiencyLabel.SUFFICIENT:
            if self.reason is not EvidenceSufficiencyReason.NONE:
                raise ValueError("SUFFICIENT review must use reason NONE")
            if self.missing_facts:
                raise ValueError("SUFFICIENT review must not declare missing facts")
            if not self.would_answer:
                raise ValueError("SUFFICIENT review must allow answering")
        else:
            if self.reason is EvidenceSufficiencyReason.NONE:
                raise ValueError("INSUFFICIENT review requires a reason")
            if self.would_answer:
                raise ValueError("INSUFFICIENT review must abstain")

    def snapshot(self) -> JsonObject:
        return {
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at.isoformat(),
            "label": self.label.value,
            "reason": self.reason.value,
            "required_facts": list(self.required_facts),
            "missing_facts": list(self.missing_facts),
            "confidence": self.confidence,
            "would_answer": self.would_answer,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSufficiencyCase:
    case_id: str
    evidence_set_id: str
    split: EvalSplit
    approval: EvalApproval
    query: str
    evidence: tuple[EvidenceSnippet, ...]
    pattern_ids: tuple[str, ...]
    source_references: tuple[EvidenceSourceReference, ...]
    reviews: tuple[HumanSufficiencyReview, ...] = ()
    adjudication: HumanSufficiencyReview | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("case_id", self.case_id),
            ("evidence_set_id", self.evidence_set_id),
            ("query", self.query),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        if not self.evidence:
            raise ValueError("evidence sufficiency case requires evidence")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique inside a case")

        if not self.pattern_ids or any(not item.strip() for item in self.pattern_ids):
            raise ValueError("pattern_ids must contain at least one non-blank value")
        if len(self.pattern_ids) != len(set(self.pattern_ids)):
            raise ValueError("pattern_ids must not contain duplicates")

        source_ids = tuple(item.source_id for item in self.source_references)
        if not source_ids:
            raise ValueError("evidence sufficiency case requires source provenance")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source reference IDs must be unique inside a case")

        if any(not tag.strip() for tag in self.tags):
            raise ValueError("tags must not contain blanks")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")

        if self.approval is EvalApproval.APPROVED:
            if not self.reviews:
                raise ValueError("approved sufficiency case requires human review")
            if self.adjudication is None:
                raise ValueError("approved sufficiency case requires human adjudication")

    def to_eval_case(self) -> EvalCase:
        """Project an approved human-adjudicated case to the generic eval contract."""

        if self.approval is not EvalApproval.APPROVED or self.adjudication is None:
            raise ValueError("only approved human-adjudicated cases can become eval goldens")

        adjudication = self.adjudication
        return EvalCase(
            case_id=self.case_id,
            purpose=(
                "Decide whether the supplied governed evidence set contains enough "
                "information to answer the query completely and safely."
            ),
            scope=EvalScope.COMPONENT,
            approval=EvalApproval.APPROVED,
            origin=EvalOrigin.SYNTHETIC,
            inputs={
                "query": self.query,
                "evidence_set_id": self.evidence_set_id,
                "evidence": [item.snapshot() for item in self.evidence],
                "pattern_ids": list(self.pattern_ids),
                "source_references": [source.snapshot() for source in self.source_references],
            },
            expected={
                "label": adjudication.label.value,
                "reason": adjudication.reason.value,
                "required_facts": list(adjudication.required_facts),
                "missing_facts": list(adjudication.missing_facts),
                "should_abstain": not adjudication.would_answer,
                "human_adjudicator": adjudication.reviewer,
                "human_review_count": len(self.reviews),
            },
            tags=tuple(dict.fromkeys(("evidence-sufficiency", *self.tags))),
        )


@dataclass(frozen=True, slots=True)
class EvidenceSufficiencyBenchmark:
    dataset_id: str
    version: str
    notes: str
    cases: tuple[EvidenceSufficiencyCase, ...]

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be blank")
        if not self.version.strip():
            raise ValueError("version must not be blank")
        if not self.notes.strip():
            raise ValueError("notes must not be blank")
        if not self.cases:
            raise ValueError("evidence sufficiency benchmark requires cases")

        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evidence sufficiency case IDs must be unique")
        evidence_set_ids = tuple(case.evidence_set_id for case in self.cases)
        if len(evidence_set_ids) != len(set(evidence_set_ids)):
            raise ValueError("evidence set IDs must be unique")

    @property
    def candidate_count(self) -> int:
        return sum(case.approval is EvalApproval.CANDIDATE for case in self.cases)

    @property
    def approved_count(self) -> int:
        return sum(case.approval is EvalApproval.APPROVED for case in self.cases)

    def summary(self) -> JsonObject:
        """Return deterministic benchmark status without treating candidates as gold."""

        by_split: JsonObject = {}
        for split in EvalSplit:
            split_cases = tuple(case for case in self.cases if case.split is split)
            by_split[split.value] = {
                "candidate": sum(case.approval is EvalApproval.CANDIDATE for case in split_cases),
                "approved": sum(case.approval is EvalApproval.APPROVED for case in split_cases),
            }

        approved_labels: dict[str, int] = {label.value: 0 for label in EvidenceSufficiencyLabel}
        approved_reasons: dict[str, int] = {reason.value: 0 for reason in EvidenceSufficiencyReason}
        for case in self.cases:
            if case.approval is not EvalApproval.APPROVED or case.adjudication is None:
                continue
            approved_labels[case.adjudication.label.value] += 1
            approved_reasons[case.adjudication.reason.value] += 1

        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "case_count": len(self.cases),
            "candidate_count": self.candidate_count,
            "approved_count": self.approved_count,
            "by_split": by_split,
            "approved_labels": approved_labels,
            "approved_reasons": approved_reasons,
        }

    def approved_dataset(self, split: EvalSplit) -> EvalDataset:
        """Return only human-adjudicated approved cases for scoring."""

        approved = tuple(
            case.to_eval_case()
            for case in self.cases
            if case.split is split and case.approval is EvalApproval.APPROVED
        )
        if not approved:
            raise ValueError(
                f"split {split.value} has no human-adjudicated approved sufficiency cases"
            )
        return EvalDataset(
            dataset_id=f"{self.dataset_id}-approved",
            version=f"{self.version}-{split.value}",
            capability="evidence_sufficiency",
            split=split,
            cases=approved,
        )


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError("expected JSON array")
    return value


def _text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty text")
    return value


def _optional_text(value: JsonValue) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("expected text or null")
    return value


def _strings(value: JsonValue) -> tuple[str, ...]:
    result = tuple(_text(item) for item in _array(value))
    if len(result) != len(set(result)):
        raise ValueError("string list must not contain duplicates")
    return result


def _parse_datetime(value: JsonValue) -> datetime:
    text = _text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reviewed_at must include timezone information")
    return parsed


def _parse_review(raw: JsonValue) -> HumanSufficiencyReview:
    row = _object(raw)
    confidence = row["confidence"]
    if type(confidence) is not int:
        raise ValueError("confidence must be an integer")
    would_answer = row["would_answer"]
    if type(would_answer) is not bool:
        raise ValueError("would_answer must be a boolean")
    return HumanSufficiencyReview(
        reviewer=_text(row["reviewer"]),
        reviewed_at=_parse_datetime(row["reviewed_at"]),
        label=EvidenceSufficiencyLabel(_text(row["label"])),
        reason=EvidenceSufficiencyReason(_text(row["reason"])),
        required_facts=_strings(row["required_facts"]),
        missing_facts=_strings(row["missing_facts"]),
        confidence=confidence,
        would_answer=would_answer,
        notes=_optional_text(row.get("notes")),
    )


def _parse_case(raw: JsonValue) -> EvidenceSufficiencyCase:
    row = _object(raw)
    evidence = tuple(
        EvidenceSnippet(
            evidence_id=_text(item["evidence_id"]),
            text=_text(item["text"]),
        )
        for item in (_object(value) for value in _array(row["evidence"]))
    )
    sources = tuple(
        EvidenceSourceReference(
            source_id=_text(item["source_id"]),
            role=EvidenceSourceRole(_text(item["role"])),
            title=_text(item["title"]),
            url=_text(item["url"]),
        )
        for item in (_object(value) for value in _array(row["source_references"]))
    )
    reviews = tuple(_parse_review(value) for value in _array(row.get("reviews", [])))
    adjudication_raw = row.get("adjudication")
    adjudication = None if adjudication_raw is None else _parse_review(adjudication_raw)
    return EvidenceSufficiencyCase(
        case_id=_text(row["case_id"]),
        evidence_set_id=_text(row["evidence_set_id"]),
        split=EvalSplit(_text(row["split"])),
        approval=EvalApproval(_text(row["approval"])),
        query=_text(row["query"]),
        evidence=evidence,
        pattern_ids=_strings(row["pattern_ids"]),
        source_references=sources,
        reviews=reviews,
        adjudication=adjudication,
        tags=_strings(row.get("tags", [])),
    )


def load_evidence_sufficiency_benchmark(
    path: str | Path,
) -> EvidenceSufficiencyBenchmark:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    row = _object(raw)
    return EvidenceSufficiencyBenchmark(
        dataset_id=_text(row["dataset_id"]),
        version=_text(row["version"]),
        notes=_text(row["notes"]),
        cases=tuple(_parse_case(value) for value in _array(row["cases"])),
    )
