"""Aider chat history adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .base import BaseAdapter
from ..ingest._common import ParsedSession, ParsedTurn, upsert_imported_session
from ..ingest.files import parse_markdown_transcript


class AiderAdapter(BaseAdapter):
    tool_name = "aider"
    direct = True

    def discover(self, project_dir: Path) -> list[Path]:
        history = project_dir / ".aider.chat.history.md"
        return [history] if history.exists() else []

    def sync(self, conn: sqlite3.Connection, project_dir: Path) -> dict:
        histories = self.discover(project_dir)
        result = {
            "tool": self.tool_name,
            "sources_found": len(histories),
            "sessions_imported": 0,
            "sessions_updated": 0,
            "turns_inserted": 0,
        }
        if not histories:
            return result

        conn.execute("BEGIN IMMEDIATE")
        try:
            for history in histories:
                turns = [
                    ParsedTurn(role=t["role"], content=t["content"])
                    for t in parse_markdown_transcript(str(history))
                ]
                parsed = ParsedSession(
                    source_tool="aider",
                    source_id=str(history.stat().st_ino if hasattr(history.stat(), "st_ino") else history.name),
                    source_path=str(history.resolve()),
                    llm_name="aider",
                    working_on="Aider chat history",
                    project_cwd=str(project_dir.resolve()),
                    turns=turns,
                )
                existed = conn.execute(
                    "SELECT 1 FROM sessions WHERE source_tool='aider' AND source_path=?",
                    (parsed.source_path,),
                ).fetchone()
                _, inserted, _ = upsert_imported_session(conn, parsed)
                if existed:
                    result["sessions_updated"] += 1
                else:
                    result["sessions_imported"] += 1
                result["turns_inserted"] += inserted
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        return result
