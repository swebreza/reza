"""Cross-LLM handoff pack.

Produces a single markdown blob the user can paste into any new LLM. The next
LLM reads it, optionally queries ``reza`` for deeper context, and picks up
where the previous one left off.

Sections (each token-budgeted):
1. Header — project + generation timestamp
2. Active session summary + last N turns (if any)
3. Top-N code nodes relevant to the query
4. Recent file changes
5. One-line instructions for the receiving LLM
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .find import unified_find
from .overview import build_overview, render_overview_markdown


@dataclass
class PackOptions:
    query: str = ""
    max_tokens: int = 4000
    session_id: Optional[str] = None
    include_overview: bool = True
    include_recent_chat: bool = True
    include_recent_changes: bool = True
    chat_turns: int = 12
    change_count: int = 15
    hits_per_source: int = 5


def _get_active_session(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    row = conn.execute(
        """SELECT * FROM sessions
           WHERE status = 'active'
           ORDER BY started_at DESC LIMIT 1"""
    ).fetchone()
    if row:
        return row
    return conn.execute(
        """SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1"""
    ).fetchone()


def _get_session_by_id(conn: sqlite3.Connection, sid: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (sid,)
    ).fetchone()


def _recent_turns(
    conn: sqlite3.Connection, session_id: str, n: int
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """SELECT role, content, recorded_at, turn_index
               FROM conversation_turns
               WHERE session_id = ?
               ORDER BY turn_index DESC
               LIMIT ?""",
            (session_id, n),
        ).fetchall()
    )[::-1]


def _recent_changes(conn: sqlite3.Connection, n: int) -> list[sqlite3.Row]:
    try:
        return list(
            conn.execute(
                """SELECT file_path, change_type, changed_at, session_id
                   FROM changes
                   ORDER BY changed_at DESC LIMIT ?""",
                (n,),
            ).fetchall()
        )
    except sqlite3.OperationalError:
        return []


def build_context_pack(
    conn: sqlite3.Connection, options: PackOptions | None = None
) -> str:
    opts = options or PackOptions()
    parts: list[str] = []

    parts.append("# reza — cross-LLM handoff pack")
    parts.append(
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_  "
        f"{('_Query: `' + opts.query + '`_') if opts.query else ''}"
    )
    parts.append("")
    parts.append(
        "> Receiving LLM: use this pack as your starting context. To load more "
        "detail on-demand run:\n"
        "> - `reza graph overview --json` — full project structure\n"
        "> - `reza graph neighbors <qualified_name> --json` — zoom into a node\n"
        "> - `reza graph subtree <file-or-qn> --json` — list contents of a container\n"
        "> - `reza find <query> --json` — hybrid search\n"
    )
    parts.append("")

    # Active session
    if opts.session_id:
        sess = _get_session_by_id(conn, opts.session_id)
    else:
        sess = _get_active_session(conn)

    if sess is not None:
        parts.append("## Session")
        parts.append(
            f"- **id:** `{sess['id']}`\n"
            f"- **llm:** {sess['llm_name']}\n"
            f"- **status:** {sess['status']}\n"
            f"- **started:** {sess['started_at']}  "
            f"**ended:** {sess['ended_at'] or '—'}\n"
            f"- **working on:** {sess['working_on'] or '—'}\n"
            f"- **summary:** {sess['summary'] or '—'}"
        )
        parts.append("")

        if opts.include_recent_chat:
            turns = _recent_turns(conn, sess["id"], opts.chat_turns)
            if turns:
                parts.append(f"### Last {len(turns)} turns")
                for t in turns:
                    c = (t["content"] or "").strip().replace("\r\n", "\n")
                    if len(c) > 600:
                        c = c[:600] + "…"
                    parts.append(f"**{t['role']}** _({t['recorded_at']})_\n")
                    parts.append(c + "\n")
                parts.append("")

    # Overview
    if opts.include_overview:
        try:
            ov = build_overview(conn)
            budget = min(1500, max(800, opts.max_tokens // 4))
            md = render_overview_markdown(ov, max_tokens=budget)
            parts.append(md)
        except sqlite3.OperationalError:
            pass

    # Hits
    if opts.query:
        hits = unified_find(conn, opts.query, limit=opts.hits_per_source * 3)
        if hits:
            parts.append(f"## Top matches for `{opts.query}`")
            for h in hits[: opts.hits_per_source * 3]:
                badge = {"graph": "G", "chat": "C", "file": "F"}[h.source]
                parts.append(
                    f"- [{badge}] **{h.title}** — {h.subtitle} "
                    f"_(score {h.score:.2f})_"
                )
                if h.qualified_name:
                    parts.append(f"  • `qn:` `{h.qualified_name}`")
            parts.append("")

    # Recent changes
    if opts.include_recent_changes:
        ch = _recent_changes(conn, opts.change_count)
        if ch:
            parts.append("## Recent file changes")
            for r in ch:
                parts.append(
                    f"- `{r['file_path']}` — {r['change_type']} "
                    f"_{r['changed_at']}_"
                )
            parts.append("")

    body = "\n".join(parts)

    # Hard budget enforcement
    char_cap = opts.max_tokens * 4
    if len(body) > char_cap:
        body = body[:char_cap].rstrip() + "\n\n…_(truncated to fit token budget)_\n"

    return body
