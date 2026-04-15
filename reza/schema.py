"""Database schema definition and connection utilities."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

DB_DIR = ".reza"
DB_NAME = "context.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT UNIQUE NOT NULL,
    file_type    TEXT,
    line_count   INTEGER DEFAULT 0,
    size_bytes   INTEGER DEFAULT 0,
    purpose      TEXT,
    tags         TEXT,
    last_modified TEXT,
    checksum     TEXT,
    llm_notes    TEXT,
    indexed_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dependencies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    target_file     TEXT,
    dependency_type TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id                   TEXT PRIMARY KEY,
    llm_name             TEXT NOT NULL,
    started_at           TEXT DEFAULT (datetime('now')),
    ended_at             TEXT,
    status               TEXT DEFAULT 'active',
    working_on           TEXT,
    summary              TEXT,
    conversation_context TEXT,
    files_modified       TEXT,
    tags                 TEXT
);

CREATE TABLE IF NOT EXISTS changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    change_type TEXT,
    session_id  TEXT,
    changed_at  TEXT DEFAULT (datetime('now')),
    diff_summary TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS conflicts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    session_a   TEXT,
    session_b   TEXT,
    llm_a       TEXT,
    llm_b       TEXT,
    detected_at TEXT DEFAULT (datetime('now')),
    resolved    INTEGER DEFAULT 0,
    resolved_at TEXT,
    resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS file_locks (
    file_path  TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    llm_name   TEXT,
    claimed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_files_type     ON files(file_type);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_changes_file   ON changes(file_path);
CREATE INDEX IF NOT EXISTS idx_changes_session ON changes(session_id);
CREATE INDEX IF NOT EXISTS idx_changes_time    ON changes(changed_at);
CREATE INDEX IF NOT EXISTS idx_conflicts_file  ON conflicts(file_path);
CREATE INDEX IF NOT EXISTS idx_conflicts_open  ON conflicts(resolved);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    token_est   INTEGER NOT NULL DEFAULT 0,
    turn_index  INTEGER NOT NULL,
    recorded_at TEXT DEFAULT (datetime('now')),
    UNIQUE (session_id, turn_index),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS handoff_drops (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT UNIQUE NOT NULL,
    session_id  TEXT,
    ingested_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_index   ON conversation_turns(session_id, turn_index);

CREATE VIRTUAL TABLE IF NOT EXISTS conversation_turns_fts USING fts5(
    content,
    role UNINDEXED,
    session_id UNINDEXED,
    turn_id UNINDEXED,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS turns_fts_insert
AFTER INSERT ON conversation_turns
BEGIN
    INSERT INTO conversation_turns_fts(content, role, session_id, turn_id)
    VALUES (new.content, new.role, new.session_id, new.id);
END;

CREATE TRIGGER IF NOT EXISTS turns_fts_delete
AFTER DELETE ON conversation_turns
BEGIN
    DELETE FROM conversation_turns_fts WHERE turn_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS turns_fts_update
AFTER UPDATE OF content ON conversation_turns
BEGIN
    DELETE FROM conversation_turns_fts WHERE turn_id = old.id;
    INSERT INTO conversation_turns_fts(content, role, session_id, turn_id)
    VALUES (new.content, new.role, new.session_id, new.id);
END;
"""

GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_nodes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL,
    name           TEXT NOT NULL,
    qualified_name TEXT NOT NULL UNIQUE,
    file_path      TEXT NOT NULL,
    line_start     INTEGER,
    line_end       INTEGER,
    language       TEXT,
    parent_name    TEXT,
    params         TEXT,
    return_type    TEXT,
    is_test        INTEGER DEFAULT 0,
    file_hash      TEXT,
    extra          TEXT DEFAULT '{}',
    updated_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS code_edges (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kind             TEXT NOT NULL,
    source_qualified TEXT NOT NULL,
    target_qualified TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    line             INTEGER DEFAULT 0,
    confidence       REAL DEFAULT 1.0,
    confidence_tier  TEXT DEFAULT 'EXTRACTED',
    extra            TEXT DEFAULT '{}',
    updated_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS code_graph_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_code_nodes_file      ON code_nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_code_nodes_kind      ON code_nodes(kind);
CREATE INDEX IF NOT EXISTS idx_code_nodes_qualified  ON code_nodes(qualified_name);
CREATE INDEX IF NOT EXISTS idx_code_edges_source     ON code_edges(source_qualified);
CREATE INDEX IF NOT EXISTS idx_code_edges_target     ON code_edges(target_qualified);
CREATE INDEX IF NOT EXISTS idx_code_edges_kind       ON code_edges(kind);
CREATE INDEX IF NOT EXISTS idx_code_edges_file       ON code_edges(file_path);

CREATE VIRTUAL TABLE IF NOT EXISTS code_nodes_fts USING fts5(
    name,
    qualified_name,
    file_path UNINDEXED,
    node_id UNINDEXED,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS code_nodes_fts_insert
AFTER INSERT ON code_nodes
BEGIN
    INSERT INTO code_nodes_fts(name, qualified_name, file_path, node_id)
    VALUES (new.name, new.qualified_name, new.file_path, new.id);
END;

CREATE TRIGGER IF NOT EXISTS code_nodes_fts_delete
AFTER DELETE ON code_nodes
BEGIN
    DELETE FROM code_nodes_fts WHERE node_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS code_nodes_fts_update
AFTER UPDATE OF name, qualified_name ON code_nodes
BEGIN
    DELETE FROM code_nodes_fts WHERE node_id = old.id;
    INSERT INTO code_nodes_fts(name, qualified_name, file_path, node_id)
    VALUES (new.name, new.qualified_name, new.file_path, new.id);
END;
"""


def find_db_path(start_dir: Optional[str] = None) -> Optional[Path]:
    """Walk up the directory tree to find .reza/context.db."""
    current = Path(start_dir or os.getcwd()).resolve()
    while True:
        candidate = current / DB_DIR / DB_NAME
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def get_db_path(project_dir: Optional[str] = None) -> Path:
    """Return the expected DB path for a given project directory."""
    return Path(project_dir or os.getcwd()).resolve() / DB_DIR / DB_NAME


def _auto_migrate(conn: sqlite3.Connection) -> None:
    """Silently apply missing schema tables to legacy databases.

    Checks for the presence of the `conversation_turns` table (added in v0.2.0)
    and the `code_nodes` table (added in v0.5.0 graph layer).
    All CREATE IF NOT EXISTS statements are safe to re-run.
    """
    try:
        conn.execute("SELECT 1 FROM conversation_turns LIMIT 1")
    except sqlite3.OperationalError:
        conn.executescript(SCHEMA)
        conn.commit()

    try:
        conn.execute("SELECT 1 FROM code_nodes LIMIT 1")
    except sqlite3.OperationalError:
        conn.executescript(GRAPH_SCHEMA)
        conn.commit()


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a configured SQLite connection.

    Raises FileNotFoundError if no DB is found and db_path is not provided.
    Auto-migrates legacy databases missing the v0.2.0+ schema on first access.
    """
    if db_path is None:
        db_path = find_db_path()
    if db_path is None:
        raise FileNotFoundError(
            "No .reza/context.db found. Run 'reza init' in your project root first."
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _auto_migrate(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize all tables and indexes in the database."""
    conn.executescript(SCHEMA)
    conn.executescript(GRAPH_SCHEMA)
    conn.commit()
