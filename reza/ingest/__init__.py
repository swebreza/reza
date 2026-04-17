"""Cross-tool chat ingestion.

Scans conversation transcripts from other LLM tools (Cursor, Codex, Claude
Code, …) and imports them into the reza context DB so any session can be
resumed, searched, or packed for handoff by any other tool.

Each imported session is tagged with:
- ``source_tool`` — 'cursor' | 'codex' | 'claude' | 'manual'
- ``source_path`` — the transcript file on disk (used for idempotent re-syncs)
- ``source_id``   — the tool's native session id (e.g. Cursor UUID, Codex rollout id)
"""

from .cursor import sync_cursor_project, discover_cursor_transcripts
from .codex import sync_codex_project, discover_codex_rollouts
from ._common import ParsedSession, ParsedTurn, upsert_imported_session

# Legacy single-file transcript ingestion (backwards compatibility — used to
# live in the top-level ``reza/ingest.py`` before this became a package).
from .files import (
    parse_json_transcript,
    parse_markdown_transcript,
    ingest_file,
    _parse_llm_from_filename,
)

__all__ = [
    "sync_cursor_project",
    "discover_cursor_transcripts",
    "sync_codex_project",
    "discover_codex_rollouts",
    "ParsedSession",
    "ParsedTurn",
    "upsert_imported_session",
    "parse_json_transcript",
    "parse_markdown_transcript",
    "ingest_file",
]
