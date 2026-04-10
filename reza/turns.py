"""Conversation turn storage and budget-aware retrieval."""

from pathlib import Path
from typing import Dict, List

from .schema import get_connection


def add_turn(
    db: Path,
    session_id: str,
    role: str,
    content: str,
    token_est: int = 0,
    turn_index: int = 0,
) -> int:
    """Append one turn. Returns the new row id.

    Raises ValueError for invalid role or unknown session_id.
    Auto-estimates token_est as len(content)//4 when token_est is 0.
    Caller is responsible for supplying a unique turn_index; use add_turns_bulk to auto-assign.
    """
    if role not in ("user", "assistant", "system"):
        raise ValueError(f"Invalid role: {role!r}. Must be user, assistant, or system.")
    if not token_est:
        token_est = len(content) // 4
    with get_connection(db) as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise ValueError(f"Session not found: {session_id}")
        cur = conn.execute(
            """
            INSERT INTO conversation_turns (session_id, role, content, token_est, turn_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, token_est, turn_index),
        )
        return cur.lastrowid


def add_turns_bulk(db: Path, session_id: str, turns: List[Dict]) -> int:
    """Batch insert turns from a list of dicts with keys: role, content, token_est (optional).

    turn_index is assigned automatically, continuing from the highest existing index.
    Returns number of turns inserted.
    Raises ValueError for unknown session_id.
    """
    if not turns:
        return 0
    with get_connection(db) as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise ValueError(f"Session not found: {session_id}")
        max_idx = conn.execute(
            "SELECT COALESCE(MAX(turn_index), -1) FROM conversation_turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        next_idx = max_idx + 1
        for i, turn in enumerate(turns):
            role = turn["role"]
            if role not in ("user", "assistant", "system"):
                raise ValueError(
                    f"Invalid role at index {i}: {role!r}. Must be user, assistant, or system."
                )
            content = turn["content"]
            token_est = turn.get("token_est") or (len(content) // 4)
            conn.execute(
                """
                INSERT INTO conversation_turns (session_id, role, content, token_est, turn_index)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, token_est, next_idx + i),
            )
    return len(turns)


def list_turns(db: Path, session_id: str) -> List[Dict]:
    """Return all turns for a session ordered by turn_index ascending."""
    with get_connection(db) as conn:
        rows = conn.execute(
            "SELECT * FROM conversation_turns WHERE session_id = ? ORDER BY turn_index ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def turns_within_budget(db: Path, session_id: str, budget_tokens: int) -> List[Dict]:
    """Return the most-recent turns whose cumulative token_est fits within budget_tokens.

    Fills from the most-recent turn backward; stops as soon as a turn would exceed the budget, even if older turns would fit individually. Result is returned in chronological order.
    """
    all_turns = list_turns(db, session_id)
    if not all_turns:
        return []
    result = []
    total = 0
    for turn in reversed(all_turns):
        cost = turn["token_est"] or (len(turn["content"]) // 4)
        if total + cost > budget_tokens:
            break
        result.append(turn)
        total += cost
    return list(reversed(result))
