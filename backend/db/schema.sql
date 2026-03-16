-- =============================================================================
-- Samvad Database Schema
-- Version : 1.0
-- Engine  : SQLite (MVP) — migration-ready for PostgreSQL
--
-- Migration notes:
--   SQLite  → PostgreSQL: swap TEXT UUIDs to UUID type, TEXT datetimes to
--   TIMESTAMPTZ, enable native FK enforcement (already ON in SQLite via PRAGMA).
--   No column renames, no structural changes required.
--
-- Usage:
--   SQLite  : sqlite3 samvad.db < schema.sql
--   Python  : cursor.executescript(open('schema.sql').read())
--
-- PRAGMA required at every SQLite connection open:
--   PRAGMA foreign_keys = ON;
--   PRAGMA journal_mode = WAL;   -- better concurrent read performance
-- =============================================================================


-- =============================================================================
-- TABLE: users
-- One row per user. Single-user deployment = one row, always.
-- Multi-user: insert additional rows. No schema change needed.
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,           -- UUID v4, generated in Python
    username        TEXT NOT NULL UNIQUE,       -- login handle, case-insensitive
    display_name    TEXT NOT NULL,              -- shown in UI header
    password_hash   TEXT NOT NULL,              -- bcrypt hash, never store plaintext
    role            TEXT NOT NULL DEFAULT 'user',
                                                -- 'admin' | 'user'
                                                -- admin can manage corpus, view audit log
    is_active       INTEGER NOT NULL DEFAULT 1, -- 0 = account disabled (not deleted)
    created_at      TEXT NOT NULL,              -- ISO 8601: 2026-03-14T09:00:00Z
    last_login_at   TEXT,                       -- NULL until first login
    preferences     TEXT                        -- JSON: UI prefs, default domain, etc.
                                                -- e.g. {"theme":"dark","default_domain":"tax"}
);

-- Index: login lookup by username
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);


-- =============================================================================
-- TABLE: sessions
-- One conversation thread. One active session per user at a time.
-- Historical sessions are preserved — never deleted, just closed.
--
-- Single-user behaviour: user always has 0 or 1 active session.
-- Multi-user behaviour: each user independently has 0 or 1 active session.
-- =============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,           -- UUID v4
    user_id         TEXT NOT NULL
                        REFERENCES users(user_id) ON DELETE CASCADE,
    title           TEXT,                       -- auto-generated or user-renamed
                                                -- e.g. "Section 80C query — 14 Mar"
    status          TEXT NOT NULL DEFAULT 'active',
                                                -- 'active' | 'closed' | 'archived'
    is_active       INTEGER NOT NULL DEFAULT 1, -- 1 = current active session for this user
                                                -- enforced: only one active per user
    domain_last     TEXT,                       -- last routed domain: tax|equity|risk|doc|general
    total_turns     INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0, -- cumulative tokens used this session
    created_at      TEXT NOT NULL,
    last_active_at  TEXT NOT NULL,
    closed_at       TEXT                        -- NULL while active
);

-- Index: fast lookup of active session per user (the most frequent query)
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_active_user
    ON sessions(user_id)
    WHERE is_active = 1;
    -- This partial unique index enforces one active session per user at the DB level.
    -- PostgreSQL supports partial unique indexes identically.

-- Index: session history list for sidebar
CREATE INDEX IF NOT EXISTS idx_sessions_user_history
    ON sessions(user_id, last_active_at DESC);


