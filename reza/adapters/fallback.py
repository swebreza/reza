"""Fallback adapters for tools without stable direct transcript capture."""

from __future__ import annotations

from .base import BaseAdapter


class ClaudeAdapter(BaseAdapter):
    tool_name = "claude"


class ContinueAdapter(BaseAdapter):
    tool_name = "continue"


class CopilotAdapter(BaseAdapter):
    tool_name = "copilot"


class VSCodeAdapter(BaseAdapter):
    tool_name = "vscode"


class KilocodeAdapter(BaseAdapter):
    tool_name = "kilocode"
