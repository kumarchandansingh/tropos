-- Tropos target logical-to-physical reference model (SQLite 3.38+).
-- DESIGN CONTRACT ONLY. Do not execute against an existing Tropos runtime DB.
-- All actors and access checks must be verified by an authenticated application layer.
PRAGMA foreign_keys = ON;

CREATE TABLE tenants (
    tenant_id TEXT PRIMARY KEY CHECK (length(trim(tenant_id)) > 0)
);

CREATE TABLE principals (
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL CHECK (length(trim(principal_id)) > 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','DISABLED')),
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE principal_groups (
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    group_id TEXT NOT NULL CHECK (length(trim(group_id)) > 0),
    PRIMARY KEY (tenant_id, principal_id, group_id),
    FOREIGN KEY (tenant_id, principal_id)
        REFERENCES principals(tenant_id, principal_id)
);

CREATE TABLE knowledge_items (
    tenant_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, knowledge_id),
    UNIQUE (tenant_id, source_system, source_record_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE source_captures (
    tenant_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    content_type TEXT NOT NULL,
    payload BLOB NOT NULL,
    raw_payload_fingerprint TEXT NOT NULL CHECK (length(raw_payload_fingerprint) = 64),
    ingestion_fingerprint TEXT NOT NULL CHECK (length(ingestion_fingerprint) = 64),
    captured_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, capture_id),
    UNIQUE (tenant_id, ingestion_fingerprint),
    UNIQUE (tenant_id, knowledge_id, capture_id),
    FOREIGN KEY (tenant_id, knowledge_id)
        REFERENCES knowledge_items(tenant_id, knowledge_id)
);

CREATE TABLE content_versions (
    tenant_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL CHECK (length(content_fingerprint) = 64),
    normalization_strategy_version TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    title TEXT NOT NULL,
    canonical_content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, knowledge_id, content_fingerprint, normalization_strategy_version),
    FOREIGN KEY (tenant_id, knowledge_id, capture_id)
        REFERENCES source_captures(tenant_id, knowledge_id, capture_id)
);

CREATE TABLE access_policy_versions (
    tenant_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL CHECK (policy_version > 0),
    scope TEXT NOT NULL CHECK (scope IN ('unresolved','tenant','restricted')),
    policy_fingerprint TEXT NOT NULL CHECK (length(policy_fingerprint) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, knowledge_id, policy_version),
    FOREIGN KEY (tenant_id, knowledge_id)
        REFERENCES knowledge_items(tenant_id, knowledge_id)
);

CREATE TABLE access_policy_groups (
    tenant_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, knowledge_id, policy_version, group_id),
    FOREIGN KEY (tenant_id, knowledge_id, policy_version)
        REFERENCES access_policy_versions(tenant_id, knowledge_id, policy_version)
);

CREATE TABLE knowledge_heads (
    tenant_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    current_content_fingerprint TEXT NOT NULL,
    current_normalization_strategy_version TEXT NOT NULL,
    current_policy_version INTEGER NOT NULL,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('ACTIVE','DELETED')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, knowledge_id),
    FOREIGN KEY (tenant_id, knowledge_id, current_content_fingerprint,
                 current_normalization_strategy_version)
        REFERENCES content_versions(tenant_id, knowledge_id, content_fingerprint,
                                    normalization_strategy_version),
    FOREIGN KEY (tenant_id, knowledge_id, current_policy_version)
        REFERENCES access_policy_versions(tenant_id, knowledge_id, policy_version)
);

CREATE TABLE knowledge_chunks (
    tenant_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    knowledge_id TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    normalization_strategy_version TEXT NOT NULL,
    chunking_strategy_version TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_content_fingerprint TEXT NOT NULL CHECK (length(chunk_content_fingerprint) = 64),
    PRIMARY KEY (tenant_id, chunk_id),
    UNIQUE (tenant_id, chunk_id, chunk_content_fingerprint),
    UNIQUE (tenant_id, knowledge_id, content_fingerprint,
            normalization_strategy_version, chunking_strategy_version, sequence_number),
    CHECK (end_offset > start_offset),
    CHECK (length(chunk_text) = end_offset - start_offset),
    FOREIGN KEY (tenant_id, knowledge_id, content_fingerprint,
                 normalization_strategy_version)
        REFERENCES content_versions(tenant_id, knowledge_id, content_fingerprint,
                                    normalization_strategy_version)
);

