"""Context packets for LLM/editor integrations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..schema import get_connection
from ..threads import get_thread_handoff_data, latest_thread
from ..turns import search_turns


def _project_meta(db: Path) -> dict:
    with get_connection(db) as conn:
        meta = dict(conn.execute("SELECT key, value FROM project_meta").fetchall())
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    return {"name": meta.get("name") or db.parent.parent.name, "meta": meta, "file_count": file_count}


def build_current_context(db: Path, budget_tokens: int = 8000) -> dict:
    tid = latest_thread(db)
    thread = get_thread_handoff_data(db, tid, budget_tokens=budget_tokens) if tid else None
    return {
        "project": _project_meta(db),
        "thread": thread,
        "turns": thread.get("turns", []) if thread else [],
        "budget": budget_tokens,
    }


def search_context(db: Path, query: str, limit: int = 10, thread_id: Optional[str] = None) -> dict:
    return {
        "project": _project_meta(db),
        "query": query,
        "results": search_turns(db, query, thread_id=thread_id, limit=limit),
    }


def render_context_markdown(packet: dict) -> str:
    project = packet.get("project", {})
    thread = packet.get("thread") or {}
    lines = [
        f"# Reza Context: {project.get('name', 'project')}",
        "",
        f"Files indexed: {project.get('file_count', 0)}",
    ]
    if thread:
        lines += [
            "",
            f"## Thread: {thread.get('title') or thread.get('id')}",
            f"ID: {thread.get('id')}",
            "",
            "## Recent Turns",
        ]
        for turn in packet.get("turns", []):
            lines.append(f"- **{turn['role']} [{turn['session_id']}]**: {turn['content']}")
    if "results" in packet:
        lines += ["", f"## Search: {packet.get('query', '')}"]
        for hit in packet.get("results", []):
            lines.append(f"- **{hit['role']} [{hit['session_id']}]**: {hit['content']}")
    return "\n".join(lines)
