"""File claim system — lets agents lock files to prevent parallel edit conflicts.

How it works:
  - An agent calls claim_file() before editing a file.
  - reza records the claim in file_locks (file_path → session_id).
  - If the watcher or git hook sees a write to a claimed file by a DIFFERENT
    session, it logs a conflict row and alerts immediately.
  - Agents release claims via release_file() or release_session_locks().
  - session end() auto-releases all locks for that session.

Conflict detection is also retroactive: check_conflict() can be called any time
a file is written to, even without an explicit claim, by comparing the writing
session against whoever currently holds the lock.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .schema import get_connection


# ─────────────────────────────────────────────
# Claiming & releasing
# ─────────────────────────────────────────────

def claim_file(db: Path, file_path: str, session_id: str) -> Dict:
    """Claim a file for exclusive editing by a session.

    Returns a dict with:
      - claimed: True if claim was granted
      - conflict: True if another session already holds the lock
      - owner: the session_id that currently holds the lock
      - llm: the LLM name of the owner
    """
    file_path = _normalize(file_path)

    with get_connection(db) as conn:
        existing = conn.execute(
            "SELECT session_id, llm_name FROM file_locks WHERE file_path = ?",
            (file_path,),
        ).fetchone()

        if existing:
            owner_id = existing["session_id"]
            if owner_id == session_id:
                # Already owned by this session — idempotent
                return {"claimed": True, "conflict": False, "owner": session_id, "llm": existing["llm_name"]}

            # Someone else holds it — log a conflict
            our_session = conn.execute(
                "SELECT llm_name FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            their_session = conn.execute(
                "SELECT llm_name FROM sessions WHERE id = ?", (owner_id,)
            ).fetchone()

            our_llm = our_session["llm_name"] if our_session else "unknown"
            their_llm = their_session["llm_name"] if their_session else "unknown"

            conn.execute(
                """
                INSERT INTO conflicts (file_path, session_a, session_b, llm_a, llm_b)
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_path, owner_id, session_id, their_llm, our_llm),
            )
            return {
                "claimed": False,
                "conflict": True,
                "owner": owner_id,
                "llm": their_llm,
            }

        # No existing lock — grant it
        our_session = conn.execute(
            "SELECT llm_name FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        llm_name = our_session["llm_name"] if our_session else "unknown"

        conn.execute(
            """
            INSERT OR REPLACE INTO file_locks (file_path, session_id, llm_name, claimed_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (file_path, session_id, llm_name),
        )
        return {"claimed": True, "conflict": False, "owner": session_id, "llm": llm_name}


def release_file(db: Path, file_path: str, session_id: Optional[str] = None) -> bool:
    """Release a file lock.

    If session_id is provided, only releases if this session owns the lock.
    Returns True if a lock was removed.
    """
    file_path = _normalize(file_path)
    with get_connection(db) as conn:
        if session_id:
            result = conn.execute(
                "DELETE FROM file_locks WHERE file_path = ? AND session_id = ?",
                (file_path, session_id),
            )
        else:
            result = conn.execute(
                "DELETE FROM file_locks WHERE file_path = ?",
                (file_path,),
            )
        return result.rowcount > 0


def release_session_locks(db: Path, session_id: str) -> int:
    """Release ALL file locks held by a session. Returns number of locks released."""
    with get_connection(db) as conn:
        result = conn.execute(
            "DELETE FROM file_locks WHERE session_id = ?",
            (session_id,),
        )
        return result.rowcount


def get_lock(db: Path, file_path: str) -> Optional[Dict]:
    """Return the current lock info for a file, or None if not locked."""
    file_path = _normalize(file_path)
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT * FROM file_locks WHERE file_path = ?",
            (file_path,),
        ).fetchone()
    return dict(row) if row else None


def list_locks(db: Path, session_id: Optional[str] = None) -> List[Dict]:
    """List all active file locks, optionally filtered by session."""
    with get_connection(db) as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM file_locks WHERE session_id = ? ORDER BY claimed_at",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM file_locks ORDER BY claimed_at"
            ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Conflict detection
# ─────────────────────────────────────────────

def check_conflict(db: Path, file_path: str, writing_session_id: Optional[str]) -> Optional[Dict]:
    """Check if writing to file_path conflicts with an existing lock.

    Called automatically by the watcher and git hook on every file write.
    Returns a conflict dict if a conflict was detected and logged, else None.
    """
    if not writing_session_id:
        return None

    file_path = _normalize(file_path)

    with get_connection(db) as conn:
        lock = conn.execute(
            "SELECT session_id, llm_name FROM file_locks WHERE file_path = ?",
            (file_path,),
        ).fetchone()

        if not lock:
            return None  # File not locked — no conflict

        lock_owner = lock["session_id"]
        if lock_owner == writing_session_id:
            return None  # Same session — fine

        # Different session writing to a locked file — conflict!
        writing_session = conn.execute(
            "SELECT llm_name FROM sessions WHERE id = ?", (writing_session_id,)
        ).fetchone()
        writing_llm = writing_session["llm_name"] if writing_session else "unknown"

        conn.execute(
            """
            INSERT INTO conflicts (file_path, session_a, session_b, llm_a, llm_b)
            VALUES (?, ?, ?, ?, ?)
            """,
            (file_path, lock_owner, writing_session_id, lock["llm_name"], writing_llm),
        )

        return {
            "file_path": file_path,
            "lock_owner": lock_owner,
            "lock_owner_llm": lock["llm_name"],
            "writing_session": writing_session_id,
            "writing_llm": writing_llm,
        }


def list_conflicts(db: Path, unresolved_only: bool = True) -> List[Dict]:
    """Return all conflicts, optionally filtered to unresolved ones."""
    with get_connection(db) as conn:
        if unresolved_only:
            rows = conn.execute(
                "SELECT * FROM conflicts WHERE resolved = 0 ORDER BY detected_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conflicts ORDER BY detected_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def resolve_conflict(db: Path, conflict_id: int, resolved_by: str = "") -> bool:
    """Mark a conflict as resolved. Returns True if the conflict was found."""
    with get_connection(db) as conn:
        result = conn.execute(
            """
            UPDATE conflicts
            SET resolved = 1, resolved_at = datetime('now'), resolved_by = ?
            WHERE id = ? AND resolved = 0
            """,
            (resolved_by, conflict_id),
        )
        return result.rowcount > 0


def resolve_file_conflicts(db: Path, file_path: str, resolved_by: str = "") -> int:
    """Resolve all open conflicts for a specific file. Returns count resolved."""
    file_path = _normalize(file_path)
    with get_connection(db) as conn:
        result = conn.execute(
            """
            UPDATE conflicts
            SET resolved = 1, resolved_at = datetime('now'), resolved_by = ?
            WHERE file_path = ? AND resolved = 0
            """,
            (resolved_by, file_path),
        )
        return result.rowcount


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _normalize(file_path: str) -> str:
    """Normalize path separators."""
    return file_path.replace("\\", "/")
