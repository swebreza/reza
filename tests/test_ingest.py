"""Tests for transcript file ingestion."""

import json
import pytest
from pathlib import Path

from reza.init_db import initialize_project
from reza.ingest import (
    parse_json_transcript,
    parse_markdown_transcript,
    ingest_file,
    _parse_llm_from_filename,
)
from reza.turns import list_turns
from reza.schema import get_connection


@pytest.fixture
def db(tmp_path):
    result = initialize_project(str(tmp_path), install_hooks=False)
    return Path(result["db_path"])


class TestParseJsonTranscript:
    def test_parses_valid_array(self, tmp_path):
        f = tmp_path / "turns.json"
        f.write_text(json.dumps([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]))
        result = parse_json_transcript(str(f))
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "hello"}
        assert result[1] == {"role": "assistant", "content": "hi there"}

    def test_raises_on_non_array(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text('{"role": "user", "content": "hello"}')
        with pytest.raises(ValueError, match="Expected a JSON array"):
            parse_json_transcript(str(f))

    def test_raises_on_invalid_role(self, tmp_path):
        f = tmp_path / "bad_role.json"
        f.write_text(json.dumps([{"role": "bot", "content": "hi"}]))
        with pytest.raises(ValueError, match="invalid role"):
            parse_json_transcript(str(f))


class TestParseMarkdownTranscript:
    def test_parses_role_markers(self, tmp_path):
        f = tmp_path / "chat.md"
        f.write_text(
            "<!-- role: user -->\nWhat is 2+2?\n\n"
            "<!-- role: assistant -->\nIt is 4.\n"
        )
        result = parse_markdown_transcript(str(f))
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert "2+2" in result[0]["content"]
        assert result[1]["role"] == "assistant"
        assert "4" in result[1]["content"]

    def test_no_markers_returns_single_assistant_turn(self, tmp_path):
        f = tmp_path / "plain.md"
        f.write_text("Just some text with no markers.")
        result = parse_markdown_transcript(str(f))
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert "Just some text" in result[0]["content"]

    def test_case_insensitive_markers(self, tmp_path):
        f = tmp_path / "chat.md"
        f.write_text("<!-- Role: User -->\nhello\n<!-- Role: Assistant -->\nworld\n")
        result = parse_markdown_transcript(str(f))
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_skips_empty_turns(self, tmp_path):
        f = tmp_path / "chat.md"
        f.write_text("<!-- role: user -->\n\n<!-- role: assistant -->\nresponse\n")
        result = parse_markdown_transcript(str(f))
        # empty user turn is skipped
        assert len(result) == 1
        assert result[0]["role"] == "assistant"


class TestParseLlmFromFilename:
    def test_parses_codex_prefix(self):
        assert _parse_llm_from_filename("codex-20260410.md") == "codex"

    def test_parses_claude_prefix(self):
        assert _parse_llm_from_filename("claude-abc123.json") == "claude"

    def test_falls_back_to_unknown(self):
        assert _parse_llm_from_filename("12345.md") == "unknown"

    def test_handles_no_suffix(self):
        assert _parse_llm_from_filename("cursor-session") == "cursor"


class TestIngestFile:
    def test_ingests_json_file(self, db, tmp_path):
        f = tmp_path / "codex-20260410.json"
        f.write_text(json.dumps([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]))
        sid = ingest_file(db, str(f))
        assert sid.startswith("codex-")
        turns = list_turns(db, sid)
        assert len(turns) == 2

    def test_ingests_markdown_file(self, db, tmp_path):
        f = tmp_path / "claude-session.md"
        f.write_text("<!-- role: user -->\nhi\n<!-- role: assistant -->\nhello\n")
        sid = ingest_file(db, str(f))
        assert sid.startswith("claude-")
        turns = list_turns(db, sid)
        assert len(turns) == 2

    def test_uses_provided_session_id(self, db, tmp_path):
        from reza.session import start_session
        existing_sid = start_session(db, "cursor", "existing task")
        f = tmp_path / "turns.json"
        f.write_text(json.dumps([{"role": "user", "content": "hi"}]))
        sid = ingest_file(db, str(f), session_id=existing_sid)
        assert sid == existing_sid
        assert len(list_turns(db, existing_sid)) == 1

    def test_prevents_double_import(self, db, tmp_path):
        f = tmp_path / "turns.json"
        f.write_text(json.dumps([{"role": "user", "content": "hi"}]))
        ingest_file(db, str(f))
        with pytest.raises(RuntimeError, match="Already ingested"):
            ingest_file(db, str(f))

    def test_raises_on_missing_file(self, db):
        with pytest.raises(FileNotFoundError):
            ingest_file(db, "/nonexistent/file.json")

    def test_raises_on_unsupported_format(self, db, tmp_path):
        f = tmp_path / "chat.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported format"):
            ingest_file(db, str(f))