CREATE TABLE chunk_embeddings (
    tenant_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    embedding_strategy_version TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector_json TEXT NOT NULL CHECK (json_valid(vector_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, chunk_id, embedding_strategy_version),
    FOREIGN KEY (tenant_id, chunk_id)
        REFERENCES knowledge_chunks(tenant_id, chunk_id)
);

CREATE TABLE resolve_runs (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    query_sha256 TEXT NOT NULL CHECK (length(query_sha256) = 64),
    outcome TEXT CHECK (outcome IN (
        'ANSWERED','RETRIEVAL_ABSTAINED','EVIDENCE_INSUFFICIENT','FAILED'
    )),
    trace_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, run_id),
    UNIQUE (tenant_id, trace_id),
    FOREIGN KEY (tenant_id, actor_id) REFERENCES principals(tenant_id, principal_id)
);

CREATE TABLE evidence_sets (
    tenant_id TEXT NOT NULL,
    evidence_set_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    retrieval_strategy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, evidence_set_id),
    FOREIGN KEY (tenant_id, run_id) REFERENCES resolve_runs(tenant_id, run_id)
);

CREATE TABLE evidence_members (
    tenant_id TEXT NOT NULL,
    evidence_set_id TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank > 0),
    alias TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    chunk_content_fingerprint TEXT NOT NULL,
    retrieval_score REAL NOT NULL,
    PRIMARY KEY (tenant_id, evidence_set_id, rank),
    UNIQUE (tenant_id, evidence_set_id, alias),
    UNIQUE (tenant_id, evidence_set_id, chunk_id),
    FOREIGN KEY (tenant_id, evidence_set_id)
        REFERENCES evidence_sets(tenant_id, evidence_set_id),
    FOREIGN KEY (tenant_id, chunk_id, chunk_content_fingerprint)
        REFERENCES knowledge_chunks(tenant_id, chunk_id, chunk_content_fingerprint)
);

CREATE TABLE knowledge_articles (
    tenant_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    article_type TEXT NOT NULL CHECK (article_type IN ('troubleshooting','how_to','faq')),
    product TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, article_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE article_revisions (
    tenant_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    article_json TEXT NOT NULL CHECK (json_valid(article_json)),
    article_sha256 TEXT NOT NULL CHECK (length(article_sha256) = 64),
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (
        status IN ('DRAFT','IN_REVIEW','APPROVED','CHANGES_REQUESTED')
    ),
    submitted_by TEXT NOT NULL,
    source_evidence_set_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, article_id, revision_no),
    FOREIGN KEY (tenant_id, article_id)
        REFERENCES knowledge_articles(tenant_id, article_id),
    FOREIGN KEY (tenant_id, submitted_by)
        REFERENCES principals(tenant_id, principal_id),
    FOREIGN KEY (tenant_id, source_evidence_set_id)
        REFERENCES evidence_sets(tenant_id, evidence_set_id)
);

CREATE TABLE article_citations (
    tenant_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    claim_path TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    chunk_id TEXT NOT NULL,
    chunk_content_fingerprint TEXT NOT NULL,
    PRIMARY KEY (tenant_id, article_id, revision_no, claim_path, ordinal),
    FOREIGN KEY (tenant_id, article_id, revision_no)
        REFERENCES article_revisions(tenant_id, article_id, revision_no),
    FOREIGN KEY (tenant_id, chunk_id, chunk_content_fingerprint)
        REFERENCES knowledge_chunks(tenant_id, chunk_id, chunk_content_fingerprint)
);

