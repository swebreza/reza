"""Real-time file watcher — syncs file changes to the context database.

Also performs automatic conflict detection: if a file is modified by a session
that is NOT the lock owner, a conflict is logged immediately and printed to
stdout so the watching agent sees it in real time.
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .init_db import (
    IGNORE_DIRS, IGNORE_EXTENSIONS, is_indexable,
    extract_purpose, file_checksum, count_lines,
)
from .schema import get_connection, find_db_path, DB_DIR


def _get_session_id(db: Path) -> str:
    """Return the most recent active session ID, or empty string."""
    try:
        with get_connection(db) as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            return row["id"] if row else ""
    except Exception:
        return ""


def _check_and_log_conflict(db: Path, rel_path: str, writing_session_id: str) -> bool:
    """Check for a lock conflict and log it. Returns True if conflict found."""
    if not writing_session_id:
        return False
    try:
        from .claim import check_conflict
        conflict = check_conflict(db, rel_path, writing_session_id)
        if conflict:
            print(
                f"\n[reza CONFLICT] {rel_path}\n"
                f"  Locked by : {conflict['lock_owner_llm']} ({conflict['lock_owner']})\n"
                f"  Written by: {conflict['writing_llm']} ({conflict['writing_session']})\n"
                f"  Run 'reza conflicts' to see all open conflicts.\n",
                file=sys.stderr,
            )
            return True
    except Exception:
        pass
    return False


def _upsert_file(db: Path, abs_path: str, project_root: str, change_type: str):
    """Update or insert a file record, log the change, and check for conflicts."""
    path = Path(abs_path)
    if not is_indexable(path):
        return
    try:
        rel = str(path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return

    try:
        stat = path.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except OSError:
        size, mtime = 0, datetime.now().isoformat()

    purpose = extract_purpose(abs_path)
    lines = count_lines(abs_path)
    checksum = file_checksum(abs_path)
    file_type = path.suffix.lower().lstrip(".") or path.name
    session_id = _get_session_id(db)

    # Conflict check before writing
    if session_id:
        _check_and_log_conflict(db, rel, session_id)

    try:
        with get_connection(db) as conn:
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
                (rel, file_type, lines, size, purpose, mtime, checksum),
            )
            conn.execute(
                "INSERT INTO changes (file_path, change_type, session_id) VALUES (?, ?, ?)",
                (rel, change_type, session_id or None),
            )
    except Exception:
        pass


def _delete_file(db: Path, abs_path: str, project_root: str):
    """Remove a file record and log the deletion."""
    try:
        rel = str(Path(abs_path).relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return
    session_id = _get_session_id(db)
    try:
        with get_connection(db) as conn:
            conn.execute("DELETE FROM files WHERE path = ?", (rel,))
            conn.execute(
                "INSERT INTO changes (file_path, change_type, session_id) VALUES (?, 'deleted', ?)",
                (rel, session_id or None),
            )
    except Exception:
        pass


def _should_ignore(path_str: str) -> bool:
    """Return True if any component of the path is in IGNORE_DIRS."""
    parts = Path(path_str).parts
    for part in parts:
        if part in IGNORE_DIRS or part.startswith("."):
            return True
    if Path(path_str).suffix.lower() in IGNORE_EXTENSIONS:
        return True
    return False


def start_watcher(project_dir: str, db: Path):
    """Start the blocking file watcher loop. Call in a dedicated thread/process."""
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class _Handler(FileSystemEventHandler):
        def __init__(self, project_root: str, db_path: Path):
            self.project_root = project_root
            self.db = db_path
            self._db_dir = str(Path(project_root) / DB_DIR)

        def _skip(self, path: str) -> bool:
            return path.startswith(self._db_dir) or _should_ignore(path)

        def on_created(self, event):
            if event.is_directory:
                return
            path = event.src_path
            # Auto-ingest files dropped into .reza/handoffs/
            handoffs_dir = str(Path(self.project_root) / DB_DIR / "handoffs")
            if path.startswith(handoffs_dir) and path.lower().endswith((".md", ".json")):
                try:
                    from .ingest import ingest_file
                    sid = ingest_file(self.db, path)
                    print(
                        f"\n[reza] Auto-ingested: {Path(path).name} → session {sid}\n"
                        f"  Search : reza session search \"keyword\" --id {sid}\n"
                        f"  Handoff: reza session handoff --id {sid}\n"
                    )
                except RuntimeError:
                    # Already ingested — silent skip
                    pass
                except Exception as e:
                    print(f"\n[reza] Failed to ingest {Path(path).name}: {e}\n", file=sys.stderr)
                return
            if not self._skip(path):
                _upsert_file(self.db, path, self.project_root, "created")

        def on_modified(self, event):
            if not event.is_directory and not self._skip(event.src_path):
                _upsert_file(self.db, event.src_path, self.project_root, "modified")

        def on_deleted(self, event):
            if not event.is_directory and not self._skip(event.src_path):
                _delete_file(self.db, event.src_path, self.project_root)

        def on_moved(self, event):
            if not event.is_directory:
                if not self._skip(event.src_path):
                    _delete_file(self.db, event.src_path, self.project_root)
                if not self._skip(event.dest_path):
                    _upsert_file(self.db, event.dest_path, self.project_root, "moved")

    handler = _Handler(project_dir, db)
    observer = Observer()
    observer.schedule(handler, project_dir, recursive=True)
    observer.start()
    try:
        while observer.is_alive():
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
