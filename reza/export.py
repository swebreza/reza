"""Export context to markdown or JSON — for tools without SQLite access."""

import json
from datetime import datetime
from pathlib import Path

from .schema import get_connection


def _load_data(db: Path) -> dict:
    with get_connection(db) as conn:
        meta = dict(conn.execute("SELECT key, value FROM project_meta").fetchall())
        files = [dict(r) for r in conn.execute(
            "SELECT path, file_type, line_count, purpose, tags, llm_notes FROM files ORDER BY path"
        ).fetchall()]
        sessions = [dict(r) for r in conn.execute(
            "SELECT id, llm_name, status, working_on, summary, conversation_context, "
            "files_modified, started_at FROM sessions "
            "WHERE status IN ('active', 'interrupted') ORDER BY started_at DESC"
        ).fetchall()]
        recent_changes = [dict(r) for r in conn.execute(
            "SELECT file_path, change_type, changed_at, session_id FROM changes "
            "ORDER BY changed_at DESC LIMIT 50"
        ).fetchall()]
    return {
        "meta": meta,
        "files": files,
        "active_sessions": sessions,
        "recent_changes": recent_changes,
        "exported_at": datetime.now().isoformat(),
    }


def export_json(db: Path, output_path: str):
    """Export full context as JSON."""
    data = _load_data(db)
    Path(output_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_markdown(db: Path, output_path: str):
    """Export full context as a human-readable markdown file."""
    data = _load_data(db)
    meta = data["meta"]
    lines = [
        "# Project Context (reza)",
        "",
        f"**Generated**: {data['exported_at']}  ",
        f"**Project**: {meta.get('name', 'unknown')}  ",
        f"**Language**: {meta.get('language', 'unknown')}  ",
        f"**Framework**: {meta.get('framework', 'unknown')}  ",
        f"**Total files**: {len(data['files'])}",
        "",
    ]

    # Active sessions
    if data["active_sessions"]:
        lines.append("## Active / Interrupted Sessions")
        lines.append("")
        for s in data["active_sessions"]:
            lines.append(f"### [{s['llm_name']}] `{s['id']}` — {s['status']}")
            if s["working_on"]:
                lines.append(f"**Working on**: {s['working_on']}")
            if s["summary"]:
                lines.append(f"**Summary**: {s['summary']}")
            if s["conversation_context"]:
                lines.append(f"**Context**:")
                lines.append(f"```")
                lines.append(s["conversation_context"])
                lines.append(f"```")
            if s["files_modified"]:
                lines.append(f"**Files modified**: {s['files_modified']}")
            lines.append("")

    # File listing by type
    lines.append("## Files")
    lines.append("")
    by_type: dict = {}
    for f in data["files"]:
        t = f["file_type"] or "other"
        by_type.setdefault(t, []).append(f)

    for ext, files in sorted(by_type.items(), key=lambda x: -len(x[1])):
        lines.append(f"### .{ext} ({len(files)} files)")
        for f in files:
            purpose_str = f" — {f['purpose']}" if f.get("purpose") else ""
            lines.append(f"- `{f['path']}`{purpose_str}")
        lines.append("")

    # Recent changes
    if data["recent_changes"]:
        lines.append("## Recent Changes (last 50)")
        lines.append("")
        lines.append("| File | Type | When | Session |")
        lines.append("|------|------|------|---------|")
        for c in data["recent_changes"]:
            lines.append(
                f"| `{c['file_path']}` | {c['change_type']} "
                f"| {(c['changed_at'] or '')[:16]} | {c['session_id'] or ''} |"
            )
        lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def export_context(db: Path, output_path: str):
    """Export a compact context file optimized for LLM prompt injection.

    This is the format recommended for tools that can include a file
    in their system prompt (Aider's --read, Cursor's @file, etc.).
    """
    data = _load_data(db)
    meta = data["meta"]
    lines = [
        f"<!-- reza context | {data['exported_at']} -->",
        f"# {meta.get('name', 'project')} — LLM Context",
        "",
        f"> Language: {meta.get('language', '?')} | "
        f"Framework: {meta.get('framework', '?')} | "
        f"Files: {len(data['files'])}",
        "",
    ]

    # Interrupted sessions first — most critical for handoff
    interrupted = [s for s in data["active_sessions"] if s["status"] == "interrupted"]
    if interrupted:
        lines.append("## Interrupted Sessions (pick these up)")
        for s in interrupted:
            lines.append(f"- **{s['llm_name']}** `{s['id']}`: {s['working_on'] or '(no task)'}")
            if s["summary"]:
                lines.append(f"  Summary: {s['summary']}")
            if s["conversation_context"]:
                lines.append(f"  Context: {s['conversation_context'][:300]}...")
        lines.append("")

    # Key files — those with purpose descriptions
    with_purpose = [f for f in data["files"] if f.get("purpose")]
    if with_purpose:
        lines.append("## Key Files")
        for f in with_purpose[:60]:
            lines.append(f"- `{f['path']}` — {f['purpose']}")
        if len(with_purpose) > 60:
            lines.append(f"- … and {len(with_purpose) - 60} more")
        lines.append("")

    # File tree summary
    by_type: dict = {}
    for f in data["files"]:
        t = f["file_type"] or "other"
        by_type.setdefault(t, 0)
        by_type[t] += 1

    lines.append("## File Breakdown")
    for ext, count in sorted(by_type.items(), key=lambda x: -x[1])[:12]:
        lines.append(f"- `.{ext}`: {count} files")
    lines.append("")
    lines.append("<!-- end reza context -->")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
