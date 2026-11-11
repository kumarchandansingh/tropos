"""End-to-end local review-state tests, independent of an LLM or network."""

import sqlite3
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from tropos.core.adapters.persistence.sqlite_article_review import SQLiteArticleReviewStore
from tropos.core.domain.article_review import (
    ArticleReviewDecision,
    ArticleReviewEventType,
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

_TENANT = "tenant-a"
_ARTICLE = "article-a"


def _article(title: str = "Recover after certificate rotation") -> KnowledgeArticleDraft:
    reference = EvidenceRef(
        chunk_id="chunk-a",
        knowledge_id="knowledge-a",
        source_system="synthetic-manual",
        source_record_id="restart.md",
        source_version="1",
        locator="synthetic-manual:restart.md@v1#chars=0-25",
        content_fingerprint=sha256(b"Restart the service.").hexdigest(),
    )
    claim = EvidenceClaim("Restart service after certificate rotation.", (reference,))
    return KnowledgeArticleDraft(
        title=title,
        article_type=ArticleType.HOW_TO,
        product="Example Service",
        content=HowToArticle(
            purpose=claim,
            prerequisites=(),
            steps=(ArticleStep("Restart the service.", (reference,)),),
            expected_result=claim,
        ),
    )


def _submit(
    store: SQLiteArticleReviewStore,
    *,
    tenant_id: str = _TENANT,
    article_id: str = _ARTICLE,
    title: str = "Recover after certificate rotation",
    expected_previous_revision: int = 0,
    submitted_by: str = "author-a",
) -> None:
    store.submit(
        tenant_id=tenant_id,
        article_id=article_id,
        draft=_article(title),
        submitted_by=submitted_by,
        expected_previous_revision=expected_previous_revision,
    )


def _decide(
    store: SQLiteArticleReviewStore,
    *,
    decision: ArticleReviewDecision = ArticleReviewDecision.APPROVE,
    tenant_id: str = _TENANT,
    article_id: str = _ARTICLE,
    revision_no: int = 1,
    reviewer_id: str = "reviewer-b",
    expected_event_seq: int = 1,
    note: str = "",
) -> None:
    store.decide(
        tenant_id=tenant_id,
        article_id=article_id,
        revision_no=revision_no,
        reviewer_id=reviewer_id,
        decision=decision,
        expected_event_seq=expected_event_seq,
        note=note,
    )


def test_submission_persists_immutable_revision_citations_and_history(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    store = SQLiteArticleReviewStore(path)
    draft = _article()
    record = store.submit(
        tenant_id=_TENANT, article_id=_ARTICLE, draft=draft, submitted_by="author-a"
    )

    assert record.tenant_id == _TENANT
    assert record.article_id == _ARTICLE
    assert record.revision_no == 1
    assert record.event_seq == 1
    assert record.status is ArticleReviewStatus.IN_REVIEW
    assert record.article_sha256 == article_sha256(canonical_article_json(draft))
    assert record.reviewer_id is None

    reopened = SQLiteArticleReviewStore(path)
    assert reopened.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1) == record
    payload = reopened.article_payload(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)
    assert payload is not None
    assert payload["title"] == draft.title
    assert payload["article_type"] == "how_to"
    assert payload["product"] == "Example Service"
    citations = reopened.citations(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)
    assert {c.claim_path for c in citations} == {
        "content.purpose",
        "content.steps[0]",
        "content.expected_result",
    }
    assert all(c.chunk_id == "chunk-a" for c in citations)
    assert all(c.chunk_content_fingerprint == sha256(b"Restart the service.").hexdigest()
               for c in citations)
    assert [event.event_type for event in reopened.events(
        tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1
    )] == [ArticleReviewEventType.SUBMIT]


def test_decision_is_atomic_terminal_and_auditable(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    _submit(store)
    _decide(store, note="Citations checked")

    approved = store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)
    assert approved is not None
    assert approved.status is ArticleReviewStatus.APPROVED
    assert approved.event_seq == 2
    assert approved.reviewer_id == "reviewer-b"
    assert approved.review_note == "Citations checked"
    assert [e.event_type for e in store.events(
        tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1
    )] == [ArticleReviewEventType.SUBMIT, ArticleReviewEventType.APPROVE]

    with pytest.raises(ConcurrentArticleReviewError):
        _decide(store, decision=ArticleReviewDecision.REQUEST_CHANGES, note="Too late")
    with pytest.raises(ConcurrentArticleReviewError):
        _decide(store, expected_event_seq=2)
    assert len(store.events(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)) == 2


def test_request_changes_then_new_revision_preserves_prior_review(
    tmp_path: Path,
) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    _submit(store)
    with pytest.raises(ValueError, match="requires a review note"):
        _decide(store, decision=ArticleReviewDecision.REQUEST_CHANGES, note=" ")

    _decide(
        store,
        decision=ArticleReviewDecision.REQUEST_CHANGES,
        note="Missing validated rollback step.",
    )
    rejected = store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)
    assert rejected is not None
    assert rejected.status is ArticleReviewStatus.CHANGES_REQUESTED
    assert rejected.review_note == "Missing validated rollback step."

    revised_draft = _article("Recover safely after certificate rotation")
    new_revision = store.submit(
        tenant_id=_TENANT,
        article_id=_ARTICLE,
        draft=revised_draft,
        submitted_by="author-a",
        expected_previous_revision=1,
    )
    assert new_revision.revision_no == 2
    assert new_revision.status is ArticleReviewStatus.IN_REVIEW
    assert new_revision.article_sha256 != rejected.article_sha256
    assert store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1) == rejected
    assert store.get(tenant_id=_TENANT, article_id=_ARTICLE) == new_revision
    original_payload = store.article_payload(
        tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1
    )
    assert original_payload is not None
    assert original_payload["title"] == "Recover after certificate rotation"
    assert [r.revision_no for r in store.list_revisions(
        tenant_id=_TENANT, article_id=_ARTICLE
    )] == [1, 2]

    with pytest.raises(ConcurrentArticleReviewError, match="under review"):
        store.submit(
            tenant_id=_TENANT,
            article_id=_ARTICLE,
            draft=_article("Third edit"),
            submitted_by="author-a",
            expected_previous_revision=2,
        )
    _decide(store, revision_no=2, reviewer_id="reviewer-c")
    second = store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=2)
    assert second is not None
    assert second.status is ArticleReviewStatus.APPROVED
    assert store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1) == rejected


