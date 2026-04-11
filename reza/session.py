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


def get_handoff_data(
    db: Path,
    session_id: Optional[str] = None,
    budget_tokens: Optional[int] = None,
) -> Optional[Dict]:
    """Return enriched handoff dict for a session, including conversation turns.

    If session_id is None, returns the most recent interrupted or active session.
    Returns None if no matching session found.
    Raises ValueError if a specific session_id is given but not found.

    The returned dict contains all session fields plus:
      - turns: list of turn dicts (chronological, budget-truncated if budget_tokens set)
      - turns_truncated: int — how many oldest turns were dropped due to budget
      - budget_applied: int or None — the budget_tokens value used
    """
    with get_connection(db) as conn:
        if session_id:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Session not found: {session_id}")
        else:
            row = conn.execute(
                """
                SELECT * FROM sessions
                WHERE status IN ('active', 'interrupted')
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()

    if not row:
        return None

    data = dict(row)

    from .turns import list_turns, turns_within_budget
    if budget_tokens:
        turns = turns_within_budget(db, data["id"], budget_tokens)
        all_turns = list_turns(db, data["id"])
        data["turns_truncated"] = len(all_turns) - len(turns)
        data["budget_applied"] = budget_tokens
    else:
        turns = list_turns(db, data["id"])
        data["turns_truncated"] = 0
        data["budget_applied"] = None

    data["turns"] = turns
    return data