CREATE TABLE review_events (
    tenant_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    event_seq INTEGER NOT NULL CHECK (event_seq > 0),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'SUBMIT','APPROVE','REQUEST_CHANGES'
    )),
    actor_id TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, article_id, revision_no, event_seq),
    FOREIGN KEY (tenant_id, article_id, revision_no)
        REFERENCES article_revisions(tenant_id, article_id, revision_no),
    FOREIGN KEY (tenant_id, actor_id)
        REFERENCES principals(tenant_id, principal_id)
);

CREATE TABLE publications (
    tenant_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'PUBLISHED' CHECK (state IN ('PUBLISHED','REVOKED')),
    published_by TEXT NOT NULL,
    published_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (tenant_id, publication_id),
    FOREIGN KEY (tenant_id, article_id, revision_no)
        REFERENCES article_revisions(tenant_id, article_id, revision_no),
    FOREIGN KEY (tenant_id, published_by) REFERENCES principals(tenant_id, principal_id)
);

CREATE UNIQUE INDEX uq_one_active_publication
ON publications(tenant_id, article_id) WHERE state = 'PUBLISHED';

CREATE TABLE publication_events (
    tenant_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    event_seq INTEGER NOT NULL CHECK (event_seq > 0),
    event_type TEXT NOT NULL CHECK (event_type IN ('PUBLISH','REVOKE')),
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, publication_id, event_seq),
    FOREIGN KEY (tenant_id, publication_id)
        REFERENCES publications(tenant_id, publication_id),
    FOREIGN KEY (tenant_id, actor_id)
        REFERENCES principals(tenant_id, principal_id)
);

CREATE INDEX idx_capture_knowledge ON source_captures(tenant_id, knowledge_id, captured_at);
CREATE INDEX idx_chunks_version ON knowledge_chunks(
    tenant_id, knowledge_id, content_fingerprint, normalization_strategy_version
);
CREATE INDEX idx_chunk_embeddings_strategy ON chunk_embeddings(
    tenant_id, embedding_strategy_version, chunk_id
);
CREATE INDEX idx_review_queue ON article_revisions(tenant_id, status, created_at);
CREATE INDEX idx_article_citation_chunk ON article_citations(tenant_id, chunk_id);
CREATE INDEX idx_publications_article ON publications(tenant_id, article_id, published_at);

-- Immutable snapshots and event records: SQL-level protection against accidental edits.
CREATE TRIGGER article_revision_payload_immutable
BEFORE UPDATE OF article_json, article_sha256, submitted_by, source_evidence_set_id, created_at
ON article_revisions
BEGIN SELECT RAISE(ABORT, 'article revision payload is immutable'); END;

CREATE TRIGGER article_revision_no_delete
BEFORE DELETE ON article_revisions
BEGIN SELECT RAISE(ABORT, 'article revision is immutable'); END;

CREATE TRIGGER article_citation_insert_before_submission
BEFORE INSERT ON article_citations
WHEN NOT EXISTS (
    SELECT 1 FROM article_revisions r
    WHERE r.tenant_id = NEW.tenant_id AND r.article_id = NEW.article_id
      AND r.revision_no = NEW.revision_no AND r.status = 'DRAFT'
)
BEGIN SELECT RAISE(ABORT, 'citations are frozen after submission'); END;

CREATE TRIGGER article_citation_no_update
BEFORE UPDATE ON article_citations
BEGIN SELECT RAISE(ABORT, 'citations are immutable'); END;

CREATE TRIGGER article_citation_no_delete
BEFORE DELETE ON article_citations
BEGIN SELECT RAISE(ABORT, 'citations are immutable'); END;

CREATE TRIGGER evidence_member_no_update
BEFORE UPDATE ON evidence_members
BEGIN SELECT RAISE(ABORT, 'evidence set is immutable'); END;

CREATE TRIGGER evidence_member_no_delete
BEFORE DELETE ON evidence_members
BEGIN SELECT RAISE(ABORT, 'evidence set is immutable'); END;

CREATE TRIGGER review_event_no_update
BEFORE UPDATE ON review_events
BEGIN SELECT RAISE(ABORT, 'review event is immutable'); END;