def test_approved_revision_does_not_approve_later_revision(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    _submit(store)
    _decide(store)
    first = store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)
    assert first is not None

    store.submit(
        tenant_id=_TENANT,
        article_id=_ARTICLE,
        draft=_article("Additional guidance"),
        submitted_by="author-a",
        expected_previous_revision=1,
    )
    second = store.get(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=2)
    assert first.status is ArticleReviewStatus.APPROVED
    assert second is not None
    assert second.status is ArticleReviewStatus.IN_REVIEW
    assert first.article_sha256 != second.article_sha256


def test_tenant_keys_are_isolated_even_with_same_article_id(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    _submit(store)
    _submit(store, tenant_id="tenant-b", title="Tenant B recovery")

    assert store.get(tenant_id="tenant-b", article_id=_ARTICLE) is not None
    assert store.get(tenant_id="tenant-a", article_id=_ARTICLE) is not None
    assert store.get(tenant_id="tenant-c", article_id=_ARTICLE) is None
    assert store.article_payload(
        tenant_id="tenant-a", article_id=_ARTICLE, revision_no=1
    ) != store.article_payload(
        tenant_id="tenant-b", article_id=_ARTICLE, revision_no=1
    )
    _decide(store, tenant_id="tenant-b")
    tenant_a = store.get(tenant_id="tenant-a", article_id=_ARTICLE)
    tenant_b = store.get(tenant_id="tenant-b", article_id=_ARTICLE)
    assert tenant_a is not None and tenant_a.status is ArticleReviewStatus.IN_REVIEW
    assert tenant_b is not None and tenant_b.status is ArticleReviewStatus.APPROVED


def test_separation_of_duties_and_stale_submission_guard(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    _submit(store)
    with pytest.raises(PermissionError, match="Submitter cannot review"):
        _decide(store, reviewer_id="author-a")
    with pytest.raises(ConcurrentArticleReviewError, match="changed"):
        _submit(store)
    with pytest.raises(ConcurrentArticleReviewError, match="changed"):
        store.submit(
            tenant_id=_TENANT,
            article_id=_ARTICLE,
            draft=_article("Another draft"),
            submitted_by="author-a",
            expected_previous_revision=3,
        )
    with pytest.raises(ValueError, match="valid ArticleReviewDecision"):
        store.decide(
            tenant_id=_TENANT,
            article_id=_ARTICLE,
            revision_no=1,
            reviewer_id="reviewer-b",
            decision="APPROVE",  # type: ignore[arg-type]
            expected_event_seq=1,
        )
    with pytest.raises(KeyError, match="Unknown article revision"):
        _decide(store, article_id="not-found")


def test_sql_rejects_direct_mutation_of_revisions_citations_and_events(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    store = SQLiteArticleReviewStore(path)
    _submit(store)

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE article_revisions SET article_json = ? WHERE article_id = ?",
                ('{"title":"tampered"}', _ARTICLE),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM article_citations WHERE article_id = ?", (_ARTICLE,))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE review_events SET note = 'altered' WHERE article_id = ?", (_ARTICLE,))
        with pytest.raises(sqlite3.IntegrityError, match="status requires review event"):
            db.execute(
                "UPDATE article_revisions SET status = 'APPROVED' WHERE article_id = ?",
                (_ARTICLE,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="invalid review transition"):
            db.execute(
                """INSERT INTO review_events (
                tenant_id, article_id, revision_no, event_seq, event_type,
                actor_id, note, created_at
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (_TENANT, _ARTICLE, 1, 2, "APPROVE", "author-a", None, "now"),
            )


def test_tampered_citation_or_payload_blocks_approval(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    store = SQLiteArticleReviewStore(path)
    _submit(store)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER article_citation_no_update")
        db.execute(
            "UPDATE article_citations SET chunk_id = 'forged' WHERE article_id = ?",
            (_ARTICLE,),
        )
    with pytest.raises(ValueError, match="citations failed integrity"):
        _decide(store)

    other_path = tmp_path / "reviews-other.db"
    second = SQLiteArticleReviewStore(other_path)
    _submit(second)
    with sqlite3.connect(other_path) as db:
        db.execute("DROP TRIGGER article_revision_payload_immutable")
        db.execute(
            "UPDATE article_revisions SET article_json = ? WHERE article_id = ?",
            ('{"title":"forged"}', _ARTICLE),
        )
    with pytest.raises(ValueError, match="payload failed integrity"):
        second.article_payload(tenant_id=_TENANT, article_id=_ARTICLE, revision_no=1)
    with pytest.raises(ValueError, match="payload failed integrity"):
        _decide(second)


def test_logical_identity_cannot_change_article_type_or_product(tmp_path: Path) -> None:
    store = SQLiteArticleReviewStore(tmp_path / "reviews.db")
    _submit(store)
    _decide(store)
    edited = replace(_article("Edited article"), product="Other Product")
    with pytest.raises(ValueError, match="logical identity"):
        store.submit(
            tenant_id=_TENANT,
            article_id=_ARTICLE,
            draft=edited,
            submitted_by="author-a",
            expected_previous_revision=1,
        )
    assert len(store.list_revisions(tenant_id=_TENANT, article_id=_ARTICLE)) == 1
