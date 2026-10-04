"""Validated, versioned synthetic evaluation definitions; independent of execution."""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.access import AccessPolicy, AccessScope

type Json = str | int | float | bool | None | list[Json] | dict[str, Json]


def object_value(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def text(value: Json) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty text")
    return value


def array(value: Json) -> list[Json]:
    if not isinstance(value, list):
        raise ValueError("expected an array")
    return value


def strings(value: Json) -> tuple[str, ...]:
    result = tuple(text(item) for item in array(value))
    if len(set(result)) != len(result):
        raise ValueError("duplicate identifiers")
    return result


def canonical(value: Json) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: Json) -> str:
    return sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class FixtureDocument:
    knowledge_id: str
    text: str
    source_version: str
    access: AccessPolicy

    @classmethod
    def parse(cls, value: Json) -> FixtureDocument:
        row = object_value(value)
        return cls(
            text(row["knowledge_id"]),
            text(row["text"]),
            text(row["source_version"]),
            AccessPolicy(
                text(row["tenant_id"]),
                AccessScope(text(row["scope"])),
                strings(row["allowed_groups"]),
            ),
        )


@dataclass(frozen=True)
class PlannedCase:
    case_id: str
    purpose: str
    owner: str
    status: str
    query: str
    access: RetrievalAccessContext
    relevant_ids: tuple[str, ...]
    tags: tuple[str, ...]
    max_rank: int
    updates: tuple[FixtureDocument, ...]


@dataclass(frozen=True)
class Catalogue:
    dataset_id: str
    version: str
    fingerprint: str
    corpus_fingerprint: str
    snapshot: str
    documents: tuple[FixtureDocument, ...]
    cases: tuple[PlannedCase, ...]

    @classmethod
    def load(cls, path: Path) -> Catalogue:
        return cls.parse(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def parse(cls, value: Json) -> Catalogue:
        row = object_value(value)
        if row.get("schema_version") != 2 or row.get("label_scope") != "knowledge_id":
            raise ValueError("requires catalogue schema 2 with knowledge_id labels")
        if row.get("data_classification") != "synthetic":
            raise ValueError("this evaluation runner accepts synthetic fixtures only")
        if row.get("split") not in {"development", "holdout"}:
            raise ValueError("declare development or holdout split")
        documents = tuple(FixtureDocument.parse(d) for d in array(row["documents"]))
        known = {d.knowledge_id for d in documents}
        if not documents or len(known) != len(documents):
            raise ValueError("corpus must have unique knowledge IDs")
        cases = []
        for raw in array(row["cases"]):
            c = object_value(raw)
            status = text(c["status"])
            if status not in {"draft", "approved"}:
                raise ValueError("case status must be draft or approved")
            relevant = strings(c["relevant_knowledge_ids"])
            if not set(relevant) <= known:
                raise ValueError("expected evidence is absent from the corpus")
            rank = c["max_rank"]
            if type(rank) is not int or not 1 <= rank <= 5:
                raise ValueError("max_rank must be an integer from 1 to 5")
            access = RetrievalAccessContext(text(c["tenant_id"]), strings(c["groups"]))
            updates = tuple(FixtureDocument.parse(d) for d in array(c.get("updates", [])))
            current = {d.knowledge_id: d for d in documents}
            for update in updates:
                if update.knowledge_id not in known:
                    raise ValueError("updates must target known knowledge IDs")
                if current[update.knowledge_id].access.tenant_id != update.access.tenant_id:
                    raise ValueError("a fixture update cannot change tenant")
                if current[update.knowledge_id].source_version == update.source_version:
                    raise ValueError("fixture updates need a new source version")
                current[update.knowledge_id] = update
            if any(not authorized(current[k].access, access) for k in relevant):
                raise ValueError("expected evidence must be authorized in the final fixture state")
            cases.append(
                PlannedCase(
                    text(c["case_id"]),
                    text(c["purpose"]),
                    text(c["owner"]),
                    status,
                    text(c["query"]),
                    access,
                    relevant,
                    strings(c["tags"]),
                    rank,
                    updates,
                )
            )
        if not cases or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("catalogue must have unique case IDs")
        return cls(
            text(row["dataset_id"]),
            text(row["version"]),
            digest(row),
            digest(row["documents"]),
            canonical(row),
            documents,
            tuple(cases),
        )


def authorized(policy: AccessPolicy, access: RetrievalAccessContext) -> bool:
    return policy.tenant_id == access.tenant_id and (
        policy.scope is AccessScope.TENANT
        or policy.scope is AccessScope.RESTRICTED
        and bool(set(policy.allowed_groups) & set(access.groups))
    )
