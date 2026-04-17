"""Codex rollout ingestion.

Codex stores one session per "rollout" file at:
    ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<TIMESTAMP>-<UUID>.jsonl

The first line is always a ``session_meta`` event with::

    { "type": "session_meta",
      "payload": { "id": "...", "timestamp": "...", "cwd": "...", "cli_version": "..." } }

Subsequent ``response_item`` events carry the actual turns::

    { "type": "response_item",
      "payload": { "role": "user", "content": [ {type: 'input_text', text: ...}, ... ] } }

We match a rollout to the current project by comparing ``session_meta.cwd``
(case-insensitive, trailing slash forgiving).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ._common import ParsedSession, ParsedTurn, cwd_matches, upsert_imported_session


# File-path regex: absolute Windows path OR forward-slash path ending in a
# known source/config extension. Used to salvage file touches from Codex
# function_call arguments (a string blob) and message bodies.
#
# Note: Windows paths frequently contain spaces (``C:\Users\Suweb Reza\…``)
# so we allow internal spaces inside segments. We still require a known
# extension to avoid swallowing arbitrary tokens.
_KNOWN_EXTS = (
    "py ts tsx js jsx json md html css yml yaml toml rs go java c h hpp cpp "
    "sh ps1 sql xml ini cfg lock"
).split()
_EXT_ALT = "|".join(re.escape(e) for e in _KNOWN_EXTS)

_PATH_RE = re.compile(
    r"""(?:
        [A-Za-z]:\\(?:[^\\'",<>|:*?\n]+\\)+[^\\'",<>|:*?\n]+?\.(?:""" + _EXT_ALT + r""")
      |
        (?:\./)?(?:[\w\-.]+/)+[\w\-.]+\.(?:""" + _EXT_ALT + r""")
    )""",
    re.VERBOSE | re.IGNORECASE,
)


def _harvest_paths(text: str, sink: set[str]) -> None:
    if not text:
        return
    for m in _PATH_RE.findall(text):
        sink.add(m)


_CODEX_SESSIONS = Path.home() / ".codex" / "sessions"


def discover_codex_rollouts(
    project_dir: Optional[Path] = None, *, max_files: int = 2000
) -> list[Path]:
    """List all rollout-*.jsonl files, optionally filtered by project cwd.

    ``max_files`` guards against accidentally scanning huge history directories.
    """
    if not _CODEX_SESSIONS.exists():
        return []
    files = sorted(_CODEX_SESSIONS.rglob("rollout-*.jsonl"))
    if len(files) > max_files:
        files = files[-max_files:]  # most recent
    if project_dir is None:
        return files
    matching: list[Path] = []
    for f in files:
        cwd = _peek_cwd(f)
        if cwd and cwd_matches(cwd, Path(project_dir)):
            matching.append(f)
    return matching


def _peek_cwd(path: Path) -> Optional[str]:
    """Return ``session_meta.payload.cwd`` from the first line, or None."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            line = fh.readline()
    except OSError:
        return None
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if obj.get("type") != "session_meta":
        return None
    return (obj.get("payload") or {}).get("cwd")


def _flatten_codex_content(content) -> str:
    """Normalize Codex ``content`` arrays into plain text."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype in ("input_text", "output_text", "text"):
            txt = (block.get("text") or "").strip()
            if txt:
                parts.append(txt)
        elif btype == "image":
            parts.append("[image]")
    return "\n".join(parts).strip()


_SYSTEMISH_PREFIXES = (
    "<environment_context>",
    "<INSTRUCTIONS>",
    "# AGENTS.md",
    "<user_instructions>",
    "<system",
)


def _looks_like_system_preamble(text: str) -> bool:
    head = text.lstrip()[:40].lower()
    return any(head.startswith(p.lower()) for p in _SYSTEMISH_PREFIXES)


def _parse_rollout(path: Path) -> Optional[ParsedSession]:
    meta: Optional[dict] = None
    turns: list[ParsedTurn] = []
    first_user_text = ""
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

                t = obj.get("type")
                pl = obj.get("payload") or {}
                if t == "session_meta" and meta is None:
                    meta = pl
                    continue

                if t == "response_item":
                    pt = pl.get("type")
                    if pt in ("function_call", "custom_tool_call"):
                        args = pl.get("arguments")
                        if isinstance(args, str):
                            # Raw arg blob still has JSON-escaped backslashes;
                            # decode to get single-backslash Windows paths.
                            try:
                                parsed_args = json.loads(args)
                            except (ValueError, TypeError):
                                parsed_args = None
                            if isinstance(parsed_args, dict):
                                for v in parsed_args.values():
                                    if isinstance(v, str):
                                        _harvest_paths(v, files_touched)
                            else:
                                _harvest_paths(args, files_touched)
                        continue

                    role = pl.get("role")
                    if role not in ("user", "assistant", "system"):
                        continue
                    content = _flatten_codex_content(pl.get("content"))
                    if not content:
                        continue
                    _harvest_paths(content, files_touched)
                    if role == "user" and not first_user_text and not _looks_like_system_preamble(content):
                        first_user_text = content[:140]
                    turns.append(ParsedTurn(role=role, content=content))
    except OSError:
        return None

    if not turns:
        return None

    meta = meta or {}
    source_id = meta.get("id") or path.stem
    started_at = meta.get("timestamp")
    if not started_at:
        started_at = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")

    cli_version = meta.get("cli_version") or ""
    llm_name = f"codex-{cli_version}" if cli_version else "codex"
    project_cwd = meta.get("cwd")

    working_on = first_user_text.replace("\n", " ").strip()
    if len(working_on) > 100:
        working_on = working_on[:97] + "..."

    # Narrow harvested paths to ones inside the session's project cwd so
    # we don't record noise like SKILL.md files from ~/.codex/.
    cwd_norm = str(Path(project_cwd).resolve()).lower() if project_cwd else ""
    filtered: list[str] = []
    for f in sorted(files_touched):
        try:
            ap = str(Path(f).resolve()).lower()
        except (OSError, ValueError):
            ap = f.lower()
        if cwd_norm and ap.startswith(cwd_norm):
            # Store as project-relative paths for consistency with the graph
            try:
                rel = Path(f).resolve().relative_to(Path(project_cwd).resolve())
                filtered.append(str(rel).replace("\\", "/"))
            except (OSError, ValueError):
                filtered.append(f)
        elif not cwd_norm:
            filtered.append(f)

    return ParsedSession(
        source_tool="codex",
        source_id=str(source_id),
        source_path=str(path),
        llm_name=llm_name,
        started_at=started_at,
        working_on=working_on,
        project_cwd=project_cwd,
        turns=turns,
        files_touched=filtered,
    )


def sync_codex_project(
    conn: sqlite3.Connection, project_dir: Path
) -> dict:
    """Ingest every Codex rollout whose ``cwd`` matches ``project_dir``.

    Idempotent. Returns summary stats.
    """
    rollouts = discover_codex_rollouts(project_dir)
    result = {
        "tool": "codex",
        "project_dir": str(project_dir),
        "rollouts_found": len(rollouts),
        "sessions_imported": 0,
        "sessions_updated": 0,
        "turns_inserted": 0,
    }
    if not rollouts:
        return result

    conn.execute("BEGIN IMMEDIATE")
    try:
        for r in rollouts:
            parsed = _parse_rollout(r)
            if parsed is None:
                continue
            existed_before = conn.execute(
                "SELECT 1 FROM sessions WHERE source_tool='codex' AND source_path=?",
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
