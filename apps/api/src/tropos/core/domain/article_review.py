"""Tenant-scoped immutable article revisions and reviewer decision contracts.

Review actors are caller-supplied local identifiers, not verified principals.
"""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any

from tropos.core.domain.knowledge_article import KnowledgeArticleDraft


class ArticleReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class ArticleReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class ArticleReviewEventType(StrEnum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class ConcurrentArticleReviewError(RuntimeError):
    """A submitted revision or reviewer decision changed concurrently."""


@dataclass(frozen=True, slots=True)
class ArticleReviewRecord:
    """One exact revision within one tenant-scoped logical article."""

    tenant_id: str
    article_id: str
    revision_no: int
    article_sha256: str
    status: ArticleReviewStatus
    submitted_by: str
    submitted_at: str
    updated_at: str
    event_seq: int
    reviewer_id: str | None = None
    review_note: str | None = None


@dataclass(frozen=True, slots=True)
class ArticleReviewEvent:
    tenant_id: str
    article_id: str
    revision_no: int
    event_seq: int
    event_type: ArticleReviewEventType
    actor_id: str
    recorded_at: str
    note: str | None


@dataclass(frozen=True, slots=True)
class ArticleCitation:
    """Structural path to a complete EvidenceRef in an immutable revision."""

    claim_path: str
    ordinal: int
    chunk_id: str
    chunk_content_fingerprint: str


def canonical_article_json(draft: KnowledgeArticleDraft) -> str:
    """Keep exact structured content and all evidence reference fields."""
    return json.dumps(
        asdict(draft),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def article_sha256(article_json: str) -> str:
    """Content identity is independent of mutable article/review status."""
    return sha256(article_json.encode("utf-8")).hexdigest()


def citations_from_payload(payload: dict[str, Any]) -> tuple[ArticleCitation, ...]:
    """Index every nested evidence_ref without discarding its parent claim path."""
    result: list[ArticleCitation] = []

    def collect(node: Any, path: str) -> None:
        if isinstance(node, dict):
            refs: Any = node.get("evidence_refs")
            if refs is not None:
                if not isinstance(refs, list):
                    raise ValueError("Invalid article evidence_refs structure")
                for ordinal, ref in enumerate(refs, start=1):
                    if not isinstance(ref, dict):
                        raise ValueError("Invalid article evidence reference")
                    chunk_id = ref.get("chunk_id")
                    fingerprint = ref.get("content_fingerprint")
                    if (
                        not isinstance(chunk_id, str)
                        or not chunk_id.strip()
                        or not isinstance(fingerprint, str)
                        or not fingerprint.strip()
                    ):
                        raise ValueError("Invalid article evidence reference identity")
                    result.append(
                        ArticleCitation(path, ordinal, chunk_id, fingerprint)
                    )
            for key, value in node.items():
                if key != "evidence_refs":
                    collect(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                collect(value, f"{path}[{index}]")

    collect(payload, "")
    if not result:
        raise ValueError("Submitted Knowledge Article must contain evidence citations")
    return tuple(result)
