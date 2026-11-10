"""Durable, deterministic Knowledge Article review tests (no LLM or network)."""

from dataclasses import replace
from pathlib import Path

import pytest

from tropos.core.adapters.persistence.sqlite_article_review import SQLiteArticleReviewStore
from tropos.core.domain.article_review import (
    ArticleReviewDecision,
    ArticleReviewStatus,
    ConcurrentArticleReviewError,
    article_sha256,
    canonical_article_json,
)
from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import (
    ArticleStep,
    ArticleType,
    EvidenceClaim,
    HowToArticle,
    KnowledgeArticleDraft,
)


def _article() -> KnowledgeArticleDraft:
    reference = EvidenceRef(
        chunk_id="chunk-a",
        knowledge_id="knowledge-a",
        source_system="synthetic-manual",
        source_record_id="restart.md",
        source_version="1",
        locator="synthetic-manual:restart.md@v1#chars=0-25",
        content_fingerprint="test-fingerprint",
    )
    claim = EvidenceClaim("Restart service after certificate rotation.", (reference,))
    return KnowledgeArticleDraft(
        title="Recover after certificate rotation",
        article_type=ArticleType.HOW_TO,
        product="Example Service",
        content=HowToArticle(
            purpose=claim,
            prerequisites=(),
            steps=(ArticleStep("Restart the service.", (reference,)),),
            expected_result=claim,
        ),
    )


def test_submit_persists_exact_draft_and_history_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    store = SQLiteArticleReviewStore(path)
    draft = _article()

    submitted = store.submit(article_id="article-a", draft=draft, submitted_by="author-a")

    assert submitted.status is ArticleReviewStatus.IN_REVIEW
    assert submitted.version == 1
    assert submitted.article_sha256 == article_sha256(canonical_article_json(draft))
    assert store.article_payload("article-a") == {
        "title": draft.title,
        "article_type": "how_to",
        "product": "Example Service",
        "module": None,
        "tags": [],
        "content": store.article_payload("article-a")["content"],
    }

    reopened = SQLiteArticleReviewStore(path)
    assert reopened.get("article-a") == submitted
    assert reopened.article_payload("article-a") is not None
    history = reopened.events("article-a")
    assert len(history) == 1
    assert history[0].status is ArticleReviewStatus.IN_REVIEW
    assert history[0].actor_id == "author-a"


def test_reviewer_can_approve_and_audit_is_append_only(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    submitted = store.submit(article_id="article-a", draft=_article(), submitted_by="author-a")

    approved = store.decide(
        article_id="article-a",
        reviewer_id="reviewer-b",
        decision=ArticleReviewDecision.APPROVE,
        expected_version=submitted.version,
        note="Evidence examined.",
    )

    assert approved.status is ArticleReviewStatus.APPROVED
    assert approved.version == 2
    assert approved.article_sha256 == submitted.article_sha256
    assert approved.reviewer_id == "reviewer-b"
    assert [event.status for event in store.events("article-a")] == [
        ArticleReviewStatus.IN_REVIEW,
        ArticleReviewStatus.APPROVED,
    ]
    with pytest.raises(ConcurrentArticleReviewError):
        store.decide(
            article_id="article-a",
            reviewer_id="reviewer-c",
            decision=ArticleReviewDecision.REQUEST_CHANGES,
            expected_version=1,
            note="Another reviewer",
        )
    assert len(store.events("article-a")) == 2


def test_changes_requested_needs_reason_and_is_terminal_for_revision(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    store.submit(article_id="article-a", draft=_article(), submitted_by="author-a")

    with pytest.raises(ValueError, match="requires a review note"):
        store.decide(
            article_id="article-a",
            reviewer_id="reviewer-b",
            decision=ArticleReviewDecision.REQUEST_CHANGES,
            expected_version=1,
        )
    assert len(store.events("article-a")) == 1

    changed = store.decide(
        article_id="article-a",
        reviewer_id="reviewer-b",
        decision=ArticleReviewDecision.REQUEST_CHANGES,
        expected_version=1,
        note="Needs a validated rollback step.",
    )
    assert changed.status is ArticleReviewStatus.CHANGES_REQUESTED
    assert changed.review_note == "Needs a validated rollback step."
    with pytest.raises(ConcurrentArticleReviewError):
        store.decide(
            article_id="article-a",
            reviewer_id="reviewer-b",
            decision=ArticleReviewDecision.APPROVE,
            expected_version=2,
        )


def test_submitter_cannot_approve_their_own_draft(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    store.submit(article_id="article-a", draft=_article(), submitted_by="author-a")
    with pytest.raises(PermissionError, match="Submitter cannot review"):
        store.decide(
            article_id="article-a",
            reviewer_id="author-a",
            decision=ArticleReviewDecision.APPROVE,
            expected_version=1,
        )
    assert store.get("article-a").status is ArticleReviewStatus.IN_REVIEW  # type: ignore[union-attr]


def test_duplicate_submission_cannot_silently_replace_approved_evidence(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    draft = _article()
    original = store.submit(article_id="article-a", draft=draft, submitted_by="author-a")
    changed = replace(draft, title="Different text")

    with pytest.raises(ConcurrentArticleReviewError, match="already submitted"):
        store.submit(article_id="article-a", draft=changed, submitted_by="author-a")

    assert store.get("article-a") == original
    assert store.article_payload("article-a")["title"] == draft.title  # type: ignore[index]
    assert article_sha256(canonical_article_json(draft)) != article_sha256(
        canonical_article_json(changed)
    )


def test_fails_closed_if_stored_draft_was_modified(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "reviews.db"
    store = SQLiteArticleReviewStore(path)
    store.submit(article_id="article-a", draft=_article(), submitted_by="author-a")

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE article_reviews SET article_json = ? WHERE article_id = ?",
            ('{"title":"tampered"}', "article-a"),
        )

    with pytest.raises(ValueError, match="integrity verification"):
        store.article_payload("article-a")


def test_rejects_invalid_or_stale_decisions(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    store.submit(article_id="article-a", draft=_article(), submitted_by="author-a")

    with pytest.raises(ConcurrentArticleReviewError):
        store.decide(
            article_id="article-a",
            reviewer_id="reviewer-b",
            decision=ArticleReviewDecision.APPROVE,
            expected_version=2,
        )
    with pytest.raises(ValueError, match="valid ArticleReviewDecision"):
        store.decide(
            article_id="article-a",
            reviewer_id="reviewer-b",
            decision="approve",  # type: ignore[arg-type]
            expected_version=1,
        )
    with pytest.raises(KeyError, match="Unknown article"):
        store.decide(
            article_id="missing",
            reviewer_id="reviewer-b",
            decision=ArticleReviewDecision.APPROVE,
            expected_version=1,
        )