CREATE TRIGGER review_event_no_delete
BEFORE DELETE ON review_events
BEGIN SELECT RAISE(ABORT, 'review event is immutable'); END;

CREATE TRIGGER publication_event_no_update
BEFORE UPDATE ON publication_events
BEGIN SELECT RAISE(ABORT, 'publication event is immutable'); END;

CREATE TRIGGER publication_event_no_delete
BEFORE DELETE ON publication_events
BEGIN SELECT RAISE(ABORT, 'publication event is immutable'); END;

-- The review event journal drives status; a direct status UPDATE must match
-- the latest event, otherwise it is rejected.
CREATE TRIGGER article_revision_status_from_event
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
BEGIN SELECT RAISE(ABORT, 'review status must follow a recorded event'); END;

CREATE TRIGGER review_event_transition_guard
BEFORE INSERT ON review_events
BEGIN
    SELECT CASE WHEN NEW.event_seq != (
        SELECT COALESCE(MAX(event_seq), 0) + 1 FROM review_events
        WHERE tenant_id = NEW.tenant_id AND article_id = NEW.article_id
          AND revision_no = NEW.revision_no
    ) THEN RAISE(ABORT, 'review events must be sequential') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM article_revisions r
        WHERE r.tenant_id = NEW.tenant_id AND r.article_id = NEW.article_id
          AND r.revision_no = NEW.revision_no
          AND (
              (NEW.event_type = 'SUBMIT' AND r.status = 'DRAFT'
               AND NEW.actor_id = r.submitted_by)
              OR
              (NEW.event_type IN ('APPROVE','REQUEST_CHANGES')
               AND r.status = 'IN_REVIEW' AND NEW.actor_id != r.submitted_by)
          )
    ) THEN RAISE(ABORT, 'invalid review transition or separation of duties') END;
    SELECT CASE WHEN NEW.event_type = 'REQUEST_CHANGES'
                 AND length(trim(COALESCE(NEW.note,''))) = 0
        THEN RAISE(ABORT, 'request changes requires a reason') END;
END;

CREATE TRIGGER review_event_applies_status
AFTER INSERT ON review_events
BEGIN
    UPDATE article_revisions
    SET status = CASE NEW.event_type
        WHEN 'SUBMIT' THEN 'IN_REVIEW'
        WHEN 'APPROVE' THEN 'APPROVED'
        ELSE 'CHANGES_REQUESTED'
    END
    WHERE tenant_id = NEW.tenant_id AND article_id = NEW.article_id
      AND revision_no = NEW.revision_no;
END;

-- Publication is an explicit action, not a synonym for approval.
-- The current-evidence gate ensures referenced chunks are still current and
-- their source is not deleted or unresolved at publication time.
CREATE TRIGGER publication_eligibility_guard
BEFORE INSERT ON publications
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM article_revisions r
        WHERE r.tenant_id = NEW.tenant_id AND r.article_id = NEW.article_id
          AND r.revision_no = NEW.revision_no AND r.status = 'APPROVED'
    ) THEN RAISE(ABORT, 'publication requires an approved revision') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM article_citations c
        WHERE c.tenant_id = NEW.tenant_id AND c.article_id = NEW.article_id
          AND c.revision_no = NEW.revision_no
    ) THEN RAISE(ABORT, 'publication requires evidence citations') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM article_citations c
        LEFT JOIN knowledge_chunks k
          ON k.tenant_id = c.tenant_id AND k.chunk_id = c.chunk_id
        LEFT JOIN knowledge_heads h
          ON h.tenant_id = k.tenant_id AND h.knowledge_id = k.knowledge_id
        LEFT JOIN access_policy_versions p
          ON p.tenant_id = h.tenant_id AND p.knowledge_id = h.knowledge_id
         AND p.policy_version = h.current_policy_version
        WHERE c.tenant_id = NEW.tenant_id AND c.article_id = NEW.article_id
          AND c.revision_no = NEW.revision_no
          AND (h.knowledge_id IS NULL
               OR p.policy_version IS NULL
               OR h.lifecycle_status != 'ACTIVE'
               OR p.scope = 'unresolved'
               OR k.content_fingerprint != h.current_content_fingerprint
               OR k.normalization_strategy_version !=
                  h.current_normalization_strategy_version)
    ) THEN RAISE(ABORT, 'publication references stale or ineligible evidence') END;
