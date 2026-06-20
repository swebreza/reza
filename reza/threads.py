"""Thread-aware cross-tool session continuity."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional

from .schema import get_connection
from .turns import list_turns


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())[:4]
    return "-".join(words) or "thread"


def _new_thread_id(title: str = "") -> str:
    return f"thread-{_slug(title)}-{uuid.uuid4().hex[:8]}"


def create_thread(db: Path, title: str = "", thread_id: Optional[str] = None) -> str:
    tid = thread_id or _new_thread_id(title)
    with get_connection(db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO threads (id, title, status, created_at, updated_at)
            VALUES (?, ?, 'active', datetime('now'), datetime('now'))
            """,
            (tid, title or tid),
        )
    return tid


def ensure_thread_for_session(db: Path, session_id: str, title: str = "") -> str:
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT thread_id, working_on FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Session not found: {session_id}")
        if row["thread_id"]:
            return row["thread_id"]
    tid = create_thread(db, title or row["working_on"] or session_id)
    link_session(db, session_id, tid)
    return tid


def latest_thread(db: Path) -> Optional[str]:
    with get_connection(db) as conn:
        row = conn.execute(
            """
            SELECT thread_id FROM sessions
            WHERE thread_id IS NOT NULL
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
    return row["thread_id"] if row else None


def link_session(db: Path, session_id: str, thread_id: str) -> bool:
    with get_connection(db) as conn:
        s = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not s:
            return False
        t = conn.execute("SELECT id FROM threads WHERE id = ?", (thread_id,)).fetchone()
        if not t:
            return False
        conn.execute(
            "UPDATE sessions SET thread_id = ? WHERE id = ?", (thread_id, session_id)
        )
        conn.execute(
            "UPDATE threads SET updated_at = datetime('now') WHERE id = ?", (thread_id,)
        )
    return True


def unlink_session(db: Path, session_id: str) -> bool:
    with get_connection(db) as conn:
        cur = conn.execute(
            "UPDATE sessions SET thread_id = NULL WHERE id = ?", (session_id,)
        )
    return cur.rowcount > 0


def list_threads(db: Path) -> list[dict]:
    with get_connection(db) as conn:
        rows = conn.execute(
            """
            SELECT t.*,
                   COUNT(s.id) AS session_count,
                   MAX(s.started_at) AS last_session_at
            FROM threads t
            LEFT JOIN sessions s ON s.thread_id = t.id
            GROUP BY t.id
            ORDER BY COALESCE(last_session_at, t.updated_at, t.created_at) DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_thread(db: Path, thread_id: str) -> Optional[dict]:
    with get_connection(db) as conn:
        row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        if not row:
            return None
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE thread_id = ? ORDER BY started_at ASC",
            (thread_id,),
        ).fetchall()
    data = dict(row)
    data["sessions"] = [dict(s) for s in sessions]
    return data


def get_thread_handoff_data(
    db: Path,
    thread_id: Optional[str] = None,
    budget_tokens: Optional[int] = None,
) -> Optional[dict]:
    tid = thread_id or latest_thread(db)
    if not tid:
        return None
    data = get_thread(db, tid)
    if not data:
        return None

    turns: list[dict] = []
    for session in data["sessions"]:
        turns.extend(list_turns(db, session["id"]))

    if budget_tokens:
        selected = []
        total = 0
        for turn in reversed(turns):
            cost = turn["token_est"] or (len(turn["content"]) // 4)
            if total + cost > budget_tokens:
                break
            selected.append(turn)
            total += cost
        turns = list(reversed(selected))

    data["type"] = "thread"
    data["turns"] = turns
    data["turns_truncated"] = max(0, sum(
        len(list_turns(db, s["id"])) for s in data["sessions"]
    ) - len(turns))
    data["budget_applied"] = budget_tokens
    return data
