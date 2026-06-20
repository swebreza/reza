"""Shared helpers for cross-tool chat ingestion."""

from __future__ import annotations

import sqlite3
import uuid
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from reza.privacy import redact_text


@dataclass
class ParsedTurn:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class ParsedSession:
    """A single conversation, tool-agnostic."""
    source_tool: str            # 'cursor' | 'codex' | 'claude'
    source_id: str              # tool-native session id (UUID / rollout id)
    source_path: str            # absolute path to the transcript file
    llm_name: str               # display name, e.g. 'cursor' or 'codex-gpt-5'
    started_at: Optional[str] = None   # ISO timestamp
    working_on: str = ""
    project_cwd: Optional[str] = None  # if recorded by the tool
    turns: list[ParsedTurn] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)


def _reza_id_for(session: ParsedSession) -> str:
    """Deterministic reza session id derived from source_tool + source_id.

    Stable across re-syncs so the same Cursor/Codex session always maps to the
    same reza session. Falls back to random UUID if source_id is missing.
    """
    if session.source_id:
        short = session.source_id.replace("-", "")[:12]
        return f"{session.source_tool}-{short}"
    return f"{session.source_tool}-{uuid.uuid4().hex[:12]}"


def _thread_id_for(session: ParsedSession) -> str:
    if session.source_id:
        short = session.source_id.replace("-", "")[:12]
    else:
        short = uuid.uuid4().hex[:12]
    return f"thread-{session.source_tool}-{short}"


def _thread_title_for(session: ParsedSession) -> str:
    title = (session.working_on or "").strip()
    if title:
        title = re.sub(r"\s+", " ", title)
        return title[:120]
    return f"{session.source_tool} session {session.source_id or ''}".strip()


def upsert_imported_session(
    conn: sqlite3.Connection, session: ParsedSession
) -> tuple[str, int, int]:
    """Insert or refresh a session + append any new turns.

    Idempotent: if the same (source_tool, source_path) was seen before we
    count existing turns and only insert the new tail.

    Returns:
        (reza_session_id, turns_synced, turns_skipped)
    """
    if not session.turns:
        return (_reza_id_for(session), 0, 0)

    sid = _reza_id_for(session)

    existing = conn.execute(
        """SELECT id FROM sessions
           WHERE (source_tool = ? AND source_path = ?)
              OR id = ?
           LIMIT 1""",
        (session.source_tool, session.source_path, sid),
    ).fetchone()

    files_csv = ",".join(session.files_touched) if session.files_touched else ""
    thread_id = _thread_id_for(session)
    thread_title = _thread_title_for(session)
    conn.execute(
        """
        INSERT OR IGNORE INTO threads (id, title, status, created_at, updated_at)
        VALUES (?, ?, 'active', COALESCE(?, datetime('now')), datetime('now'))
        """,
        (thread_id, thread_title, session.started_at),
    )

    if existing:
        sid = existing["id"] if hasattr(existing, "keys") else existing[0]
        conn.execute(
            """UPDATE sessions SET
                 llm_name       = COALESCE(NULLIF(?, ''), llm_name),
                 working_on     = COALESCE(NULLIF(?, ''), working_on),
                 files_modified = COALESCE(NULLIF(?, ''), files_modified),
                 source_tool    = ?,
                 source_path    = ?,
                 source_id      = ?,
                 thread_id      = COALESCE(thread_id, ?)
               WHERE id = ?""",
            (
                session.llm_name,
                session.working_on,
                files_csv,
                session.source_tool,
                session.source_path,
                session.source_id,
                thread_id,
                sid,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO sessions
                 (id, llm_name, status, started_at, working_on,
                  files_modified,
                  source_tool, source_path, source_id, thread_id)
               VALUES (?, ?, 'completed', COALESCE(?, datetime('now')), ?,
                       ?, ?, ?, ?, ?)""",
            (
                sid,
                session.llm_name,
                session.started_at,
                session.working_on,
                files_csv,
                session.source_tool,
                session.source_path,
                session.source_id,
                thread_id,
            ),
        )
    conn.execute("UPDATE threads SET updated_at = datetime('now') WHERE id = ?", (thread_id,))

    already = conn.execute(
        "SELECT COUNT(*) AS n FROM conversation_turns WHERE session_id = ?",
        (sid,),
    ).fetchone()
    already_n = already["n"] if hasattr(already, "keys") else already[0]

    total = len(session.turns)
    if already_n >= total:
        return (sid, 0, total)

    new_tail = session.turns[already_n:]
    # Figure out the next turn_index. Use existing count as the offset.
    next_idx = already_n
    rows = []
    for t in new_tail:
        content = redact_text(t.content or "")
        rows.append((sid, t.role, content, max(1, len(content) // 4), next_idx))
        next_idx += 1

    conn.executemany(
        """INSERT INTO conversation_turns
             (session_id, role, content, token_est, turn_index, recorded_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        rows,
    )
    conn.execute(
        """INSERT INTO conversation_sources
             (session_id, adapter_name, source_path, source_id, project_path, last_seen_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(adapter_name, source_path) DO UPDATE SET
             session_id = excluded.session_id,
             source_id = excluded.source_id,
             project_path = excluded.project_path,
             last_seen_at = datetime('now')""",
        (
            sid,
            session.source_tool,
            session.source_path,
            session.source_id,
            session.project_cwd,
        ),
    )
    conn.execute(
        """INSERT INTO sync_checkpoints
             (adapter_name, source_path, position, last_synced_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(adapter_name, source_path) DO UPDATE SET
             position = excluded.position,
             last_synced_at = datetime('now')""",
        (session.source_tool, session.source_path, total),
    )
    return (sid, len(rows), already_n)


def cwd_matches(project_cwd: Optional[str], target: Path) -> bool:
    """Best-effort match of a tool-recorded CWD against the current project.

    Case-insensitive on Windows, forgiving of trailing slashes and drive case.
    """
    if not project_cwd:
        return False
    try:
        a = Path(project_cwd).resolve()
        b = Path(target).resolve()
    except (OSError, ValueError):
        return False
    return str(a).lower().rstrip("\\/") == str(b).lower().rstrip("\\/")