END;

CREATE TRIGGER publication_start_event
AFTER INSERT ON publications
BEGIN
    INSERT INTO publication_events
        (tenant_id, publication_id, event_seq, event_type, actor_id, created_at)
    VALUES (NEW.tenant_id, NEW.publication_id, 1, 'PUBLISH',
            NEW.published_by, NEW.published_at);
END;

CREATE TRIGGER publication_event_transition_guard
BEFORE INSERT ON publication_events
BEGIN
    SELECT CASE WHEN NEW.event_seq != (
        SELECT COALESCE(MAX(event_seq), 0) + 1 FROM publication_events
        WHERE tenant_id = NEW.tenant_id AND publication_id = NEW.publication_id
    ) THEN RAISE(ABORT, 'publication events must be sequential') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM publications p
        WHERE p.tenant_id = NEW.tenant_id AND p.publication_id = NEW.publication_id
          AND ((NEW.event_type = 'PUBLISH' AND NEW.event_seq = 1
                AND p.state = 'PUBLISHED' AND NEW.actor_id = p.published_by)
               OR (NEW.event_type = 'REVOKE' AND p.state = 'PUBLISHED'
                   AND NEW.event_seq > 1))
    ) THEN RAISE(ABORT, 'invalid publication transition') END;
END;

CREATE TRIGGER publication_state_from_event
BEFORE UPDATE OF state ON publications
WHEN NEW.state != 'REVOKED' OR NOT EXISTS (
    SELECT 1 FROM publication_events e
    WHERE e.tenant_id = NEW.tenant_id AND e.publication_id = NEW.publication_id
      AND e.event_type = 'REVOKE'
      AND e.event_seq = (
          SELECT MAX(x.event_seq) FROM publication_events x
          WHERE x.tenant_id = e.tenant_id AND x.publication_id = e.publication_id
      )
)
BEGIN SELECT RAISE(ABORT, 'publication state must follow a recorded revocation'); END;

CREATE TRIGGER publication_event_revokes
AFTER INSERT ON publication_events
WHEN NEW.event_type = 'REVOKE'
BEGIN
    UPDATE publications
    SET state = 'REVOKED', revoked_at = NEW.created_at
    WHERE tenant_id = NEW.tenant_id AND publication_id = NEW.publication_id;
END;


-- Read-side freshness projection. Consumers must STILL enforce caller-specific
-- tenant/group authorization against every cited source before displaying text.
-- A subsequent source deletion or governance change must hide stale publications
-- without relying solely on background invalidation jobs.
CREATE VIEW currently_eligible_publications AS
SELECT p.* FROM publications p
WHERE p.state = 'PUBLISHED'
AND NOT EXISTS (
    SELECT 1 FROM article_citations c
    LEFT JOIN knowledge_chunks k
      ON k.tenant_id = c.tenant_id AND k.chunk_id = c.chunk_id
    LEFT JOIN knowledge_heads h
      ON h.tenant_id = k.tenant_id AND h.knowledge_id = k.knowledge_id
    LEFT JOIN access_policy_versions policy
      ON policy.tenant_id = h.tenant_id AND policy.knowledge_id = h.knowledge_id
     AND policy.policy_version = h.current_policy_version
    WHERE c.tenant_id = p.tenant_id AND c.article_id = p.article_id
      AND c.revision_no = p.revision_no
      AND (h.knowledge_id IS NULL OR policy.policy_version IS NULL
           OR h.lifecycle_status != 'ACTIVE' OR policy.scope = 'unresolved'
           OR h.current_content_fingerprint != k.content_fingerprint
           OR h.current_normalization_strategy_version !=
              k.normalization_strategy_version)
);
