"""Update individual files in the DB — used by git hooks and CLI.

Includes conflict detection: if a staged/written file is locked by a different
session, a conflict is logged and reported before the update proceeds.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from .init_db import extract_purpose, file_checksum, count_lines, is_indexable
from .schema import get_connection, find_db_path


def _upsert(conn, project_root: str, rel_path: str, change_type: str, session_id: Optional[str]):
    """Insert or update one file record and log the change."""
    abs_path = Path(project_root) / rel_path
    if not abs_path.exists():
        conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        conn.execute(
            "INSERT INTO changes (file_path, change_type, session_id) VALUES (?, 'deleted', ?)",
            (rel_path, session_id),
        )
        return

    if not is_indexable(abs_path):
        return

    from datetime import datetime
    try:
        stat = abs_path.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except OSError:
        return

    purpose = extract_purpose(str(abs_path))
    lines = count_lines(str(abs_path))
    checksum = file_checksum(str(abs_path))
    file_type = abs_path.suffix.lower().lstrip(".") or abs_path.name

    conn.execute(
        """
        INSERT INTO files (path, file_type, line_count, size_bytes, purpose, last_modified, checksum)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            file_type     = excluded.file_type,
            line_count    = excluded.line_count,
            size_bytes    = excluded.size_bytes,
            purpose       = excluded.purpose,
            last_modified = excluded.last_modified,
            checksum      = excluded.checksum,
            indexed_at    = datetime('now')
        """,
        (rel_path, file_type, lines, size, purpose, mtime, checksum),
    )
    conn.execute(
        "INSERT INTO changes (file_path, change_type, session_id) VALUES (?, ?, ?)",
        (rel_path, change_type, session_id),
    )


def _active_session(conn) -> Optional[str]:
    row = conn.execute(
        "SELECT id FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


def _check_conflict(db: Path, rel_path: str, session_id: Optional[str], silent: bool):
    """Run conflict detection for a single file path."""
    if not session_id:
        return
    try:
        from .claim import check_conflict
        conflict = check_conflict(db, rel_path, session_id)
        if conflict and not silent:
            print(
                f"\n[reza CONFLICT] {rel_path}\n"
                f"  Locked by : {conflict['lock_owner_llm']} ({conflict['lock_owner']})\n"
                f"  Written by: {conflict['writing_llm']} ({conflict['writing_session']})\n"
                f"  Run 'reza conflicts' to review.\n",
                file=sys.stderr,
            )
    except Exception:
        pass


def update_staged(db: Path, silent: bool = False):
    """Update the DB for all staged files (called from pre-commit hook)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return

    project_root = str(db.parent.parent)
    conflicts_found = []

    with get_connection(db) as conn:
        session_id = _active_session(conn)
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            status_code, rel_path = parts[0].strip(), parts[1].strip()

            if status_code == "D":
                change_type = "deleted"
            elif status_code == "A":
                change_type = "created"
            else:
                change_type = "modified"

            _upsert(conn, project_root, rel_path, change_type, session_id)

    # Conflict detection runs after the connection is closed (avoids nested conn)
    if session_id:
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            rel_path = parts[1].strip()
            _check_conflict(db, rel_path, session_id, silent)

    if not silent:
        print("reza: context DB updated.")


def update_single_file(db: Path, file_path: str, silent: bool = False):
    """Update the DB for a single file path."""
    abs_path = Path(file_path).resolve()
    db_path = db or find_db_path(str(abs_path.parent))
    if not db_path:
        return

    project_root = str(db_path.parent.parent)
    try:
        rel_path = str(abs_path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return

    with get_connection(db_path) as conn:
        session_id = _active_session(conn)
        change_type = "modified" if abs_path.exists() else "deleted"
        _upsert(conn, project_root, rel_path, change_type, session_id)

    _check_conflict(db_path, rel_path, session_id, silent)

    if not silent:
        print(f"reza: updated {rel_path}")
