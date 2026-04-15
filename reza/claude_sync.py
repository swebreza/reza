"""Claude Code conversation sync — reads Claude's .jsonl files and syncs turns to reza.

This module is the engine behind `reza sync-claude`. It is designed to be called
by a Claude Code Stop hook after every response, so turns are saved even when
Claude hits its context limit and has no tokens left to call reza itself.

Claude .jsonl format (one JSON object per line):
  User turn:      {"type": "user",      "message": {"role": "user",      "content": "text..."}, "sessionId": "...", ...}
  Assistant turn: {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "..."}]}, ...}

The sync is fully idempotent: it counts existing turns in reza and only inserts
new ones (by absolute position in the jsonl file), so calling it on every hook
fire is safe and cheap.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from .schema import get_connection
from .session import start_session
from .turns import add_turns_bulk, list_turns


def parse_jsonl(jsonl_path: Path) -> List[Dict]:
    """Parse Claude's .jsonl conversation file into an ordered list of turn dicts.

    Each dict has keys: role ('user'|'assistant'), content (str).
    Lines that are not conversation turns (tool use, sidechain, etc.) are skipped.
    """
    turns = []
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Conversation file not found: {jsonl_path}")
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip non-message objects (summaries, meta events, etc.)
            if obj.get("type") not in ("user", "assistant"):
                continue

            # Skip sidechain entries
            if obj.get("isSidechain"):
                continue

            msg = obj.get("message", {})
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue

            raw = msg.get("content", "")

            # User turns: content is a plain string
            if isinstance(raw, str):
                content = raw.strip()
            # Assistant turns: content is [{type:"text", text:"..."}, ...]
            elif isinstance(raw, list):
                parts = []
                for block in raw:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            parts.append(text)
                content = "\n".join(parts).strip()
            else:
                continue

            if not content:
                continue

            turns.append({"role": role, "content": content})

    return turns


def _parse_llm_from_session_path(jsonl_path: Path) -> str:
    """Try to derive an llm_name from the parent directory path."""
    # Claude stores sessions under ~/.claude/projects/PROJECT_HASH/SESSION_ID.jsonl
    # The parent dir name is a project hash, not a useful name — just return 'claude'
    name = jsonl_path.stem  # session UUID
    # If the filename looks like an llm-prefixed name (e.g. codex-abc.jsonl) use it
    m = re.match(r'^([a-z][a-z0-9-]+?)-[0-9a-f]{6,}', name, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return "claude"


def sync_claude_session(
    db: Path,
    jsonl_path: Path,
    reza_session_id: Optional[str] = None,
) -> Dict:
    """Sync turns from a Claude .jsonl file to reza.

    Resolves which reza session to use:
      1. reza_session_id if provided
      2. ID stored in .reza/current_session (written by `reza session start`)
      3. Most recent active or interrupted session
      4. Auto-creates a new session with llm_name='claude' if none found

    Idempotent: already-synced turns (by count) are skipped; only appends new ones.

    Returns:
        dict with keys: session_id, synced (int), skipped (int), total (int)
    """
    db = Path(db)
    jsonl_path = Path(jsonl_path)

    # 1. Parse all turns from the .jsonl file
    all_turns = parse_jsonl(jsonl_path)
    total = len(all_turns)

    if total == 0:
        return {"session_id": reza_session_id or "unknown", "synced": 0, "skipped": 0, "total": 0}

    # 2. Resolve session ID
    sid = reza_session_id
    if not sid:
        # Try .reza/current_session
        db_dir = db.parent
        current_session_file = db_dir / "current_session"
        if current_session_file.exists():
            sid = current_session_file.read_text(encoding="utf-8").strip()

    if not sid:
        # Try most recent active/interrupted session that belongs to Claude.
        # Restrict to llm_name starting with 'claude' or 'unknown' (auto-created) to
        # avoid hijacking sessions owned by Cursor, Aider, Codex, etc.
        with get_connection(db) as conn:
            row = conn.execute(
                """
                SELECT id FROM sessions
                WHERE status IN ('active', 'interrupted')
                  AND (llm_name LIKE 'claude%' OR llm_name = 'unknown')
                ORDER BY started_at DESC LIMIT 1
                """
            ).fetchone()
        if row:
            sid = row["id"]

    if not sid:
        # Auto-create
        llm_name = _parse_llm_from_session_path(jsonl_path)
        sid = start_session(db, llm_name, working_on="auto-synced from Claude Code")

    # 3. Check how many turns are already stored (idempotency)
    existing = list_turns(db, sid)
    already = len(existing)

    if already >= total:
        return {"session_id": sid, "synced": 0, "skipped": total, "total": total}

    # 4. Only insert the new tail
    new_turns = all_turns[already:]
    add_turns_bulk(db, sid, new_turns)

    return {
        "session_id": sid,
        "synced": len(new_turns),
        "skipped": already,
        "total": total,
    }
