"""Cursor conversation adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .base import BaseAdapter
from ..ingest.cursor import discover_cursor_transcripts, sync_cursor_project


class CursorAdapter(BaseAdapter):
    tool_name = "cursor"
    direct = True

    def discover(self, project_dir: Path) -> list[Path]:
        return discover_cursor_transcripts(project_dir)

    def sync(self, conn: sqlite3.Connection, project_dir: Path) -> dict:
        result = sync_cursor_project(conn, project_dir)
        result["sources_found"] = result.get("transcripts_found", 0)
        return result
