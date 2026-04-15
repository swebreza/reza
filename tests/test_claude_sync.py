"""Unit tests for reza.claude_sync — .jsonl parsing and idempotent sync."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from reza.schema import get_db_path, init_schema
from reza.session import start_session
from reza.turns import list_turns
from reza.claude_sync import parse_jsonl, sync_claude_session


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> Path:
    """Create a minimal reza DB in tmp_path and return its path."""
    reza_dir = tmp_path / ".reza"
    reza_dir.mkdir()
    db_path = reza_dir / "context.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _make_jsonl(tmp_path: Path, turns: list, filename: str = "session.jsonl") -> Path:
    """Write a Claude-format .jsonl file with the given turns."""
    p = tmp_path / filename
    lines = []
    for i, turn in enumerate(turns):
        role = turn["role"]
        content = turn["content"]

        if role == "user":
            obj = {
                "type": "user",
                "sessionId": "test-session-abc",
                "uuid": f"uuid-{i}",
                "timestamp": "2026-04-12T10:00:00Z",
                "cwd": str(tmp_path),
                "message": {"role": "user", "content": content},
            }
        else:
            obj = {
                "type": "assistant",
                "sessionId": "test-session-abc",
                "uuid": f"uuid-{i}",
                "timestamp": "2026-04-12T10:00:01Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": content}],
                },
            }
        lines.append(json.dumps(obj))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# parse_jsonl
# ─────────────────────────────────────────────────────────────────────────────

class TestParseJsonl:
    def test_parses_user_and_assistant(self, tmp_path):
        turns = [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "Paris."},
        ]
        p = _make_jsonl(tmp_path, turns)
        result = parse_jsonl(p)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "What is the capital of France?"}
        assert result[1] == {"role": "assistant", "content": "Paris."}

    def test_skips_sidechain_entries(self, tmp_path):
        p = tmp_path / "session.jsonl"
        obj = {
            "type": "user",
            "isSidechain": True,
            "message": {"role": "user", "content": "sidechain text"},
        }
        p.write_text(json.dumps(obj) + "\n", encoding="utf-8")
        result = parse_jsonl(p)
        assert result == []

    def test_skips_unknown_types(self, tmp_path):
        p = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "summary", "summary": "lots happened"}),
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
        ]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = parse_jsonl(p)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_skips_empty_content(self, tmp_path):
        p = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": "   "}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": []}}),
            json.dumps({"type": "user", "message": {"role": "user", "content": "real message"}}),
        ]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = parse_jsonl(p)
        assert len(result) == 1
        assert result[0]["content"] == "real message"

    def test_handles_multi_block_assistant_content(self, tmp_path):
        p = tmp_path / "session.jsonl"
        obj = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "First part."},
                    {"type": "tool_use", "id": "t1", "name": "Read"},
                    {"type": "text", "text": "Second part."},
                ],
            },
        }
        p.write_text(json.dumps(obj) + "\n", encoding="utf-8")
        result = parse_jsonl(p)
        assert len(result) == 1
        assert "First part." in result[0]["content"]
        assert "Second part." in result[0]["content"]

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_jsonl(tmp_path / "nonexistent.jsonl")

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("", encoding="utf-8")
        assert parse_jsonl(p) == []

    def test_malformed_json_lines_skipped(self, tmp_path):
        p = tmp_path / "session.jsonl"
        lines = [
            "{this is not json}",
            json.dumps({"type": "user", "message": {"role": "user", "content": "valid"}}),
        ]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = parse_jsonl(p)
        assert len(result) == 1
        assert result[0]["content"] == "valid"


# ─────────────────────────────────────────────────────────────────────────────
# sync_claude_session
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncClaudeSession:
    def test_syncs_all_turns_new_session(self, tmp_path):
        db = _make_db(tmp_path)
        turns_data = [
            {"role": "user", "content": "Hello Claude"},
            {"role": "assistant", "content": "Hi! How can I help?"},
            {"role": "user", "content": "Explain FTS5"},
        ]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl)

        assert result["synced"] == 3
        assert result["skipped"] == 0
        assert result["total"] == 3
        sid = result["session_id"]

        stored = list_turns(db, sid)
        assert len(stored) == 3
        assert stored[0]["role"] == "user"
        assert stored[0]["content"] == "Hello Claude"
        assert stored[2]["content"] == "Explain FTS5"

    def test_uses_explicit_session_id(self, tmp_path):
        db = _make_db(tmp_path)
        sid = start_session(db, "claude", "test task")
        turns_data = [{"role": "user", "content": "test"}, {"role": "assistant", "content": "ok"}]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl, reza_session_id=sid)

        assert result["session_id"] == sid
        assert result["synced"] == 2

    def test_idempotent_second_call_skips_all(self, tmp_path):
        db = _make_db(tmp_path)
        turns_data = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        jsonl = _make_jsonl(tmp_path, turns_data)

        r1 = sync_claude_session(db, jsonl)
        r2 = sync_claude_session(db, jsonl, reza_session_id=r1["session_id"])

        assert r2["synced"] == 0
        assert r2["skipped"] == 2
        assert len(list_turns(db, r1["session_id"])) == 2

    def test_incremental_sync_only_appends_new(self, tmp_path):
        db = _make_db(tmp_path)
        initial = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Turn 2"},
        ]
        jsonl = _make_jsonl(tmp_path, initial)
        r1 = sync_claude_session(db, jsonl)
        sid = r1["session_id"]

        # Simulate more turns appearing in the .jsonl
        extended = initial + [
            {"role": "user", "content": "Turn 3"},
            {"role": "assistant", "content": "Turn 4"},
        ]
        jsonl.write_text(
            "\n".join(
                json.dumps(
                    {"type": t["role"], "message": {"role": t["role"], "content": t["content"]}}
                    if t["role"] == "user"
                    else {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": t["content"]}],
                        },
                    }
                )
                for t in extended
            ) + "\n",
            encoding="utf-8",
        )

        r2 = sync_claude_session(db, jsonl, reza_session_id=sid)
        assert r2["synced"] == 2
        assert r2["skipped"] == 2
        assert len(list_turns(db, sid)) == 4

    def test_empty_jsonl_returns_zero(self, tmp_path):
        db = _make_db(tmp_path)
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("", encoding="utf-8")
        result = sync_claude_session(db, jsonl)
        assert result["synced"] == 0
        assert result["total"] == 0

    def test_uses_current_session_file(self, tmp_path):
        db = _make_db(tmp_path)
        sid = start_session(db, "claude", "from current_session file")
        # Write .reza/current_session
        (tmp_path / ".reza" / "current_session").write_text(sid, encoding="utf-8")

        turns_data = [{"role": "user", "content": "auto pick up"}]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl)
        assert result["session_id"] == sid
        assert result["synced"] == 1

    def test_falls_back_to_most_recent_active_session(self, tmp_path):
        db = _make_db(tmp_path)
        sid = start_session(db, "claude", "active session")
        # No current_session file

        turns_data = [{"role": "assistant", "content": "auto fallback"}]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl)
        assert result["session_id"] == sid
        assert result["synced"] == 1

    def test_auto_creates_session_if_none_found(self, tmp_path):
        db = _make_db(tmp_path)
        # No existing sessions, no current_session file
        turns_data = [{"role": "user", "content": "new convo"}]
        jsonl = _make_jsonl(tmp_path, turns_data, filename="claude-abc123.jsonl")

        result = sync_claude_session(db, jsonl)
        assert result["synced"] == 1
        # Should have auto-created a session with llm_name=claude
        stored = list_turns(db, result["session_id"])
        assert len(stored) == 1

    def test_token_estimates_set(self, tmp_path):
        db = _make_db(tmp_path)
        content = "A" * 400  # 100 token estimate
        turns_data = [{"role": "user", "content": content}]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl)
        stored = list_turns(db, result["session_id"])
        assert stored[0]["token_est"] == 100


# ─────────────────────────────────────────────────────────────────────────────
# Regression: Issue #1 — legacy DB auto-migration
# ─────────────────────────────────────────────────────────────────────────────

def _make_legacy_db(tmp_path: Path) -> Path:
    """Create a v0.1.0-style DB with only the original 6 tables, no conversation_turns."""
    reza_dir = tmp_path / ".reza"
    reza_dir.mkdir()
    db_path = reza_dir / "context.db"
    conn = sqlite3.connect(str(db_path))
    # Only the original schema — no conversation_turns, no FTS
    conn.executescript("""
        CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT);
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL,
            file_type TEXT, line_count INTEGER DEFAULT 0, size_bytes INTEGER DEFAULT 0,
            purpose TEXT, tags TEXT, last_modified TEXT, checksum TEXT,
            llm_notes TEXT, indexed_at TEXT
        );
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, llm_name TEXT NOT NULL, started_at TEXT,
            ended_at TEXT, status TEXT DEFAULT 'active', working_on TEXT,
            summary TEXT, conversation_context TEXT, files_modified TEXT, tags TEXT
        );
        INSERT INTO sessions (id, llm_name, status, working_on)
        VALUES ('legacy-session-1', 'claude', 'interrupted', 'old work');
    """)
    conn.commit()
    conn.close()
    return db_path


class TestLegacyDBAutoMigration:
    """Regression: old DBs without conversation_turns / FTS must not crash."""

    def test_search_turns_on_legacy_db_returns_empty(self, tmp_path):
        db = _make_legacy_db(tmp_path)
        from reza.turns import search_turns
        # Must not raise OperationalError: no such table: conversation_turns_fts
        results = search_turns(db, "auth")
        assert results == []

    def test_get_handoff_data_on_legacy_db_returns_session(self, tmp_path):
        db = _make_legacy_db(tmp_path)
        from reza.session import get_handoff_data
        # Must not raise OperationalError: no such table: conversation_turns
        data = get_handoff_data(db)
        assert data is not None
        assert data["id"] == "legacy-session-1"
        assert data["turns"] == []

    def test_sync_claude_session_on_legacy_db_succeeds(self, tmp_path):
        db = _make_legacy_db(tmp_path)
        turns_data = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        jsonl = _make_jsonl(tmp_path, turns_data)
        # Must not raise — should auto-migrate and sync into legacy-session-1
        result = sync_claude_session(db, jsonl)
        assert result["synced"] == 2
        assert result["session_id"] == "legacy-session-1"

    def test_legacy_db_migrated_once_not_repeatedly(self, tmp_path):
        """Second connection after migration should find tables already there — no error."""
        db = _make_legacy_db(tmp_path)
        from reza.turns import list_turns
        from reza.session import start_session
        # First connection triggers migration
        sid = start_session(db, "claude", "first touch after migration")
        # Second connection — tables already exist, no re-run of executescript needed
        turns = list_turns(db, sid)
        assert turns == []


# ─────────────────────────────────────────────────────────────────────────────
# Regression: Issue #2 — session hijack prevention
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionHijackPrevention:
    """Regression: sync-claude must not write into non-Claude sessions."""

    def test_does_not_hijack_cursor_session(self, tmp_path):
        db = _make_db(tmp_path)
        cursor_sid = start_session(db, "cursor", "cursor task")
        # No current_session file, no explicit session ID
        turns_data = [{"role": "user", "content": "claude turn"}]
        jsonl = _make_jsonl(tmp_path, turns_data, filename="session.jsonl")

        result = sync_claude_session(db, jsonl)
        # Must NOT write into the cursor session
        assert result["session_id"] != cursor_sid
        # A new claude session should have been auto-created
        assert "claude" in result["session_id"] or result["session_id"] not in [cursor_sid]
        assert result["synced"] == 1

    def test_does_not_hijack_aider_session(self, tmp_path):
        db = _make_db(tmp_path)
        aider_sid = start_session(db, "aider", "aider task")
        codex_sid = start_session(db, "codex", "codex task")
        turns_data = [{"role": "assistant", "content": "from claude"}]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl)
        assert result["session_id"] != aider_sid
        assert result["session_id"] != codex_sid

    def test_does_pick_up_claude_session_as_fallback(self, tmp_path):
        db = _make_db(tmp_path)
        cursor_sid = start_session(db, "cursor", "cursor task")
        claude_sid = start_session(db, "claude", "claude task")
        turns_data = [{"role": "user", "content": "claude work"}]
        jsonl = _make_jsonl(tmp_path, turns_data)

        result = sync_claude_session(db, jsonl)
        # Should pick the claude session, not the cursor one
        assert result["session_id"] == claude_sid

    def test_current_session_file_overrides_all_fallbacks(self, tmp_path):
        db = _make_db(tmp_path)
        cursor_sid = start_session(db, "cursor", "cursor task")
        claude_sid = start_session(db, "claude", "claude task")
        # Write a specific session to current_session — it takes priority
        (tmp_path / ".reza" / "current_session").write_text(cursor_sid, encoding="utf-8")

        turns_data = [{"role": "user", "content": "override test"}]
        jsonl = _make_jsonl(tmp_path, turns_data)
        result = sync_claude_session(db, jsonl)
        # current_session file explicitly set to cursor_sid — must respect it
        assert result["session_id"] == cursor_sid

    def test_auto_creates_new_session_when_no_claude_session_exists(self, tmp_path):
        db = _make_db(tmp_path)
        start_session(db, "cursor", "cursor only")
        start_session(db, "aider", "aider only")
        turns_data = [{"role": "user", "content": "new claude work"}]
        jsonl = _make_jsonl(tmp_path, turns_data, filename="session.jsonl")

        result = sync_claude_session(db, jsonl)
        # Neither cursor nor aider — must create a new session
        assert result["synced"] == 1
        # New session should have claude-derived llm_name
        from reza.schema import get_connection
        with get_connection(db) as conn:
            row = conn.execute(
                "SELECT llm_name FROM sessions WHERE id = ?", (result["session_id"],)
            ).fetchone()
        assert row["llm_name"] == "claude"
