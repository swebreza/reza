"""Shared adapter registry for cross-tool conversation sync."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


SUPPORTED_TOOLS = ("cursor", "codex", "aider", "claude", "continue", "copilot", "vscode", "kilocode")


@dataclass
class AdapterResult:
    tool: str
    enabled: bool
    result: dict


class BaseAdapter:
    tool_name = "base"
    direct = False

    def discover(self, project_dir: Path) -> list[Path]:
        return []

    def sync(self, conn: sqlite3.Connection, project_dir: Path) -> dict:
        return {
            "tool": self.tool_name,
            "sources_found": 0,
            "sessions_imported": 0,
            "sessions_updated": 0,
            "turns_inserted": 0,
            "fallback": True,
        }

    def config(self, project_dir: Path) -> dict:
        sources = [str(p) for p in self.discover(project_dir)]
        return {
            "enabled": True,
            "direct": self.direct,
            "paths": sources,
            "fallback": not self.direct or not sources,
        }


class AdapterRegistry:
    def __init__(self, adapters: Optional[Iterable[BaseAdapter]] = None):
        if adapters is None:
            from .codex import CodexAdapter
            from .cursor import CursorAdapter
            from .aider import AiderAdapter
            from .fallback import (
                ClaudeAdapter,
                ContinueAdapter,
                CopilotAdapter,
                KilocodeAdapter,
                VSCodeAdapter,
            )

            adapters = [
                CursorAdapter(),
                CodexAdapter(),
                AiderAdapter(),
                ClaudeAdapter(),
                ContinueAdapter(),
                CopilotAdapter(),
                VSCodeAdapter(),
                KilocodeAdapter(),
            ]
        self.adapters = {a.tool_name: a for a in adapters}

    def get(self, tool: str) -> BaseAdapter:
        if tool not in self.adapters:
            raise ValueError(f"Unsupported adapter: {tool}")
        return self.adapters[tool]

    def select(self, tool: Optional[str] = None) -> list[BaseAdapter]:
        if tool:
            return [self.get(tool)]
        return list(self.adapters.values())


def adapter_config_path(project_dir: Path) -> Path:
    return project_dir.resolve() / ".reza" / "adapters.json"


def load_adapter_config(project_dir: Path) -> dict:
    path = adapter_config_path(project_dir)
    if not path.exists():
        return {"adapters": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def install_adapter_config(project_dir: Path, tool: Optional[str] = None) -> dict:
    project_dir = project_dir.resolve()
    config_path = adapter_config_path(project_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    registry = AdapterRegistry()
    adapters = {}
    for adapter in registry.select(tool):
        adapters[adapter.tool_name] = adapter.config(project_dir)
    config = {"version": 1, "project": str(project_dir), "adapters": adapters}
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def sync_adapters(
    conn: sqlite3.Connection,
    project_dir: Path,
    tool: Optional[str] = None,
) -> dict:
    registry = AdapterRegistry()
    config = load_adapter_config(project_dir)
    configured = config.get("adapters") or {}
    results = {}
    for adapter in registry.select(tool):
        cfg = configured.get(adapter.tool_name, {"enabled": True})
        if not cfg.get("enabled", True):
            results[adapter.tool_name] = {"tool": adapter.tool_name, "enabled": False}
            continue
        results[adapter.tool_name] = adapter.sync(conn, project_dir.resolve())
    return {"project_dir": str(project_dir.resolve()), "tools": results}
