"""Query functions — overview, file search, recent changes, sessions, unified context."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import get_connection

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Unified context: conversation + code graph
# ---------------------------------------------------------------------------


def get_unified_context(
    db: Path,
    changed_files: Optional[List[str]] = None,
    search_query: Optional[str] = None,
    session_id: Optional[str] = None,
    max_depth: int = 3,
    turn_limit: int = 5,
) -> Dict[str, Any]:
    """Build a combined context packet from conversation history AND code graph.

    This is the key differentiator over code-review-graph: LLMs get both
    structural code awareness (blast radius, signatures) and relevant
    conversation history (what was discussed about affected code) in one query.

    Returns:
        - graph_context: impacted files, signatures, test gaps (if graph built)
        - conversation_context: relevant conversation turns matching the query
        - file_discussions: conversation turns mentioning impacted files
    """
    result: Dict[str, Any] = {
        "graph_context": None,
        "conversation_context": [],
        "file_discussions": {},
    }

    if changed_files:
        try:
            from .graph.store import GraphStore
            from .graph.impact import get_compact_context
            store = GraphStore(db)
            stats = store.get_stats()
            if stats.total_nodes > 0:
                result["graph_context"] = get_compact_context(
                    store, changed_files, max_depth=max_depth,
                )
            store.close()
        except (ImportError, Exception) as e:
            logger.debug("Graph context unavailable: %s", e)

    if search_query:
        from .turns import search_turns
        result["conversation_context"] = search_turns(
            db, search_query, session_id=session_id, limit=turn_limit,
        )

    impacted_files: List[str] = []
    if result["graph_context"]:
        impacted_files = result["graph_context"].get("impacted_files", [])

    if impacted_files:
        file_discussions: Dict[str, List[Dict]] = {}
        for fp in impacted_files[:10]:
            basename = Path(fp).name
            from .turns import search_turns
            hits = search_turns(db, basename, session_id=session_id, limit=3)
            if hits:
                file_discussions[fp] = hits
        result["file_discussions"] = file_discussions

    return result
