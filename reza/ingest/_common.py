"""Shared helpers for cross-tool chat ingestion."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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

    if existing:
        sid = existing["id"] if hasattr(existing, "keys") else existing[0]
        conn.execute(
            """UPDATE sessions SET
                 llm_name       = COALESCE(NULLIF(?, ''), llm_name),
                 working_on     = COALESCE(NULLIF(?, ''), working_on),
                 files_modified = COALESCE(NULLIF(?, ''), files_modified),
                 source_tool    = ?,
                 source_path    = ?,
                 source_id      = ?
               WHERE id = ?""",
            (
                session.llm_name,
                session.working_on,
                files_csv,
                session.source_tool,
                session.source_path,
                session.source_id,
                sid,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO sessions
                 (id, llm_name, status, started_at, working_on,
                  files_modified,
                  source_tool, source_path, source_id)
               VALUES (?, ?, 'completed', COALESCE(?, datetime('now')), ?,
                       ?, ?, ?, ?)""",
            (
                sid,
                session.llm_name,
                session.started_at,
                session.working_on,
                files_csv,
                session.source_tool,
                session.source_path,
                session.source_id,
            ),
        )

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
        content = t.content or ""
        rows.append((sid, t.role, content, max(1, len(content) // 4), next_idx))
        next_idx += 1

    conn.executemany(
        """INSERT INTO conversation_turns
             (session_id, role, content, token_est, turn_index, recorded_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        rows,
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
