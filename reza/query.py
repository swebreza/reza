"""Query functions — overview, file search, recent changes, sessions."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import get_connection


def get_overview(db: Path) -> Dict[str, Any]:
    """Return a full project overview: meta, active sessions, file breakdown."""
    with get_connection(db) as conn:
        meta = dict(conn.execute("SELECT key, value FROM project_meta").fetchall())
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

        active_sessions = [
            dict(r) for r in conn.execute(
                "SELECT id, llm_name, working_on, started_at FROM sessions "
                "WHERE status IN ('active', 'interrupted') ORDER BY started_at DESC"
            ).fetchall()
        ]

        # Group files by type with sample purposes
        file_tree = []
        ext_rows = conn.execute(
            "SELECT file_type, COUNT(*) as cnt FROM files GROUP BY file_type ORDER BY cnt DESC LIMIT 20"
        ).fetchall()
        for row in ext_rows:
            purposes = conn.execute(
                "SELECT purpose FROM files WHERE file_type = ? AND purpose IS NOT NULL LIMIT 5",
                (row["file_type"],),
            ).fetchall()
            purpose_str = " | ".join(p["purpose"] for p in purposes if p["purpose"])
            file_tree.append((row["file_type"], row["cnt"], purpose_str))

    return {
        "meta": meta,
        "file_count": file_count,
        "active_sessions": active_sessions,
        "file_tree": file_tree,
    }


def find_files(db: Path, query: str) -> List[Dict]:
    """Search files by path substring or purpose keyword."""
    pattern = f"%{query}%"
    with get_connection(db) as conn:
        rows = conn.execute(
            """
            SELECT path, file_type, line_count, purpose, llm_notes
            FROM files
            WHERE path LIKE ? OR purpose LIKE ? OR tags LIKE ?
            ORDER BY
                CASE WHEN path LIKE ? THEN 0 ELSE 1 END,
                line_count DESC
            LIMIT 50
            """,
            (pattern, pattern, pattern, pattern),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_changes(db: Path, limit: int = 30) -> List[Dict]:
    """Return the most recent file changes recorded in the DB."""
    with get_connection(db) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.file_path, c.change_type, c.session_id,
                   c.changed_at, c.diff_summary,
                   s.llm_name
            FROM changes c
            LEFT JOIN sessions s ON c.session_id = s.id
            ORDER BY c.changed_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_sessions_list(db: Path, status: Optional[str] = None) -> List[Dict]:
    """Return sessions, filtered by status if provided."""
    with get_connection(db) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status = ? ORDER BY started_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status IN ('active', 'interrupted') "
                "ORDER BY started_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_file_info(db: Path, file_path: str) -> Optional[Dict]:
    """Return full info for a specific file path (exact or partial match)."""
    pattern = f"%{file_path}%"
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE path = ? OR path LIKE ? LIMIT 1",
            (file_path, pattern),
        ).fetchone()
        if not row:
            return None
        result = dict(row)

        # Attach recent changes for this file
        changes = conn.execute(
            "SELECT change_type, changed_at, session_id FROM changes "
            "WHERE file_path = ? ORDER BY changed_at DESC LIMIT 10",
            (result["path"],),
        ).fetchall()
        result["recent_changes"] = [dict(c) for c in changes]
    return result