-- =============================================================================
-- TABLE: turns
-- Individual messages within a session. Both user and assistant turns.
-- Append-only — turns are never updated or deleted.
-- =============================================================================
CREATE TABLE IF NOT EXISTS turns (
    turn_id         TEXT PRIMARY KEY,           -- UUID v4
    session_id      TEXT NOT NULL
                        REFERENCES sessions(session_id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL
                        REFERENCES users(user_id) ON DELETE CASCADE,
                                                -- denormalised for fast per-user queries
                                                -- without joining through sessions
    turn_number     INTEGER NOT NULL,           -- 1-indexed within session
    role            TEXT NOT NULL,              -- 'user' | 'assistant'
    content         TEXT NOT NULL,              -- full message text
    domain          TEXT,                       -- routed domain for this turn
    tokens_input    INTEGER,                    -- tokens in prompt for this turn
    tokens_output   INTEGER,                    -- tokens in response for this turn
    retrieval_used  INTEGER NOT NULL DEFAULT 0, -- 1 if RAG retrieval was performed
    sources_cited   TEXT,                       -- JSON array of source references
                                                -- e.g. [{"doc":"IT Act 2025","section":"80C","page":null}]
    flags           TEXT,                       -- JSON array: injection flags if any
                                                -- e.g. ["INJECTION_ATTEMPT_L1"]
    latency_ms      INTEGER,                    -- response generation time in ms
    created_at      TEXT NOT NULL
);

-- Index: load all turns for a session in order (most frequent query)
CREATE INDEX IF NOT EXISTS idx_turns_session
    ON turns(session_id, turn_number ASC);

-- Index: per-user turn history (for audit and export)
CREATE INDEX IF NOT EXISTS idx_turns_user
    ON turns(user_id, created_at DESC);


-- =============================================================================
-- TABLE: session_summaries
-- Rolling compressed context. One active summary per session at a time.
-- Previous summaries are retained for debugging and audit purposes.
-- =============================================================================
CREATE TABLE IF NOT EXISTS session_summaries (
    summary_id          TEXT PRIMARY KEY,       -- UUID v4
    session_id          TEXT NOT NULL
                            REFERENCES sessions(session_id) ON DELETE CASCADE,
    summary_text        TEXT NOT NULL,          -- structured format (see below)
    turns_from          INTEGER NOT NULL,       -- first turn number covered
    turns_to            INTEGER NOT NULL,       -- last turn number covered
    is_current          INTEGER NOT NULL DEFAULT 1,
                                                -- 1 = active summary used in context
                                                -- 0 = superseded by newer summary
    tokens_saved        INTEGER,                -- how many tokens this summary replaced
    created_at          TEXT NOT NULL
);

-- Index: fast fetch of current summary for a session
CREATE INDEX IF NOT EXISTS idx_summaries_session_current
    ON session_summaries(session_id, is_current DESC);

-- =============================================================================
-- Summary text format (enforced by application, not DB):
--
-- [SESSION CONTEXT]
-- User profile signals : <inferred from conversation>
-- Topics covered       : <comma-separated topics>
-- Key figures          : <important numbers, tickers, section references>
-- Open questions       : <unresolved items from prior turns>
-- Last domain          : <tax|equity|risk|doc|general>
-- Turns summarised     : <turns_from>-<turns_to>
-- =============================================================================


-- =============================================================================
-- TABLE: user_documents
-- Persistent document library — one entry per uploaded file per user.
-- Documents are indexed into ChromaDB once and reused across sessions.
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_documents (
    doc_id              TEXT PRIMARY KEY,       -- UUID v4, also used as ChromaDB collection prefix
    user_id             TEXT NOT NULL
                            REFERENCES users(user_id) ON DELETE CASCADE,
    filename            TEXT NOT NULL,          -- original filename as uploaded
    display_name        TEXT,                   -- user-renamed label (nullable)
    file_type           TEXT NOT NULL,          -- 'pdf'|'docx'|'csv'|'xlsx'|'txt'
    file_size_bytes     INTEGER,
    chunk_count         INTEGER,                -- number of chunks indexed into ChromaDB
    embedding_model     TEXT,                   -- e.g. 'bge-small-en-v1.5'
                                                -- important for re-index detection
    sanitisation_status TEXT NOT NULL DEFAULT 'clean',
                                                -- 'clean'|'flagged'|'quarantined'
    sanitisation_flags  TEXT,                   -- JSON array of detected patterns if flagged
    chroma_collection   TEXT,                   -- ChromaDB collection name for this doc
    indexed_at          TEXT NOT NULL,
    last_used_at        TEXT                    -- updated when attached to a session
);

-- Index: user's document library list
CREATE INDEX IF NOT EXISTS idx_user_documents_user
    ON user_documents(user_id, indexed_at DESC);

-- Index: find documents by sanitisation status (for security review)
CREATE INDEX IF NOT EXISTS idx_user_documents_sanit
    ON user_documents(sanitisation_status)
    WHERE sanitisation_status != 'clean';


-- =============================================================================
-- TABLE: session_documents
-- Join table: which documents are active in which session.
-- A document can be attached to multiple sessions without re-indexing.
-- Retriever scopes ChromaDB queries to collections in this table.
-- =============================================================================
CREATE TABLE IF NOT EXISTS session_documents (
    session_id      TEXT NOT NULL
                        REFERENCES sessions(session_id) ON DELETE CASCADE,
    doc_id          TEXT NOT NULL
                        REFERENCES user_documents(doc_id) ON DELETE CASCADE,
    attached_at     TEXT NOT NULL,
    attached_by     TEXT NOT NULL DEFAULT 'user',
                                                -- 'user' = manually uploaded in this session
                                                -- 'reattached' = pulled from library
    PRIMARY KEY (session_id, doc_id)
);

-- Index: find all sessions that use a given document
CREATE INDEX IF NOT EXISTS idx_session_documents_doc
    ON session_documents(doc_id);


-- =============================================================================
-- TABLE: corpus_index
-- Global registry of pre-indexed regulatory documents in ChromaDB.
-- No user scope — corpus is shared across all users.
-- Tracks what is in the RAG corpus, version, and index health.
-- =============================================================================
CREATE TABLE IF NOT EXISTS corpus_index (
    corpus_id       TEXT PRIMARY KEY,           -- UUID v4
    source_name     TEXT NOT NULL,              -- e.g. 'Income Tax Act 2025'
    source_type     TEXT NOT NULL,              -- 'act'|'regulation'|'circular'|'dtaa'|'book'
    regulator       TEXT,                       -- 'CBDT'|'SEBI'|'RBI'|'MCA'|null
    version         TEXT,                       -- e.g. 'FY2025-26', 'Amendment No.3'
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    embedding_model TEXT NOT NULL,              -- e.g. 'bge-small-en-v1.5'
    chroma_collection TEXT NOT NULL,            -- ChromaDB collection name
    index_status    TEXT NOT NULL DEFAULT 'active',
                                                -- 'active'|'reindexing'|'deprecated'
    file_path       TEXT,                       -- source file path on disk
    indexed_at      TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    notes           TEXT                        -- e.g. 'Covers Sections 1-200 only'
);

-- Index: lookup by source type (used by retriever domain filter)
CREATE INDEX IF NOT EXISTS idx_corpus_source_type
    ON corpus_index(source_type, index_status);


-- =============================================================================
-- TABLE: audit_log
-- System events, errors, and security flags only.
-- No query content stored — this is for debugging and system health.
-- Kept simple per design decision.
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    log_id          TEXT PRIMARY KEY,           -- UUID v4
    user_id         TEXT
                        REFERENCES users(user_id) ON DELETE SET NULL,
                                                -- nullable: system events have no user
    session_id      TEXT,                       -- nullable: some events are not session-scoped
    event_type      TEXT NOT NULL,
                                                -- See event type registry below
    severity        TEXT NOT NULL DEFAULT 'info',
                                                -- 'info'|'warning'|'error'|'critical'
    message         TEXT NOT NULL,              -- human-readable description
    details         TEXT,                       -- JSON: structured extra data, never query content
    created_at      TEXT NOT NULL
);

