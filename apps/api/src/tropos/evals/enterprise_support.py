"""Realistic synthetic enterprise-support benchmark and projections.

The benchmark is a single source for complete resolved-case records, retrieval
labels, Resolve knowledge-action expectations, and grounded Knowledge Article
expectations. Public vendor material informs failure patterns only; committed
records are synthetic and contain no customer data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tropos.capabilities.resolve.domain.knowledge_action import (
    ClosureEvidenceStatus,
    DecisionReason,
    KnowledgeAction,
    KnowledgeCoverage,
)
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_article import ArticleType
from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalOrigin,
    EvalScope,
    EvalSplit,
    JsonObject,
    JsonValue,
    fingerprint,
)
from tropos.evals.retrieval import RetrievalEvalCase


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


def _optional_text(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _text(value)


def _strings(value: JsonValue) -> tuple[str, ...]:
    result = tuple(_text(item) for item in _array(value))
    if len(result) != len(set(result)):
        raise ValueError("string lists must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class BenchmarkKnowledgeDocument:
    knowledge_id: str
    title: str
    text: str
    source_version: str
    access: AccessPolicy


@dataclass(frozen=True, slots=True)
class BenchmarkRetrievalQuery:
    query_id: str
    query: str
    access: RetrievalAccessContext
    relevant_knowledge_ids: tuple[str, ...]
    tags: tuple[str, ...]
    max_rank: int
    split: EvalSplit | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkSupportCase:
    case_id: str
    split: EvalSplit
    approval: EvalApproval
    origin: EvalOrigin
    tags: tuple[str, ...]
    research_pattern_ids: tuple[str, ...]
    access: RetrievalAccessContext
    case_record: JsonObject
    closure_evidence: ClosureEvidenceStatus
    knowledge_coverage: KnowledgeCoverage | None
    action: KnowledgeAction
    reason: DecisionReason
    retrieval_queries: tuple[BenchmarkRetrievalQuery, ...]
    article_expectation: JsonObject | None


@dataclass(frozen=True, slots=True)
class EnterpriseSupportBenchmark:
    dataset_id: str
    version: str
    default_split: EvalSplit
    notes: str
    knowledge_documents: tuple[BenchmarkKnowledgeDocument, ...]
    cases: tuple[BenchmarkSupportCase, ...]
    negative_retrieval_cases: tuple[BenchmarkRetrievalQuery, ...]

    def cases_for_split(self, split: EvalSplit) -> tuple[BenchmarkSupportCase, ...]:
        return tuple(case for case in self.cases if case.split is split)

    def retrieval_cases(
        self,
        split: EvalSplit | None = None,
    ) -> tuple[RetrievalEvalCase, ...]:
        selected_split = split or self.default_split
        projected: list[RetrievalEvalCase] = []

        for case in self.cases_for_split(selected_split):
            projected.extend(
                RetrievalEvalCase(
                    case_id=query.query_id,
                    query=query.query,
                    access=query.access,
                    relevant_knowledge_ids=query.relevant_knowledge_ids,
                    tags=_merge_tags(case.tags, query.tags),
                )
                for query in case.retrieval_queries
            )

        projected.extend(
            RetrievalEvalCase(
                case_id=query.query_id,
                query=query.query,
                access=query.access,
                relevant_knowledge_ids=query.relevant_knowledge_ids,
                tags=query.tags,
            )
            for query in self.negative_retrieval_cases
            if query.split is selected_split
        )
        return tuple(projected)

    def retrieval_dataset(
        self,
        split: EvalSplit | None = None,
    ) -> EvalDataset:
        """Project complete case packs into the generic retrieval EvalDataset."""

        selected_split = split or self.default_split
        cases: list[EvalCase] = []
        corpus_fingerprint = fingerprint(
            [
                {
                    "knowledge_id": document.knowledge_id,
                    "title": document.title,
                    "text": document.text,
                    "source_version": document.source_version,
                    "tenant_id": document.access.tenant_id,
                    "scope": document.access.scope.value,
                    "allowed_groups": list(document.access.allowed_groups),
                }
                for document in self.knowledge_documents
            ]
        )

        for support_case in self.cases_for_split(selected_split):
            for query in support_case.retrieval_queries:
                cases.append(
                    EvalCase(
                        case_id=query.query_id,
                        purpose=(
                            "Retrieve the current authorized knowledge expected for "
                            "this resolved support scenario."
                        ),
                        scope=EvalScope.COMPONENT,
                        approval=support_case.approval,
                        origin=support_case.origin,
                        inputs={
                            "query": query.query,
                            "tenant_id": query.access.tenant_id,
                            "groups": list(query.access.groups),
                            "max_rank": query.max_rank,
                            "corpus_fingerprint": corpus_fingerprint,
                        },
                        expected={"relevant_knowledge_ids": list(query.relevant_knowledge_ids)},
                        tags=_merge_tags(support_case.tags, query.tags),
                    )
                )

        for query in self.negative_retrieval_cases:
            if query.split is not selected_split:
                continue
            cases.append(
                EvalCase(
                    case_id=query.query_id,
                    purpose=(
                        "Return no evidence for an unsupported, ambiguous, "
                        "cross-tenant, or unauthorized retrieval request."
                    ),
                    scope=EvalScope.COMPONENT,
                    approval=EvalApproval.APPROVED,
                    origin=EvalOrigin.SYNTHETIC,
                    inputs={
                        "query": query.query,
                        "tenant_id": query.access.tenant_id,
                        "groups": list(query.access.groups),
                        "max_rank": query.max_rank,
                        "corpus_fingerprint": corpus_fingerprint,
                    },
                    expected={"relevant_knowledge_ids": []},
                    tags=query.tags,
                )
            )

        return EvalDataset(
            dataset_id=f"{self.dataset_id}-retrieval",
            version=f"{self.version}-{selected_split.value}",
            capability="retrieval",
            split=selected_split,
            cases=tuple(cases),
        )

    def resolve_decision_dataset(
        self,
        split: EvalSplit | None = None,
    ) -> EvalDataset:
        selected_split = split or self.default_split
        return EvalDataset(
            dataset_id=f"{self.dataset_id}-resolve-decision",
            version=f"{self.version}-{selected_split.value}",
            capability="resolve_decision",
            split=selected_split,
            cases=tuple(
                EvalCase(
                    case_id=case.case_id,
                    purpose=(
                        "Decide whether resolved-case knowledge should be reused, "
                        "improved, created, or skipped."
                    ),
                    scope=EvalScope.COMPONENT,
                    approval=case.approval,
                    origin=case.origin,
                    inputs={
                        "case_record": case.case_record,
                        "tenant_id": case.access.tenant_id,
                        "groups": list(case.access.groups),
                    },
                    expected={
                        "closure_evidence": case.closure_evidence.value,
                        "knowledge_coverage": (
                            case.knowledge_coverage.value
                            if case.knowledge_coverage is not None
                            else None
                        ),
                        "action": case.action.value,
                        "reason": case.reason.value,
                    },
                    tags=case.tags,
                )
                for case in self.cases_for_split(selected_split)
            ),
        )

    def knowledge_article_dataset(
        self,
        split: EvalSplit | None = None,
    ) -> EvalDataset:
        selected_split = split or self.default_split
        article_cases: list[EvalCase] = []
        for case in self.cases_for_split(selected_split):
            if case.article_expectation is None:
                continue
            article = case.article_expectation
            article_cases.append(
                EvalCase(
                    case_id=case.case_id,
                    purpose=(
                        "Generate or improve a grounded operational Knowledge Article "
                        "from the resolved-case evidence."
                    ),
                    scope=EvalScope.COMPONENT,
                    approval=case.approval,
                    origin=case.origin,
                    inputs={
                        "article_type": _text(article["article_type"]),
                        "subject": _text(article["subject"]),
                        "product": _text(article["product"]),
                        "module": _optional_text(article.get("module")),
                        "evidence": _array(article["evidence"]),
                        "reference_article": _object(article["reference_article"]),
                        "case_record": case.case_record,
                    },
                    expected=_object(article["expected"]),
                    tags=case.tags,
                )
            )

        if not article_cases:
            raise ValueError(f"split {selected_split.value} has no Knowledge Article cases")

        return EvalDataset(
            dataset_id=f"{self.dataset_id}-knowledge-article",
            version=f"{self.version}-{selected_split.value}",
            capability="resolve",
            split=selected_split,
            cases=tuple(article_cases),
        )


def _merge_tags(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tag for group in groups for tag in group))


def _parse_document(raw: JsonValue) -> BenchmarkKnowledgeDocument:
    row = _object(raw)
    access = AccessPolicy(
        tenant_id=_text(row["tenant_id"]),
        scope=AccessScope(_text(row["scope"])),
        allowed_groups=_strings(row["allowed_groups"]),
    )
    return BenchmarkKnowledgeDocument(
        knowledge_id=_text(row["knowledge_id"]),
        title=_text(row["title"]),
        text=_text(row["text"]),
        source_version=_text(row["source_version"]),
        access=access,
    )


def _parse_query(
    raw: JsonValue,
    *,
    access: RetrievalAccessContext | None = None,
    split: EvalSplit | None = None,
) -> BenchmarkRetrievalQuery:
    row = _object(raw)
    query_access = access or RetrievalAccessContext(
        tenant_id=_text(row["tenant_id"]),
        groups=_strings(row["groups"]),
    )
    max_rank = row["max_rank"]
    if type(max_rank) is not int or not 1 <= max_rank <= 5:
        raise ValueError("max_rank must be an integer from 1 to 5")
    return BenchmarkRetrievalQuery(
        query_id=_text(row["query_id"]),
        query=_text(row["query"]),
        access=query_access,
        relevant_knowledge_ids=_strings(row["relevant_knowledge_ids"]),
        tags=_strings(row["tags"]),
        max_rank=max_rank,
        split=split,
    )


def _expected_decision(
    closure: ClosureEvidenceStatus,
    coverage: KnowledgeCoverage | None,
) -> tuple[KnowledgeAction, DecisionReason]:
    if closure is ClosureEvidenceStatus.INSUFFICIENT:
        if coverage is not None:
            raise ValueError("insufficient closure evidence cannot carry knowledge coverage")
        return KnowledgeAction.NO_ACTION, DecisionReason.INSUFFICIENT_CLOSURE_EVIDENCE
    if coverage is KnowledgeCoverage.NONE:
        return KnowledgeAction.CREATE, DecisionReason.NO_RELATED_KNOWLEDGE
    if coverage is KnowledgeCoverage.PARTIAL:
        return KnowledgeAction.IMPROVE, DecisionReason.RELATED_KNOWLEDGE_INCOMPLETE
    if coverage is KnowledgeCoverage.SUFFICIENT:
        return KnowledgeAction.REUSE, DecisionReason.RELATED_KNOWLEDGE_SUFFICIENT
    raise ValueError("sufficient closure evidence requires knowledge coverage")


def _validate_case_record(case_id: str, record: JsonObject) -> None:
    required_text = (
        "status",
        "priority",
        "channel",
        "opened_at",
        "resolved_at",
        "short_description",
        "description",
        "resolution_notes",
    )
    for field in required_text:
        _text(record[field])

    if _text(record["status"]) != "resolved":
        raise ValueError(f"{case_id}: benchmark case must be resolved")

    environment = _object(record["environment"])
    for field in ("product", "module", "platform", "user_scope"):
        _text(environment[field])

    comments = _array(record["comments"])
    for comment in comments:
        _text(comment)

    notes = _array(record["work_notes"])
    if not notes:
        raise ValueError(f"{case_id}: case requires at least one work note")
    note_ids: list[str] = []
    for raw_note in notes:
        note = _object(raw_note)
        note_ids.append(_text(note["note_id"]))
        _text(note["author_role"])
        _text(note["text"])
    if len(note_ids) != len(set(note_ids)):
        raise ValueError(f"{case_id}: duplicate work-note IDs")


def _reference_evidence_ids(value: JsonValue) -> set[str]:
    collected: set[str] = set()
    if isinstance(value, dict):
        raw_refs = value.get("evidence_chunk_ids")
        if raw_refs is not None:
            collected.update(_strings(raw_refs))
        for child in value.values():
            collected.update(_reference_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            collected.update(_reference_evidence_ids(child))
    return collected


def _validate_article_expectation(
    case_id: str,
    action: KnowledgeAction,
    article: JsonObject | None,
) -> None:
    should_have_article = action in {KnowledgeAction.CREATE, KnowledgeAction.IMPROVE}
    if should_have_article != (article is not None):
        raise ValueError(
            f"{case_id}: CREATE/IMPROVE require an article expectation; "
            "REUSE/NO_ACTION must not create one"
        )
    if article is None:
        return

    _text(article["subject"])
    _text(article["product"])
    _optional_text(article.get("module"))

    evidence = _array(article["evidence"])
    evidence_ids: set[str] = set()
    for raw_evidence in evidence:
        item = _object(raw_evidence)
        evidence_id = _text(item["chunk_id"])
        _text(item["text"])
        if evidence_id in evidence_ids:
            raise ValueError(f"{case_id}: duplicate article evidence ID {evidence_id}")
        evidence_ids.add(evidence_id)

    article_type = ArticleType(_text(article["article_type"]))
    expected = _object(article["expected"])
    if ArticleType(_text(expected["article_type"])) is not article_type:
        raise ValueError(f"{case_id}: article type and expected type disagree")
    _strings(expected["required_sections"])
    _strings(expected["forbidden_terms"])

    for key in ("claims", "gaps"):
        for raw_item in _array(expected[key]):
            item = _object(raw_item)
            _text(item["contains"])
            refs = set(_strings(item["evidence_chunk_ids"]))
            if not refs <= evidence_ids:
                raise ValueError(
                    f"{case_id}: {key} references article evidence that is not supplied"
                )
            if key == "gaps":
                _text(item["kind"])

    reference = _object(article["reference_article"])
    if ArticleType(_text(reference["article_type"])) is not article_type:
        raise ValueError(f"{case_id}: reference article type disagrees with expectation")
    _text(reference["title"])
    reference_ids = _reference_evidence_ids(reference)
    if not reference_ids:
        raise ValueError(f"{case_id}: reference article requires evidence citations")
    if not reference_ids <= evidence_ids:
        raise ValueError(f"{case_id}: reference article cites evidence that is not supplied")


def _parse_case(
    raw: JsonValue,
    known_documents: dict[str, BenchmarkKnowledgeDocument],
) -> BenchmarkSupportCase:
    row = _object(raw)
    case_id = _text(row["case_id"])
    split = EvalSplit(_text(row["split"]))
    approval = EvalApproval(_text(row["approval"]))
    origin = EvalOrigin(_text(row["origin"]))
    access = RetrievalAccessContext(
        tenant_id=_text(row["tenant_id"]),
        groups=_strings(row["groups"]),
    )
    case_record = _object(row["case_record"])
    _validate_case_record(case_id, case_record)

    expected = _object(row["expected"])
    closure = ClosureEvidenceStatus(_text(expected["closure_evidence"]))
    coverage_raw = expected["knowledge_coverage"]
    coverage = KnowledgeCoverage(_text(coverage_raw)) if coverage_raw is not None else None
    action = KnowledgeAction(_text(expected["action"]))
    reason = DecisionReason(_text(expected["reason"]))
    canonical_action, canonical_reason = _expected_decision(closure, coverage)
    if (action, reason) != (canonical_action, canonical_reason):
        raise ValueError(f"{case_id}: expected action/reason does not match decision policy")

    queries = tuple(
        _parse_query(raw_query, access=access) for raw_query in _array(row["retrieval_queries"])
    )

    if action is KnowledgeAction.NO_ACTION and queries:
        raise ValueError(f"{case_id}: NO_ACTION case must not execute retrieval")
    if action is KnowledgeAction.CREATE and any(query.relevant_knowledge_ids for query in queries):
        raise ValueError(f"{case_id}: CREATE case must have no reusable knowledge label")
    if action in {KnowledgeAction.REUSE, KnowledgeAction.IMPROVE} and (
        not queries or any(not query.relevant_knowledge_ids for query in queries)
    ):
        raise ValueError(f"{case_id}: REUSE/IMPROVE queries require relevant knowledge")

    for query in queries:
        for knowledge_id in query.relevant_knowledge_ids:
            if knowledge_id not in known_documents:
                raise ValueError(f"{case_id}: unknown relevant knowledge ID {knowledge_id}")
            document = known_documents[knowledge_id]
            if document.access.tenant_id != access.tenant_id:
                raise ValueError(f"{case_id}: relevant knowledge is in another tenant")
            if document.access.scope is AccessScope.RESTRICTED and not set(
                document.access.allowed_groups
            ) & set(access.groups):
                raise ValueError(f"{case_id}: relevant knowledge is not authorized")

    article_raw = row["article_expectation"]
    article = _object(article_raw) if article_raw is not None else None
    _validate_article_expectation(case_id, action, article)

    return BenchmarkSupportCase(
        case_id=case_id,
        split=split,
        approval=approval,
        origin=origin,
        tags=_strings(row["tags"]),
        research_pattern_ids=_strings(row["research_pattern_ids"]),
        access=access,
        case_record=case_record,
        closure_evidence=closure,
        knowledge_coverage=coverage,
        action=action,
        reason=reason,
        retrieval_queries=queries,
        article_expectation=article,
    )


def load_enterprise_support_benchmark(path: Path) -> EnterpriseSupportBenchmark:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("enterprise support benchmark must be a JSON object")
    if raw.get("schema_version") != 1:
        raise ValueError("enterprise support benchmark requires schema_version 1")
    if raw.get("data_classification") != "synthetic":
        raise ValueError("enterprise support benchmark must contain synthetic data only")

    documents = tuple(_parse_document(item) for item in _array(raw["knowledge_documents"]))
    document_ids = tuple(document.knowledge_id for document in documents)
    if not documents or len(document_ids) != len(set(document_ids)):
        raise ValueError("knowledge documents require unique knowledge IDs")
    known_documents = {document.knowledge_id: document for document in documents}

    cases = tuple(_parse_case(item, known_documents) for item in _array(raw["cases"]))
    case_ids = tuple(case.case_id for case in cases)
    if not cases or len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark cases require unique case IDs")

    negative = tuple(
        _parse_query(
            item,
            split=EvalSplit(_text(_object(item)["split"])),
        )
        for item in _array(raw["negative_retrieval_cases"])
    )

    all_query_ids = [
        *(query.query_id for case in cases for query in case.retrieval_queries),
        *(query.query_id for query in negative),
    ]
    if len(all_query_ids) != len(set(all_query_ids)):
        raise ValueError("retrieval query IDs must be unique across the benchmark")

    for query in negative:
        if query.relevant_knowledge_ids:
            raise ValueError("negative retrieval cases cannot declare relevant knowledge")
        if query.split is None:
            raise ValueError("negative retrieval cases require an explicit split")

    return EnterpriseSupportBenchmark(
        dataset_id=_text(raw["dataset_id"]),
        version=_text(raw["version"]),
        default_split=EvalSplit(_text(raw["default_split"])),
        notes=_text(raw["notes"]),
        knowledge_documents=documents,
        cases=cases,
        negative_retrieval_cases=negative,
    )
