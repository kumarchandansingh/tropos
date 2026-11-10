"""Local durable Knowledge Article review store with atomic reviewer decisions."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tropos.core.domain.article_review import (
    ArticleReviewDecision,
    ArticleReviewEvent,
    ArticleReviewRecord,
    ArticleReviewStatus,
    ConcurrentArticleReviewError,
    article_sha256,
    canonical_article_json,
)
from tropos.core.domain.knowledge_article import KnowledgeArticleDraft


class SQLiteArticleReviewStore:
    """Store an immutable submitted draft and append-only human decision events.

    This is a local-operator persistence boundary, NOT an authentication or
    authorization implementation. A future API must derive actor IDs from a
    verified principal rather than accepting caller-asserted identities.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS article_reviews (
                    article_id TEXT PRIMARY KEY,
                    article_json TEXT NOT NULL,
                    article_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    submitted_by TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewer_id TEXT,
                    review_note TEXT
                );

                CREATE TABLE IF NOT EXISTS article_review_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    note TEXT,
                    FOREIGN KEY (article_id) REFERENCES article_reviews(article_id)
                );

                CREATE INDEX IF NOT EXISTS idx_article_review_events_article
                ON article_review_events (article_id, event_id);
                """
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> ArticleReviewRecord:
        return ArticleReviewRecord(
            article_id=str(row["article_id"]),
            article_sha256=str(row["article_sha256"]),
            status=ArticleReviewStatus(row["status"]),
            version=int(row["version"]),
            submitted_by=str(row["submitted_by"]),
            submitted_at=str(row["submitted_at"]),
            updated_at=str(row["updated_at"]),
            reviewer_id=(str(row["reviewer_id"]) if row["reviewer_id"] is not None else None),
            review_note=(str(row["review_note"]) if row["review_note"] is not None else None),
        )

    def submit(
        self,
        *,
        article_id: str,
        draft: KnowledgeArticleDraft,
        submitted_by: str,
    ) -> ArticleReviewRecord:
        """Submit one immutable revision for review; duplicate IDs are rejected."""
        if not article_id.strip() or not submitted_by.strip():
            raise ValueError("article_id and submitted_by must not be blank")
        payload = canonical_article_json(draft)
        digest = article_sha256(payload)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO article_reviews (
                        article_id, article_json, article_sha256, status, version,
                        submitted_by, submitted_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        article_id,
                        payload,
                        digest,
                        ArticleReviewStatus.IN_REVIEW.value,
                        submitted_by,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO article_review_events
                    (article_id, status, actor_id, recorded_at, note)
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (article_id, ArticleReviewStatus.IN_REVIEW.value, submitted_by, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ConcurrentArticleReviewError("Article ID already submitted") from exc
        result = self.get(article_id)
        assert result is not None
        return result

    def decide(
        self,
        *,
        article_id: str,
        reviewer_id: str,
        decision: ArticleReviewDecision,
        expected_version: int,
        note: str = "",
    ) -> ArticleReviewRecord:
        """Approve or request changes exactly once using optimistic concurrency."""
        if not article_id.strip() or not reviewer_id.strip():
            raise ValueError("article_id and reviewer_id must not be blank")
        if expected_version < 1:
            raise ValueError("expected_version must be positive")
        if not isinstance(decision, ArticleReviewDecision):
            raise ValueError("decision must be a valid ArticleReviewDecision")
        if decision is ArticleReviewDecision.REQUEST_CHANGES and not note.strip():
            raise ValueError("Requesting changes requires a review note")

        target = (
            ArticleReviewStatus.APPROVED
            if decision is ArticleReviewDecision.APPROVE
            else ArticleReviewStatus.CHANGES_REQUESTED
        )
        now = datetime.now(UTC).isoformat()
        clean_note = note.strip() or None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version, status, submitted_by, article_json, article_sha256 "
                "FROM article_reviews WHERE article_id = ?",
                (article_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown article ID: {article_id}")
            if article_sha256(str(row["article_json"])) != row["article_sha256"]:
                raise ValueError("Stored Knowledge Article payload failed integrity verification")
            if row["submitted_by"] == reviewer_id:
                raise PermissionError("Submitter cannot review their own draft")
            if (
                int(row["version"]) != expected_version
                or row["status"] != ArticleReviewStatus.IN_REVIEW.value
            ):
                raise ConcurrentArticleReviewError("Review version or status has changed")

            updated = connection.execute(
                """
                UPDATE article_reviews
                SET status = ?, version = version + 1,
                    reviewer_id = ?, review_note = ?, updated_at = ?
                WHERE article_id = ? AND version = ? AND status = ?
                """,
                (
                    target.value,
                    reviewer_id,
                    clean_note,
                    now,
                    article_id,
                    expected_version,
                    ArticleReviewStatus.IN_REVIEW.value,
                ),
            )
            if updated.rowcount != 1:
                raise ConcurrentArticleReviewError("Review was updated concurrently")
            connection.execute(
                """
                INSERT INTO article_review_events
                (article_id, status, actor_id, recorded_at, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (article_id, target.value, reviewer_id, now, clean_note),
            )
        result = self.get(article_id)
        assert result is not None
        return result

    def get(self, article_id: str) -> ArticleReviewRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM article_reviews WHERE article_id = ?",
                (article_id,),
            ).fetchone()
            return self._record(row) if row is not None else None

    def article_payload(self, article_id: str) -> dict[str, Any] | None:
        """Return the frozen structured draft for a future authenticated review UI."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT article_json, article_sha256 FROM article_reviews WHERE article_id = ?",
                (article_id,),
            ).fetchone()
        if row is None:
            return None
        payload = str(row["article_json"])
        if article_sha256(payload) != row["article_sha256"]:
            raise ValueError("Stored Knowledge Article payload failed integrity verification")
        return cast(dict[str, Any], json.loads(payload))

    def events(self, article_id: str) -> tuple[ArticleReviewEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, article_id, status, actor_id, recorded_at, note
                FROM article_review_events
                WHERE article_id = ?
                ORDER BY event_id
                """,
                (article_id,),
            ).fetchall()
        return tuple(
            ArticleReviewEvent(
                event_id=int(row["event_id"]),
                article_id=str(row["article_id"]),
                status=ArticleReviewStatus(row["status"]),
                actor_id=str(row["actor_id"]),
                recorded_at=str(row["recorded_at"]),
                note=str(row["note"]) if row["note"] is not None else None,
            )
            for row in rows
        )
