"""Executable tests for the DESIGN-ONLY target SQL data model.

These tests validate reference schema integrity, not deployed Tropos behavior.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

_SCHEMA = (
    Path(__file__).resolve().parents[5]
    / "docs"
    / "architecture"
    / "data-model"
    / "target_schema.sql"
)
_NOW = "2026-11-10T00:00:00+00:00"


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA.read_text(encoding="utf-8"))
    try:
        yield connection
    finally:
        connection.close()


def _seed(db: sqlite3.Connection, tenant: str = "tenant-a") -> dict[str, str]:
    ids = {
        "tenant": tenant,
        "knowledge": f"knowledge-{tenant}",
        "capture": f"capture-{tenant}",
        "chunk": f"chunk-{tenant}",
        "run": f"run-{tenant}",
        "set": f"evidence-{tenant}",
        "article": f"article-{tenant}",
        "publication": f"publication-{tenant}",
    }
    db.execute("INSERT INTO tenants (tenant_id) VALUES (?)", (tenant,))
    for actor in ("author", "reviewer", "publisher"):
        db.execute(
            "INSERT INTO principals VALUES (?,?,?)", (tenant, actor, "ACTIVE")
        )
    db.execute(
        "INSERT INTO knowledge_items VALUES (?,?,?,?)",
        (tenant, ids["knowledge"], "synthetic-manual", f"{tenant}-document.md"),
    )
    db.execute(
        "INSERT INTO source_captures VALUES (?,?,?,?,?,?,?,?,?)",
        (
            tenant,
            ids["capture"],
            ids["knowledge"],
            "1",
            "text/markdown",
            b"abc",
            "1" * 64,
            "2" * 64,
            _NOW,
        ),
    )
    db.execute(
        "INSERT INTO content_versions VALUES (?,?,?,?,?,?,?,?)",
        (tenant, ids["knowledge"], "a" * 64, "normalizer-v1", ids["capture"],
         "Demo", "abc", _NOW),
    )
    db.execute(
        "INSERT INTO access_policy_versions VALUES (?,?,?,?,?,?)",
        (tenant, ids["knowledge"], 1, "tenant", "b" * 64, _NOW),
    )
    db.execute(
        "INSERT INTO knowledge_heads VALUES (?,?,?,?,?,?,?)",
        (tenant, ids["knowledge"], "a" * 64, "normalizer-v1", 1, "ACTIVE", _NOW),
    )
    db.execute(
        "INSERT INTO knowledge_chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tenant, ids["chunk"], ids["knowledge"], "a" * 64,
         "normalizer-v1", "chunker-v1", 0, 0, 3, "abc", "c" * 64),
    )
    db.execute(
        "INSERT INTO resolve_runs VALUES (?,?,?,?,?,?,?,?)",
        (tenant, ids["run"], "author", "3" * 64, "ANSWERED",
         f"trace-{tenant}", _NOW, _NOW),
    )
    db.execute(
        "INSERT INTO evidence_sets VALUES (?,?,?,?,?)",
        (tenant, ids["set"], ids["run"], "bm25-v1", _NOW),
    )
    db.execute(
        "INSERT INTO evidence_members VALUES (?,?,?,?,?,?,?)",
        (tenant, ids["set"], 1, "E1", ids["chunk"], "c" * 64, 0.5),
    )
    db.execute(
        "INSERT INTO knowledge_articles VALUES (?,?,?,?,?)",
        (tenant, ids["article"], "how_to", "Example Product", _NOW),
    )
    db.execute(
        "INSERT INTO article_revisions VALUES (?,?,?,?,?,?,?,?,?)",
        (tenant, ids["article"], 1, '{"title":"Synthetic article"}',
         "d" * 64, "DRAFT", "author", ids["set"], _NOW),
    )
    db.execute(
        "INSERT INTO article_citations VALUES (?,?,?,?,?,?,?)",
        (tenant, ids["article"], 1, "content.steps[0]", 1, ids["chunk"], "c" * 64),
    )
    return ids


def _event(
    db: sqlite3.Connection,
    ids: dict[str, str],
    seq: int,
    kind: str,
    actor: str,
    note: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO review_events VALUES (?,?,?,?,?,?,?,?)",
        (ids["tenant"], ids["article"], 1, seq, kind, actor, note, _NOW),
    )


def _approve(db: sqlite3.Connection, ids: dict[str, str]) -> None:
    _event(db, ids, 1, "SUBMIT", "author")
    _event(db, ids, 2, "APPROVE", "reviewer", "Sources verified")


def _publish(db: sqlite3.Connection, ids: dict[str, str]) -> None:
    db.execute(
        "INSERT INTO publications VALUES (?,?,?,?,?,?,?,?)",
        (ids["tenant"], ids["publication"], ids["article"], 1,
         "PUBLISHED", "publisher", _NOW, None),
    )


def test_reference_schema_compiles_and_enables_foreign_keys(
    db: sqlite3.Connection,
) -> None:
    assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == []
    names = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"knowledge_heads", "knowledge_chunks", "article_revisions",
            "review_events", "publication_events", "evidence_members"} <= names


def test_tenant_and_evidence_fingerprint_integrity(db: sqlite3.Connection) -> None:
    ids_a = _seed(db, "tenant-a")
    ids_b = _seed(db, "tenant-b")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO evidence_members VALUES (?,?,?,?,?,?,?)",
            ("tenant-a", ids_a["set"], 2, "E2", ids_b["chunk"], "c" * 64, 0.3),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO article_citations VALUES (?,?,?,?,?,?,?)",
            ("tenant-a", ids_a["article"], 1, "content.steps[1]", 1,
             ids_a["chunk"], "f" * 64),
        )


def test_review_is_ordered_auditable_and_separates_author_reviewer(
    db: sqlite3.Connection,
) -> None:
    ids = _seed(db)
    with pytest.raises(sqlite3.IntegrityError, match="invalid review transition"):
        _event(db, ids, 1, "APPROVE", "reviewer")
    _event(db, ids, 1, "SUBMIT", "author")
    assert db.execute(
        "SELECT status FROM article_revisions WHERE tenant_id=? AND article_id=?",
        (ids["tenant"], ids["article"]),
    ).fetchone() == ("IN_REVIEW",)
    with pytest.raises(sqlite3.IntegrityError, match="separation of duties"):
        _event(db, ids, 2, "APPROVE", "author")
    with pytest.raises(sqlite3.IntegrityError, match="sequential"):
        _event(db, ids, 3, "APPROVE", "reviewer")
    _event(db, ids, 2, "APPROVE", "reviewer")
    assert db.execute(
        "SELECT status FROM article_revisions WHERE tenant_id=? AND article_id=?",
        (ids["tenant"], ids["article"]),
    ).fetchone() == ("APPROVED",)
    with pytest.raises(sqlite3.IntegrityError, match="invalid review transition"):
        _event(db, ids, 3, "REQUEST_CHANGES", "reviewer", "Too late")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute(
            "UPDATE review_events SET note='changed' WHERE event_seq=2"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute(
            "UPDATE article_revisions SET article_json='{}' WHERE article_id=?",
            (ids["article"],),
        )


def test_changes_requested_must_have_explanation(db: sqlite3.Connection) -> None:
    ids = _seed(db)
    _event(db, ids, 1, "SUBMIT", "author")
    with pytest.raises(sqlite3.IntegrityError, match="requires a reason"):
        _event(db, ids, 2, "REQUEST_CHANGES", "reviewer", " ")
    _event(db, ids, 2, "REQUEST_CHANGES", "reviewer", "Add rollback evidence")
    assert db.execute(
        "SELECT status FROM article_revisions WHERE article_id=?",
        (ids["article"],),
    ).fetchone() == ("CHANGES_REQUESTED",)
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        db.execute(
            "INSERT INTO article_citations VALUES (?,?,?,?,?,?,?)",
            (ids["tenant"], ids["article"], 1, "content.extra", 1, ids["chunk"], "c" * 64),
        )


def test_publication_requires_approval_and_current_evidence(
    db: sqlite3.Connection,
) -> None:
    ids = _seed(db)
    with pytest.raises(sqlite3.IntegrityError, match="approved revision"):
        _publish(db, ids)
    _approve(db, ids)
    _publish(db, ids)
    assert db.execute(
        "SELECT COUNT(*) FROM currently_eligible_publications"
    ).fetchone() == (1,)
    assert db.execute(
        "SELECT event_type FROM publication_events WHERE publication_id=?",
        (ids["publication"],),
    ).fetchall() == [("PUBLISH",)]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO publications VALUES (?,?,?,?,?,?,?,?)",
            (ids["tenant"], "duplicate-publication", ids["article"], 1,
             "PUBLISHED", "publisher", _NOW, None),
        )
    db.execute(
        "INSERT INTO publication_events VALUES (?,?,?,?,?,?)",
        (ids["tenant"], ids["publication"], 2, "REVOKE", "publisher", _NOW),
    )
    assert db.execute(
        "SELECT state FROM publications WHERE publication_id=?",
        (ids["publication"],),
    ).fetchone() == ("REVOKED",)
    assert db.execute(
        "SELECT COUNT(*) FROM currently_eligible_publications"
    ).fetchone() == (0,)


@pytest.mark.parametrize("source_change", ["deleted", "unresolved", "new_version"])
def test_publication_fails_closed_after_source_change(
    db: sqlite3.Connection, source_change: str
) -> None:
    ids = _seed(db)
    _approve(db, ids)
    _publish(db, ids)

    if source_change == "deleted":
        db.execute(
            "UPDATE knowledge_heads SET lifecycle_status='DELETED' WHERE knowledge_id=?",
            (ids["knowledge"],),
        )
    elif source_change == "unresolved":
        db.execute(
            "INSERT INTO access_policy_versions VALUES (?,?,?,?,?,?)",
            (ids["tenant"], ids["knowledge"], 2, "unresolved", "e" * 64, _NOW),
        )
        db.execute(
            "UPDATE knowledge_heads SET current_policy_version=2 WHERE knowledge_id=?",
            (ids["knowledge"],),
        )
    else:
        db.execute(
            "INSERT INTO content_versions VALUES (?,?,?,?,?,?,?,?)",
            (ids["tenant"], ids["knowledge"], "f" * 64, "normalizer-v1",
             ids["capture"], "New version", "different", _NOW),
        )
        db.execute(
            "UPDATE knowledge_heads SET current_content_fingerprint=? WHERE knowledge_id=?",
            ("f" * 64, ids["knowledge"]),
        )

    # Previously published row remains in the audit trail but stops being eligible.
    assert db.execute(
        "SELECT COUNT(*) FROM publications WHERE state='PUBLISHED'"
    ).fetchone() == (1,)
    assert db.execute(
        "SELECT COUNT(*) FROM currently_eligible_publications"
    ).fetchone() == (0,)

    # New publication attempts on the stale revision fail.
    with pytest.raises(sqlite3.IntegrityError, match="stale or ineligible"):
        db.execute(
            "INSERT INTO publications VALUES (?,?,?,?,?,?,?,?)",
            (ids["tenant"], "publication-later", ids["article"], 1,
             "PUBLISHED", "publisher", _NOW, None),
        )


def test_direct_status_forgery_is_rejected(db: sqlite3.Connection) -> None:
    ids = _seed(db)
    with pytest.raises(sqlite3.IntegrityError, match="recorded event"):
        db.execute(
            "UPDATE article_revisions SET status='APPROVED' WHERE article_id=?",
            (ids["article"],),
        )
