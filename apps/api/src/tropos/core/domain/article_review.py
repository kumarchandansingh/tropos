"""Review contracts for immutable, evidence-backed Knowledge Article drafts."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256

from tropos.core.domain.knowledge_article import KnowledgeArticleDraft


class ArticleReviewStatus(StrEnum):
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class ArticleReviewDecision(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"


class ConcurrentArticleReviewError(RuntimeError):
    """A review was already created or its version/state changed."""


@dataclass(frozen=True, slots=True)
class ArticleReviewRecord:
    """One immutable article revision and its current human-review outcome."""

    article_id: str
    article_sha256: str
    status: ArticleReviewStatus
    version: int
    submitted_by: str
    submitted_at: str
    updated_at: str
    reviewer_id: str | None = None
    review_note: str | None = None


@dataclass(frozen=True, slots=True)
class ArticleReviewEvent:
    """Append-only state-transition evidence; not an authenticated identity record."""

    event_id: int
    article_id: str
    status: ArticleReviewStatus
    actor_id: str
    recorded_at: str
    note: str | None


def canonical_article_json(draft: KnowledgeArticleDraft) -> str:
    """Serialize the entire typed draft, including citation identities, deterministically."""
    return json.dumps(
        asdict(draft),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def article_sha256(article_json: str) -> str:
    """Bind approval to exact draft content, not to a mutable article title or ID."""
    return sha256(article_json.encode("utf-8")).hexdigest()
