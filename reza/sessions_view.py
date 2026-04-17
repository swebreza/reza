"""Rich session inspection — show, load, and export subgraphs for a session.

Powers ``reza session show``, ``reza session load``, and the VS Code
Sessions panel. All functions operate on a ``sqlite3.Connection`` so they can
be called from anywhere with an open DB.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SessionDetail:
    id: str
    llm_name: str
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    working_on: str
    summary: str
    source_tool: Optional[str]
    source_id: Optional[str]
    source_path: Optional[str]
    turn_count: int
    token_total: int
    files_touched: list[str] = field(default_factory=list)
    first_user_message: str = ""
    last_turn_at: Optional[str] = None


def _file_set(row: sqlite3.Row) -> set[str]:
    raw = row["files_modified"] if "files_modified" in row.keys() else None
    if not raw:
        return set()
    return {f.strip() for f in raw.split(",") if f.strip()}


def list_sessions(
    conn: sqlite3.Connection,
    *,
    source: Optional[str] = None,
    limit: int = 100,
    search: Optional[str] = None,
) -> list[SessionDetail]:
    """Return session summaries, newest first."""
    where: list[str] = []
    params: list = []
    if source and source != "all":
        where.append("s.source_tool = ? OR (s.source_tool IS NULL AND s.llm_name = ?)")
        params.extend([source, source])
    if search:
        where.append(
            "(s.working_on LIKE ? OR s.summary LIKE ? OR s.llm_name LIKE ?)"
        )
        like = f"%{search}%"
        params.extend([like, like, like])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    q = f"""
        SELECT s.*,
               COALESCE(t.turn_count, 0) AS turn_count,
               COALESCE(t.tokens, 0) AS token_total,
               t.last_recorded,
               fu.first_user
        FROM sessions s
        LEFT JOIN (
            SELECT session_id,
                   COUNT(*) AS turn_count,
                   SUM(token_est) AS tokens,
                   MAX(recorded_at) AS last_recorded
            FROM conversation_turns GROUP BY session_id
        ) t ON t.session_id = s.id
        LEFT JOIN (
            SELECT session_id, content AS first_user
            FROM conversation_turns
            WHERE role = 'user'
            GROUP BY session_id
            HAVING MIN(turn_index)
        ) fu ON fu.session_id = s.id
        {where_sql}
        ORDER BY COALESCE(t.last_recorded, s.started_at) DESC
        LIMIT ?
    """  # nosec B608
    rows = conn.execute(q, [*params, limit]).fetchall()

    result: list[SessionDetail] = []
    for r in rows:
        files = sorted(_file_set(r))
        changes_rows = conn.execute(
            """SELECT DISTINCT file_path FROM changes WHERE session_id = ?""",
            (r["id"],),
        ).fetchall()
        files = sorted(set(files) | {c["file_path"] for c in changes_rows})
        first_user = (r["first_user"] or "").strip()
        if first_user:
            first_user = first_user.replace("\n", " ")[:140]
        result.append(
            SessionDetail(
                id=r["id"],
                llm_name=r["llm_name"],
                status=r["status"] or "",
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                working_on=r["working_on"] or "",
                summary=r["summary"] or "",
                source_tool=(r["source_tool"] if "source_tool" in r.keys() else None),
                source_id=(r["source_id"] if "source_id" in r.keys() else None),
                source_path=(r["source_path"] if "source_path" in r.keys() else None),
                turn_count=r["turn_count"] or 0,
                token_total=r["token_total"] or 0,
                files_touched=files,
                first_user_message=first_user,
                last_turn_at=r["last_recorded"],
            )
        )
    return result


def get_session_detail(
    conn: sqlite3.Connection, session_id: str
) -> Optional[SessionDetail]:
    """Return the detail for one session."""
    rows = list_sessions(conn, limit=1000)
    for r in rows:
        if r.id == session_id:
            return r
    return None


def get_session_turns(
    conn: sqlite3.Connection, session_id: str, limit: int = 500
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """SELECT role, content, token_est, turn_index, recorded_at
               FROM conversation_turns
               WHERE session_id = ?
               ORDER BY turn_index ASC
               LIMIT ?""",
            (session_id, limit),
        ).fetchall()
    )


def get_session_graph_scope(
    conn: sqlite3.Connection, session_id: str
) -> dict:
    """Return the subgraph of files/nodes touched by ``session_id``.

    Used by the VS Code sessions panel to visualise a session's footprint.

    Returns a dict with:
      - files:    list[str]   files modified during the session
      - node_ids: list[str]   qualified_names of nodes in those files
      - edges:    list[dict]  CONTAINS/CALLS/etc. edges between those nodes
    """
    detail = get_session_detail(conn, session_id)
    if detail is None:
        return {"files": [], "node_ids": [], "edges": []}

    files = list(detail.files_touched)
    if not files:
        return {"files": [], "node_ids": [], "edges": []}

    placeholders = ",".join("?" for _ in files)
    node_rows = conn.execute(
        f"""SELECT qualified_name, kind, name, file_path, line_start, line_end,
                   language, parent_name
             FROM code_nodes
             WHERE file_path IN ({placeholders})""",  # nosec B608
        files,
    ).fetchall()
    node_ids = {r["qualified_name"] for r in node_rows}

    edge_rows = []
    if node_ids:
        id_list = list(node_ids)
        placeholders_ids = ",".join("?" for _ in id_list)
        edge_rows = conn.execute(
            f"""SELECT kind, source_qualified, target_qualified, file_path, line
                  FROM code_edges
                 WHERE source_qualified IN ({placeholders_ids})
                    OR target_qualified IN ({placeholders_ids})""",  # nosec B608
            id_list + id_list,
        ).fetchall()

    return {
        "files": files,
        "nodes": [
            {
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "name": r["name"],
                "file_path": r["file_path"],
                "line_start": r["line_start"],
                "line_end": r["line_end"],
                "language": r["language"],
                "parent_name": r["parent_name"],
            }
            for r in node_rows
        ],
        "node_ids": sorted(node_ids),
        "edges": [
            {
                "kind": r["kind"],
                "source": r["source_qualified"],
                "target": r["target_qualified"],
                "file_path": r["file_path"],
                "line": r["line"],
            }
            for r in edge_rows
        ],
    }


def render_session_markdown(
    detail: SessionDetail,
    turns: list[sqlite3.Row],
    *,
    max_turns: int = 20,
) -> str:
    """Pretty-print a session's full detail + recent turns for humans."""
    lines: list[str] = []
    lines.append(f"# Session `{detail.id}`")
    src = detail.source_tool or "manual"
    lines.append(
        f"- **tool:** {src}"
        + (f" _(source id: `{detail.source_id}`)_" if detail.source_id else "")
    )
    lines.append(f"- **llm:** {detail.llm_name}")
    lines.append(f"- **status:** {detail.status}")
    lines.append(f"- **started:** {detail.started_at or '—'}")
    if detail.ended_at:
        lines.append(f"- **ended:** {detail.ended_at}")
    if detail.last_turn_at:
        lines.append(f"- **last turn:** {detail.last_turn_at}")
    lines.append(f"- **turns:** {detail.turn_count:,}")
    lines.append(f"- **tokens (est):** {detail.token_total:,}")
    if detail.working_on:
        lines.append(f"- **working on:** {detail.working_on}")
    if detail.summary:
        lines.append(f"- **summary:** {detail.summary}")
    if detail.files_touched:
        lines.append(f"- **files touched ({len(detail.files_touched)}):**")
        for f in detail.files_touched[:30]:
            lines.append(f"  - `{f}`")
        if len(detail.files_touched) > 30:
            lines.append(f"  - _+{len(detail.files_touched) - 30} more_")
    lines.append("")

    shown = turns[-max_turns:] if len(turns) > max_turns else turns
    if shown:
        lines.append(
            f"## Last {len(shown)} turn(s) "
            f"{'(of ' + str(len(turns)) + ')' if len(turns) > len(shown) else ''}"
        )
        for t in shown:
            c = (t["content"] or "").strip()
            if len(c) > 800:
                c = c[:800] + "…"
            ts = t["recorded_at"] or ""
            lines.append(f"### {t['role']} — _{ts}_")
            lines.append(c)
            lines.append("")

    return "\n".join(lines) + "\n"


def detail_to_dict(detail: SessionDetail) -> dict:
    return {
        "id": detail.id,
        "llm_name": detail.llm_name,
        "status": detail.status,
        "started_at": detail.started_at,
        "ended_at": detail.ended_at,
        "last_turn_at": detail.last_turn_at,
        "working_on": detail.working_on,
        "summary": detail.summary,
        "source_tool": detail.source_tool,
        "source_id": detail.source_id,
        "source_path": detail.source_path,
        "turn_count": detail.turn_count,
        "token_total": detail.token_total,
        "files_touched": detail.files_touched,
        "first_user_message": detail.first_user_message,
    }


def _relative_age(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = (datetime.now(t.tzinfo) - t).total_seconds()
    except (ValueError, OSError):
        return iso
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    if diff < 86400:
        return f"{int(diff / 3600)}h ago"
    return f"{int(diff / 86400)}d ago"
