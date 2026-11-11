"""Tenant-scoped SQLite Knowledge Article revision/review store.

This is a local-only persistence and workflow contract, not an authenticated
network API. Never use caller-provided actors/tenants as verified principals.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tropos.core.domain.article_review import (
    ArticleCitation,
    ArticleReviewDecision,
    ArticleReviewEvent,
    ArticleReviewEventType,
    ArticleReviewRecord,
    ArticleReviewStatus,
    ConcurrentArticleReviewError,
    article_sha256,
    canonical_article_json,
    citations_from_payload,
)
from tropos.core.domain.knowledge_article import KnowledgeArticleDraft


class SQLiteArticleReviewStore:
    """Local revisions match DATA-101 logical article/revision/event/citation keys.

    The production target additionally requires authenticated tenant, reviewer
    and permission controls, and source-chunk foreign-key validation.
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
        with self._connect() as db:
            legacy = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'article_reviews'"
            ).fetchone()
            if legacy is not None:
                raise RuntimeError(
                    "Legacy article_reviews data requires explicit tenant and revision migration; "
                    "refusing to reinterpret unscoped historical approvals"
                )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY CHECK (length(trim(tenant_id)) > 0)
                );

                CREATE TABLE IF NOT EXISTS knowledge_articles (
                    tenant_id TEXT NOT NULL,
                    article_id TEXT NOT NULL,
                    article_type TEXT NOT NULL CHECK (
                        article_type IN ('troubleshooting','how_to','faq')
                    ),
                    product TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, article_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );

                CREATE TABLE IF NOT EXISTS article_revisions (
                    tenant_id TEXT NOT NULL,
                    article_id TEXT NOT NULL,
                    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
                    article_json TEXT NOT NULL CHECK (json_valid(article_json)),
                    article_sha256 TEXT NOT NULL CHECK (length(article_sha256) = 64),
                    status TEXT NOT NULL CHECK (
                        status IN ('DRAFT','IN_REVIEW','APPROVED','CHANGES_REQUESTED')
                    ),
                    submitted_by TEXT NOT NULL,
                    source_evidence_set_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, article_id, revision_no),
                    FOREIGN KEY (tenant_id, article_id)
                        REFERENCES knowledge_articles(tenant_id, article_id)
                );

                CREATE TABLE IF NOT EXISTS article_citations (
                    tenant_id TEXT NOT NULL,
                    article_id TEXT NOT NULL,
                    revision_no INTEGER NOT NULL,
                    claim_path TEXT NOT NULL,
                    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
                    chunk_id TEXT NOT NULL,
                    chunk_content_fingerprint TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, article_id, revision_no, claim_path, ordinal),
                    FOREIGN KEY (tenant_id, article_id, revision_no)
                        REFERENCES article_revisions(tenant_id, article_id, revision_no)
                );

                CREATE TABLE IF NOT EXISTS review_events (
                    tenant_id TEXT NOT NULL,
                    article_id TEXT NOT NULL,
                    revision_no INTEGER NOT NULL,
                    event_seq INTEGER NOT NULL CHECK (event_seq > 0),
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('SUBMIT','APPROVE','REQUEST_CHANGES')
                    ),
                    actor_id TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, article_id, revision_no, event_seq),
                    FOREIGN KEY (tenant_id, article_id, revision_no)
                        REFERENCES article_revisions(tenant_id, article_id, revision_no)
                );

                CREATE INDEX IF NOT EXISTS idx_article_review_queue
                    ON article_revisions(tenant_id, status, created_at);
                CREATE INDEX IF NOT EXISTS idx_article_citation_chunk
                    ON article_citations(tenant_id, chunk_id);

                CREATE TRIGGER IF NOT EXISTS article_revision_payload_immutable
                BEFORE UPDATE OF article_json, article_sha256, submitted_by,
                    source_evidence_set_id, created_at
                ON article_revisions
                BEGIN SELECT RAISE(ABORT, 'article revision payload is immutable'); END;

                CREATE TRIGGER IF NOT EXISTS article_revision_no_delete
                BEFORE DELETE ON article_revisions
                BEGIN SELECT RAISE(ABORT, 'article revision is immutable'); END;

                CREATE TRIGGER IF NOT EXISTS article_citation_insert_before_submission
                BEFORE INSERT ON article_citations
                WHEN NOT EXISTS (
                    SELECT 1 FROM article_revisions r
                    WHERE r.tenant_id = NEW.tenant_id
                      AND r.article_id = NEW.article_id
                      AND r.revision_no = NEW.revision_no AND r.status = 'DRAFT'
                )
                BEGIN SELECT RAISE(ABORT, 'citations frozen after submission'); END;

                CREATE TRIGGER IF NOT EXISTS article_citation_no_update
                BEFORE UPDATE ON article_citations
                BEGIN SELECT RAISE(ABORT, 'article citations are immutable'); END;

                CREATE TRIGGER IF NOT EXISTS article_citation_no_delete
                BEFORE DELETE ON article_citations
                BEGIN SELECT RAISE(ABORT, 'article citations are immutable'); END;

                CREATE TRIGGER IF NOT EXISTS review_event_no_update
                BEFORE UPDATE ON review_events
                BEGIN SELECT RAISE(ABORT, 'review events are immutable'); END;

                CREATE TRIGGER IF NOT EXISTS review_event_no_delete
                BEFORE DELETE ON review_events
                BEGIN SELECT RAISE(ABORT, 'review events are immutable'); END;

                CREATE TRIGGER IF NOT EXISTS article_review_event_transition
                BEFORE INSERT ON review_events
                BEGIN
                    SELECT CASE WHEN NEW.event_seq != (
                        SELECT COALESCE(MAX(event_seq), 0) + 1 FROM review_events
                        WHERE tenant_id = NEW.tenant_id AND article_id = NEW.article_id
                          AND revision_no = NEW.revision_no
                    ) THEN RAISE(ABORT, 'review event sequence mismatch') END;

                    SELECT CASE WHEN NOT EXISTS (
                        SELECT 1 FROM article_revisions r
                        WHERE r.tenant_id = NEW.tenant_id
                          AND r.article_id = NEW.article_id
                          AND r.revision_no = NEW.revision_no
                          AND (
                              (NEW.event_type = 'SUBMIT' AND r.status = 'DRAFT'
                               AND NEW.actor_id = r.submitted_by)
                              OR
                              (NEW.event_type IN ('APPROVE','REQUEST_CHANGES')
                               AND r.status = 'IN_REVIEW'
                               AND NEW.actor_id != r.submitted_by)
                          )
                    ) THEN RAISE(ABORT, 'invalid review transition or self-review') END;

                    SELECT CASE WHEN NEW.event_type = 'REQUEST_CHANGES'
                        AND length(trim(COALESCE(NEW.note, ''))) = 0
                        THEN RAISE(ABORT, 'request changes requires a reason') END;
                END;

                CREATE TRIGGER IF NOT EXISTS article_revision_status_from_event
                BEFORE UPDATE OF status ON article_revisions
                WHEN NOT EXISTS (
                    SELECT 1 FROM review_events e
                    WHERE e.tenant_id = NEW.tenant_id
                      AND e.article_id = NEW.article_id
                      AND e.revision_no = NEW.revision_no
                      AND e.event_seq = (
                          SELECT MAX(x.event_seq) FROM review_events x
                          WHERE x.tenant_id = e.tenant_id
                            AND x.article_id = e.article_id
                            AND x.revision_no = e.revision_no
                      )
                      AND NEW.status = CASE e.event_type
                          WHEN 'SUBMIT' THEN 'IN_REVIEW'
                          WHEN 'APPROVE' THEN 'APPROVED'
                          ELSE 'CHANGES_REQUESTED'
                      END
                )
                BEGIN SELECT RAISE(ABORT, 'status requires review event'); END;

                CREATE TRIGGER IF NOT EXISTS article_review_event_applies_status
                AFTER INSERT ON review_events
                BEGIN
                    UPDATE article_revisions
                    SET status = CASE NEW.event_type
                        WHEN 'SUBMIT' THEN 'IN_REVIEW'
                        WHEN 'APPROVE' THEN 'APPROVED'
                        ELSE 'CHANGES_REQUESTED'
                    END, updated_at = NEW.created_at
                    WHERE tenant_id = NEW.tenant_id AND article_id = NEW.article_id
                      AND revision_no = NEW.revision_no;
                END;
                """
            )

    @staticmethod
    def _required(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be blank")

    @staticmethod
    def _read_revision(
        db: sqlite3.Connection,
        tenant_id: str,
        article_id: str,
        revision_no: int | None,
    ) -> sqlite3.Row | None:
        if revision_no is None:
            return db.execute(
                """
                SELECT * FROM article_revisions
                WHERE tenant_id = ? AND article_id = ?
                ORDER BY revision_no DESC LIMIT 1
                """,
                (tenant_id, article_id),
            ).fetchone()
        return db.execute(
            """
            SELECT * FROM article_revisions
            WHERE tenant_id = ? AND article_id = ? AND revision_no = ?
            """,
            (tenant_id, article_id, revision_no),
        ).fetchone()

    @staticmethod
    def _verified_payload(
        db: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        payload_text = str(row["article_json"])
        if article_sha256(payload_text) != str(row["article_sha256"]):
            raise ValueError("Stored Knowledge Article payload failed integrity verification")
        payload = cast(dict[str, Any], json.loads(payload_text))
        expected = {
            (c.claim_path, c.ordinal, c.chunk_id, c.chunk_content_fingerprint)
            for c in citations_from_payload(payload)
        }
        citations = db.execute(
            """
            SELECT claim_path, ordinal, chunk_id, chunk_content_fingerprint
            FROM article_citations
            WHERE tenant_id = ? AND article_id = ? AND revision_no = ?
            """,
            (row["tenant_id"], row["article_id"], row["revision_no"]),
        ).fetchall()
        actual = {(str(c[0]), int(c[1]), str(c[2]), str(c[3])) for c in citations}
        if actual != expected or len(citations) != len(expected):
            raise ValueError("Stored Knowledge Article citations failed integrity verification")
        return payload

    @staticmethod
    def _to_record(db: sqlite3.Connection, row: sqlite3.Row) -> ArticleReviewRecord:
        event = db.execute(
            """
            SELECT event_seq, event_type, actor_id, note
            FROM review_events
            WHERE tenant_id = ? AND article_id = ? AND revision_no = ?
            ORDER BY event_seq DESC LIMIT 1
            """,
            (row["tenant_id"], row["article_id"], row["revision_no"]),
        ).fetchone()
        if event is None:
            raise ValueError("Submitted revision is missing a review event")
        reviewer = str(event["actor_id"]) if event["event_type"] != "SUBMIT" else None
        note = str(event["note"]) if event["note"] is not None else None
        return ArticleReviewRecord(
            tenant_id=str(row["tenant_id"]),
            article_id=str(row["article_id"]),
            revision_no=int(row["revision_no"]),
            article_sha256=str(row["article_sha256"]),
            status=ArticleReviewStatus(row["status"]),
            submitted_by=str(row["submitted_by"]),
            submitted_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            event_seq=int(event["event_seq"]),
            reviewer_id=reviewer,
            review_note=note,
        )

    def submit(
        self,
        *,
        tenant_id: str,
        article_id: str,
        draft: KnowledgeArticleDraft,
        submitted_by: str,
        expected_previous_revision: int = 0,
        source_evidence_set_id: str | None = None,
    ) -> ArticleReviewRecord:
        """Create revision 1 or a *new* revision after a terminal review outcome."""
        for field, value in (
            ("tenant_id", tenant_id),
            ("article_id", article_id),
            ("submitted_by", submitted_by),
        ):
            self._required(value, field)
        if expected_previous_revision < 0:
            raise ValueError("expected_previous_revision must not be negative")
        if source_evidence_set_id is not None:
            self._required(source_evidence_set_id, "source_evidence_set_id")

        article_json = canonical_article_json(draft)
        sha = article_sha256(article_json)
        citations = citations_from_payload(cast(dict[str, Any], json.loads(article_json)))
        now = datetime.now(UTC).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = self._read_revision(db, tenant_id, article_id, None)
            current = int(latest["revision_no"]) if latest is not None else 0
            if current != expected_previous_revision:
                raise ConcurrentArticleReviewError("Article revision changed since last read")
            if latest is not None and latest["status"] not in (
                ArticleReviewStatus.APPROVED.value,
                ArticleReviewStatus.CHANGES_REQUESTED.value,
            ):
                raise ConcurrentArticleReviewError("Previous revision is still under review")

            if current == 0:
                db.execute("INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", (tenant_id,))
                db.execute(
                    """
                    INSERT INTO knowledge_articles
                    (tenant_id, article_id, article_type, product, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (tenant_id, article_id, draft.article_type.value, draft.product, now),
                )
            else:
                parent = db.execute(
                    """
                    SELECT article_type, product FROM knowledge_articles
                    WHERE tenant_id = ? AND article_id = ?
                    """,
                    (tenant_id, article_id),
                ).fetchone()
                if parent is None:
                    raise ValueError("Article identity record is missing")
                if (
                    parent["article_type"] != draft.article_type.value
                    or parent["product"] != draft.product
                ):
                    raise ValueError("Article type and product must match its logical identity")

            revision_no = current + 1
            db.execute(
                """
                INSERT INTO article_revisions
                (tenant_id, article_id, revision_no, article_json, article_sha256,
                 status, submitted_by, source_evidence_set_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?)
                """,
                (
                    tenant_id, article_id, revision_no, article_json, sha,
                    submitted_by, source_evidence_set_id, now, now,
                ),
            )
            db.executemany(
                """
                INSERT INTO article_citations
                (tenant_id, article_id, revision_no, claim_path, ordinal,
                 chunk_id, chunk_content_fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        tenant_id, article_id, revision_no, item.claim_path, item.ordinal,
                        item.chunk_id, item.chunk_content_fingerprint,
                    )
                    for item in citations
                ],
            )
            db.execute(
                """
                INSERT INTO review_events
                (tenant_id, article_id, revision_no, event_seq,
                 event_type, actor_id, note, created_at)
                VALUES (?, ?, ?, 1, 'SUBMIT', ?, NULL, ?)
                """,
                (tenant_id, article_id, revision_no, submitted_by, now),
            )
        result = self.get(tenant_id=tenant_id, article_id=article_id, revision_no=revision_no)
        assert result is not None
        return result

    def decide(
        self,
        *,
        tenant_id: str,
        article_id: str,
        revision_no: int,
        reviewer_id: str,
        decision: ArticleReviewDecision,
        expected_event_seq: int,
        note: str = "",
    ) -> ArticleReviewRecord:
        """Compare-and-swap on one exact immutable revision and append its event."""
        for field, value in (
            ("tenant_id", tenant_id),
            ("article_id", article_id),
            ("reviewer_id", reviewer_id),
        ):
            self._required(value, field)
        if revision_no < 1 or expected_event_seq < 1:
            raise ValueError("revision_no and expected_event_seq must be positive")
        if not isinstance(decision, ArticleReviewDecision):
            raise ValueError("decision must be a valid ArticleReviewDecision")
        if decision is ArticleReviewDecision.REQUEST_CHANGES and not note.strip():
            raise ValueError("Requesting changes requires a review note")

        now = datetime.now(UTC).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._read_revision(db, tenant_id, article_id, revision_no)
            if row is None:
                raise KeyError(f"Unknown article revision: {article_id}/{revision_no}")
            self._verified_payload(db, row)
            if row["submitted_by"] == reviewer_id:
                raise PermissionError("Submitter cannot review their own draft")
            event = db.execute(
                """
                SELECT MAX(event_seq) FROM review_events
                WHERE tenant_id = ? AND article_id = ? AND revision_no = ?
                """,
                (tenant_id, article_id, revision_no),
            ).fetchone()
            current_seq = int(event[0]) if event is not None and event[0] is not None else 0
            if current_seq != expected_event_seq or row["status"] != "IN_REVIEW":
                raise ConcurrentArticleReviewError("Review version or status has changed")
            db.execute(
                """
                INSERT INTO review_events
                (tenant_id, article_id, revision_no, event_seq,
                 event_type, actor_id, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id, article_id, revision_no, current_seq + 1,
                    decision.value, reviewer_id, note.strip() or None, now,
                ),
            )
        result = self.get(tenant_id=tenant_id, article_id=article_id, revision_no=revision_no)
        assert result is not None
        return result

    def get(
        self, *, tenant_id: str, article_id: str, revision_no: int | None = None
    ) -> ArticleReviewRecord | None:
        with self._connect() as db:
            row = self._read_revision(db, tenant_id, article_id, revision_no)
            if row is None:
                return None
            self._verified_payload(db, row)
            return self._to_record(db, row)

    def article_payload(
        self, *, tenant_id: str, article_id: str, revision_no: int
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = self._read_revision(db, tenant_id, article_id, revision_no)
            return self._verified_payload(db, row) if row is not None else None

    def citations(
        self, *, tenant_id: str, article_id: str, revision_no: int
    ) -> tuple[ArticleCitation, ...]:
        with self._connect() as db:
            row = self._read_revision(db, tenant_id, article_id, revision_no)
            if row is None:
                return ()
            payload = self._verified_payload(db, row)
            return citations_from_payload(payload)

    def events(
        self, *, tenant_id: str, article_id: str, revision_no: int
    ) -> tuple[ArticleReviewEvent, ...]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT event_seq, event_type, actor_id, note, created_at
                FROM review_events
                WHERE tenant_id = ? AND article_id = ? AND revision_no = ?
                ORDER BY event_seq
                """,
                (tenant_id, article_id, revision_no),
            ).fetchall()
        return tuple(
            ArticleReviewEvent(
                tenant_id=tenant_id,
                article_id=article_id,
                revision_no=revision_no,
                event_seq=int(row["event_seq"]),
                event_type=ArticleReviewEventType(row["event_type"]),
                actor_id=str(row["actor_id"]),
                recorded_at=str(row["created_at"]),
                note=str(row["note"]) if row["note"] is not None else None,
            )
            for row in rows
        )

    def list_revisions(
        self, *, tenant_id: str, article_id: str
    ) -> tuple[ArticleReviewRecord, ...]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM article_revisions
                WHERE tenant_id = ? AND article_id = ?
                ORDER BY revision_no
                """,
                (tenant_id, article_id),
            ).fetchall()
            for row in rows:
                self._verified_payload(db, row)
            return tuple(self._to_record(db, row) for row in rows)
