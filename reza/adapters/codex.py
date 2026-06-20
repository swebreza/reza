"""Codex conversation adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .base import BaseAdapter
from ..ingest.codex import discover_codex_rollouts, sync_codex_project


class CodexAdapter(BaseAdapter):
    tool_name = "codex"
    direct = True

    def discover(self, project_dir: Path) -> list[Path]:
        return discover_codex_rollouts(project_dir)

    def sync(self, conn: sqlite3.Connection, project_dir: Path) -> dict:
        result = sync_codex_project(conn, project_dir)
        result["sources_found"] = result.get("rollouts_found", 0)
        return result
