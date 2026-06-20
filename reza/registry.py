"""PC-wide registry for local Reza projects."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from .schema import get_connection
from .turns import search_turns


def get_reza_home() -> Path:
    return Path(os.environ.get("REZA_HOME", Path.home() / ".reza")).expanduser()


def get_registry_path() -> Path:
    return get_reza_home() / "registry.db"


def _connect() -> sqlite3.Connection:
    path = get_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_registry (
            project_path TEXT PRIMARY KEY,
            db_path      TEXT NOT NULL,
            name         TEXT,
            last_seen_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_sources (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name     TEXT NOT NULL,
            source_path   TEXT,
            enabled       INTEGER DEFAULT 1,
            last_seen_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(tool_name, source_path)
        )
        """
    )
    conn.commit()
    return conn


def register_project(project_path: Path, db_path: Path, name: Optional[str] = None) -> None:
    project_path = project_path.resolve()
    db_path = db_path.resolve()
    if name is None:
        name = project_path.name
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO project_registry (project_path, db_path, name, last_seen_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(project_path) DO UPDATE SET
              db_path = excluded.db_path,
              name = excluded.name,
              last_seen_at = datetime('now')
            """,
            (str(project_path), str(db_path), name),
        )


def list_projects() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM project_registry ORDER BY last_seen_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def registry_status() -> dict:
    projects = list_projects()
    return {
        "registry_path": str(get_registry_path()),
        "project_count": len(projects),
        "projects": projects,
    }


def search_global(query: str, limit: int = 10) -> list[dict]:
    results: list[dict] = []
    for project in list_projects():
        db = Path(project["db_path"])
        if not db.exists():
            continue
        try:
            hits = search_turns(db, query, limit=limit)
        except Exception:
            continue
        for hit in hits:
            item = dict(hit)
            item["project_path"] = project["project_path"]
            item["project_name"] = project.get("name") or Path(project["project_path"]).name
            results.append(item)
    results.sort(key=lambda r: r.get("score", 0))
    return results[:limit]


def recent_handoff(limit: int = 1) -> list[dict]:
    from .threads import latest_thread, get_thread_handoff_data
    from .session import get_handoff_data

    packs: list[dict] = []
    for project in list_projects():
        db = Path(project["db_path"])
        if not db.exists():
            continue
        try:
            tid = latest_thread(db)
            pack = get_thread_handoff_data(db, tid) if tid else get_handoff_data(db)
        except Exception:
            pack = None
        if pack:
            pack["project_path"] = project["project_path"]
            packs.append(pack)
    return packs[:limit]
