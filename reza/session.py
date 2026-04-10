"""Session management — start, save, end, list, and handoff LLM sessions."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .schema import get_connection


def _new_id(llm_name: str) -> str:
    return f"{llm_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}"


def start_session(db: Path, llm_name: str, working_on: str = "", tags: str = "") -> str:
    """Create a new session and return its ID."""
    session_id = _new_id(llm_name)
    with get_connection(db) as conn:
        # Mark any previous active sessions from the same LLM as interrupted
        conn.execute(
            "UPDATE sessions SET status = 'interrupted' WHERE llm_name = ? AND status = 'active'",
            (llm_name,),
        )
        conn.execute(
            """
            INSERT INTO sessions (id, llm_name, status, working_on, tags, started_at)
            VALUES (?, ?, 'active', ?, ?, datetime('now'))
            """,
            (session_id, llm_name, working_on, tags),
        )
    return session_id


def save_session(
    db: Path,
    session_id: str,
    summary: str = "",
    conversation_context: str = "",
    files_modified: str = "",
) -> bool:
    """Update session progress. Returns True if session was found."""
    with get_connection(db) as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE sessions SET
                summary              = COALESCE(NULLIF(?, ''), summary),
                conversation_context = COALESCE(NULLIF(?, ''), conversation_context),
                files_modified       = COALESCE(NULLIF(?, ''), files_modified),
                status               = 'interrupted'
            WHERE id = ?
            """,
            (summary, conversation_context, files_modified, session_id),
        )
    return True


def end_session(db: Path, session_id: str, summary: str = "") -> bool:
    """Close a session as completed and release all file locks. Returns True if found."""
    with get_connection(db) as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE sessions SET
                status   = 'completed',
                ended_at = datetime('now'),
                summary  = COALESCE(NULLIF(?, ''), summary)
            WHERE id = ?
            """,
            (summary, session_id),
        )
        # Auto-release all file locks held by this session
        conn.execute("DELETE FROM file_locks WHERE session_id = ?", (session_id,))
    return True


def list_sessions(db: Path, status: Optional[str] = None) -> List[Dict]:
    """List sessions, optionally filtered by status."""
    with get_connection(db) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status = ? ORDER BY started_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_handoff_info(db: Path) -> List[Dict]:
    """Return all active or interrupted sessions with full context for handoff."""
    with get_connection(db) as conn:
        rows = conn.execute(
            """
            SELECT * FROM sessions
            WHERE status IN ('active', 'interrupted')
            ORDER BY started_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]