-- Index: recent events for dashboard / debugging
CREATE INDEX IF NOT EXISTS idx_audit_recent
    ON audit_log(created_at DESC);

-- Index: filter by severity for alerting
CREATE INDEX IF NOT EXISTS idx_audit_severity
    ON audit_log(severity, created_at DESC)
    WHERE severity IN ('warning', 'error', 'critical');

-- Index: events per user (for user-scoped health checks)
CREATE INDEX IF NOT EXISTS idx_audit_user
    ON audit_log(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- =============================================================================
-- Audit event type registry (enforced by application layer):
--
-- System lifecycle
--   server_start         : Samvad server started
--   server_stop          : Samvad server stopped
--   model_loaded         : Arthvidya model loaded successfully
--   model_error          : Arthvidya inference error
--   db_migration         : Schema migration applied
--
-- Auth events
--   login_success        : User authenticated successfully
--   login_failure        : Failed login attempt (wrong password)
--   logout               : User logged out
--   account_locked       : Account disabled after repeated failures
--
-- Security events
--   injection_attempt    : Input sanitiser detected injection pattern (Layer 1)
--   document_flagged     : Document sanitiser flagged uploaded content (Layer 2)
--   document_quarantined : Document quarantined — too many flags
--   output_anomaly       : Output validator detected anomaly (Layer 4)
--
-- Corpus events
--   corpus_indexed       : New document added to regulatory corpus
--   corpus_reindexed     : Existing corpus document reindexed
--   corpus_deprecated    : Corpus document marked deprecated
--
-- System errors
--   retrieval_error      : ChromaDB or BM25 retrieval failure
--   inference_timeout    : Arthvidya did not respond within timeout
--   storage_error        : Database write failure
-- =============================================================================


-- =============================================================================
-- SEED DATA — default single user
-- Application creates this on first startup if users table is empty.
-- Password must be set via setup script — this is a placeholder hash.
-- =============================================================================
-- INSERT INTO users (user_id, username, display_name, password_hash, role, created_at)
-- VALUES (
--     'usr_00000000-0000-0000-0000-000000000001',
--     'admin',
--     'Administrator',
--     '$2b$12$PLACEHOLDER_HASH_SET_VIA_SETUP_SCRIPT',
--     'admin',
--     '2026-01-01T00:00:00Z'
-- );


-- =============================================================================
-- VIEWS — convenience queries used frequently by the application
-- =============================================================================

-- Active session for a user (application calls this constantly)
CREATE VIEW IF NOT EXISTS v_active_session AS
    SELECT
        s.session_id,
        s.user_id,
        s.title,
        s.total_turns,
        s.total_tokens,
        s.domain_last,
        s.created_at,
        s.last_active_at
    FROM sessions s
    WHERE s.is_active = 1;

-- Session list for sidebar (title, last active, turn count)
CREATE VIEW IF NOT EXISTS v_session_history AS
    SELECT
        s.session_id,
        s.user_id,
        COALESCE(s.title, 'Untitled — ' || substr(s.created_at, 1, 10)) AS title,
        s.status,
        s.total_turns,
        s.domain_last,
        s.created_at,
        s.last_active_at
    FROM sessions s
    ORDER BY s.last_active_at DESC;

-- Current summary for a session (used by context assembler every inference call)
CREATE VIEW IF NOT EXISTS v_current_summary AS
    SELECT
        ss.summary_id,
        ss.session_id,
        ss.summary_text,
        ss.turns_from,
        ss.turns_to,
        ss.tokens_saved
    FROM session_summaries ss
    WHERE ss.is_current = 1;

-- Document library for a user with last-used session info
CREATE VIEW IF NOT EXISTS v_user_library AS
    SELECT
        d.doc_id,
        d.user_id,
        d.filename,
        COALESCE(d.display_name, d.filename) AS label,
        d.file_type,
        d.chunk_count,
        d.sanitisation_status,
        d.indexed_at,
        d.last_used_at
    FROM user_documents d
    ORDER BY d.last_used_at DESC NULLS LAST;

-- Active corpus (what is currently indexed and available for retrieval)
CREATE VIEW IF NOT EXISTS v_active_corpus AS
    SELECT
        corpus_id,
        source_name,
        source_type,
        regulator,
        version,
        chunk_count,
        chroma_collection,
        last_updated_at
    FROM corpus_index
    WHERE index_status = 'active'
    ORDER BY source_type, source_name;
