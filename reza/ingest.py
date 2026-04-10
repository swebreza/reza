"""Transcript file ingestion — parses .md and .json files into conversation turns."""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .schema import get_connection
from .session import start_session
from .turns import add_turns_bulk


def parse_json_transcript(file_path: str) -> List[Dict]:
    """Parse a JSON transcript. Expected format: list of {role, content} dicts.

    Raises ValueError if not a JSON array or if any role is invalid.
    """
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")
    turns = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Turn {i} is not a dict")
        role = item.get("role", "")
        content = item.get("content", "")
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Turn {i} has invalid role: {role!r}")
        turns.append({"role": role, "content": content})
    return turns


def parse_markdown_transcript(file_path: str) -> List[Dict]:
    """Parse a markdown transcript delimited by HTML comment role markers.

    Marker format: <!-- role: user --> (case-insensitive).
    Empty turns are skipped.
    If no markers found, the entire file is returned as a single assistant turn (with a warning).
    """
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    marker_pattern = re.compile(r"<!--\s*role:\s*(user|assistant|system)\s*-->", re.IGNORECASE)
    matches = list(marker_pattern.finditer(content))
    if not matches:
        print(
            f"Warning: no role markers found in {file_path}. Treating as single assistant turn.",
            file=sys.stderr,
        )
        return [{"role": "assistant", "content": content.strip()}]
    turns = []
    for i, match in enumerate(matches):
        role = match.group(1).lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        text = content[start:end].strip()
        if text:
            turns.append({"role": role, "content": text})
    return turns


def _parse_llm_from_filename(file_path: str) -> str:
    """Derive llm_name from filename prefix.

    'codex-20260410.md' -> 'codex', 'claude-abc.json' -> 'claude', '12345.md' -> 'unknown'.
    """
    stem = Path(file_path).stem
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9_]*)[-_]\d", stem)
    if m:
        return m.group(1).lower()
    parts = re.split(r"[-_]", stem)
    first = parts[0] if parts else ""
    if first and first[0].isalpha():
        return first.lower()
    return "unknown"


def ingest_file(
    db: Path,
    file_path: str,
    session_id: Optional[str] = None,
) -> str:
    """Parse and ingest a transcript file into the database.

    Creates a new session (llm_name derived from filename) if session_id is None.
    Records the file in handoff_drops to prevent re-import.
    Returns the session_id used.

    Raises:
        FileNotFoundError: file does not exist
        ValueError: unsupported format or malformed content
        RuntimeError: file was already ingested
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    abs_path = str(path.resolve())

    with get_connection(db) as conn:
        existing = conn.execute(
            "SELECT id FROM handoff_drops WHERE file_path = ?", (abs_path,)
        ).fetchone()
    if existing:
        raise RuntimeError(f"Already ingested: {file_path}")

    ext = path.suffix.lower()
    if ext == ".json":
        turns = parse_json_transcript(str(path))
    elif ext == ".md":
        turns = parse_markdown_transcript(str(path))
    else:
        raise ValueError(f"Unsupported format: {ext!r}. Use .md or .json")

    if session_id is None:
        llm_name = _parse_llm_from_filename(str(path))
        session_id = start_session(db, llm_name, f"Ingested from {path.name}")

    add_turns_bulk(db, session_id, turns)

    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO handoff_drops (file_path, session_id) VALUES (?, ?)",
            (abs_path, session_id),
        )

    return session_id
