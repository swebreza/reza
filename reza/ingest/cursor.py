"""Cursor agent-transcript ingestion.

Cursor stores chat history at:
    ~/.cursor/projects/<project-slug>/agent-transcripts/<uuid>.jsonl

Format (one JSON object per line):
    { "role": "user",       "message": { "content": "<str or blocks>" } }
    { "role": "assistant",  "message": { "content": [ {type:'text', text:...}, ... ] } }

The project-slug is a sanitized form of the workspace absolute path, e.g.::

    c:\\Users\\Suweb Reza\\onefolder\\Desktop\\reza
                ↓
    c-Users-Suweb-Reza-onefolder-Desktop-reza

We match a transcript to a project by slugifying the target project path the
same way and looking for that directory (case-insensitive).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from ._common import ParsedSession, ParsedTurn, upsert_imported_session


# Tool-use input fields that typically carry a file path
_PATH_FIELDS = (
    "path", "file_path", "target_file", "filePath",
    "relativePath", "relative_path", "notebook_path", "file",
)


_CURSOR_PROJECTS = Path.home() / ".cursor" / "projects"


def _slug_for(project_dir: Path) -> str:
    """Convert ``C:\\foo\\bar`` → ``c-foo-bar`` the way Cursor does."""
    s = str(project_dir.resolve())
    # Drop drive colon, normalise separators, replace spaces
    s = re.sub(r"^([A-Za-z]):", r"\1", s)
    s = s.replace("\\", "-").replace("/", "-").replace(" ", "-")
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _candidate_project_dirs(project_dir: Path) -> list[Path]:
    """Return possible Cursor project folders matching the given workspace."""
    if not _CURSOR_PROJECTS.exists():
        return []
    target_slug = _slug_for(project_dir).lower()
    matches: list[Path] = []
    for child in _CURSOR_PROJECTS.iterdir():
        if not child.is_dir():
            continue
        if child.name.lower() == target_slug:
            matches.append(child)
    return matches


def discover_cursor_transcripts(project_dir: Path) -> list[Path]:
    """Return .jsonl transcripts for ``project_dir`` (if any)."""
    files: list[Path] = []
    for pd in _candidate_project_dirs(project_dir):
        at = pd / "agent-transcripts"
        if at.exists():
            files.extend(sorted(at.rglob("*.jsonl")))
    return files


def _flatten_content(content, files_out: Optional[set] = None) -> str:
    """Normalize Cursor's content shapes into plain text.

    If ``files_out`` is a mutable set, file paths referenced by any
    ``tool_use`` block are added to it (useful for computing a session's
    files_touched list).
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    parts.append(text)
            elif btype == "tool_use":
                name = block.get("name", "tool")
                parts.append(f"[tool_use: {name}]")
                inp = block.get("input")
                if files_out is not None and isinstance(inp, dict):
                    for k in _PATH_FIELDS:
                        v = inp.get(k)
                        if isinstance(v, str) and v:
                            files_out.add(v)
            elif btype == "tool_result":
                tr = block.get("content") or ""
                if isinstance(tr, list):
                    tr = _flatten_content(tr, files_out)
                parts.append(f"[tool_result] {str(tr)[:400]}")
        return "\n".join(parts).strip()
    return ""


def _parse_transcript(path: Path) -> Optional[ParsedSession]:
    """Parse one Cursor transcript .jsonl into a :class:`ParsedSession`."""
    turns: list[ParsedTurn] = []
    first_user_text = ""
    project_cwd: Optional[str] = None
    files_touched: set[str] = set()

    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                role = obj.get("role")
                if role not in ("user", "assistant", "system"):
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                content = _flatten_content(msg.get("content"), files_out=files_touched)
                if not content:
                    continue
                if role == "user" and not first_user_text:
                    first_user_text = content[:140]
                turns.append(ParsedTurn(role=role, content=content))
    except OSError:
        return None

    if not turns:
        return None

    started = datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    ).isoformat().replace("+00:00", "Z")

    working_on = first_user_text.replace("\n", " ").strip()
    if len(working_on) > 100:
        working_on = working_on[:97] + "..."

    return ParsedSession(
        source_tool="cursor",
        source_id=path.stem,
        source_path=str(path),
        llm_name="cursor",
        started_at=started,
        working_on=working_on,
        project_cwd=project_cwd,
        turns=turns,
        files_touched=sorted(files_touched),
    )


def sync_cursor_project(
    conn: sqlite3.Connection, project_dir: Path
) -> dict:
    """Ingest every Cursor transcript for the given project.

    Idempotent — re-running only appends new turns.
    Returns summary stats.
    """
    transcripts = discover_cursor_transcripts(project_dir)
    result = {
        "tool": "cursor",
        "project_dir": str(project_dir),
        "transcripts_found": len(transcripts),
        "sessions_imported": 0,
        "sessions_updated": 0,
        "turns_inserted": 0,
    }
    if not transcripts:
        return result

    conn.execute("BEGIN IMMEDIATE")
    try:
        for t in transcripts:
            parsed = _parse_transcript(t)
            if parsed is None:
                continue
            existed_before = conn.execute(
                "SELECT 1 FROM sessions WHERE source_tool='cursor' AND source_path=?",
                (parsed.source_path,),
            ).fetchone()
            _, inserted, _ = upsert_imported_session(conn, parsed)
            if existed_before:
                result["sessions_updated"] += 1
            else:
                result["sessions_imported"] += 1
            result["turns_inserted"] += inserted
        conn.commit()
    except BaseException:
        conn.rollback()
        raise

    return result
