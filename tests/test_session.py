"""Tests for session management."""

import pytest
from pathlib import Path

from reza.init_db import initialize_project
from reza.session import (
    start_session, save_session, end_session,
    list_sessions, get_handoff_info,
)
from reza.schema import get_connection


@pytest.fixture
def db(tmp_path):
    result = initialize_project(str(tmp_path), install_hooks=False)
    return Path(result["db_path"])


class TestStartSession:
    def test_creates_session(self, db):
        sid = start_session(db, "claude", "implement auth")
        assert sid.startswith("claude-")
        assert len(sid) > 8

    def test_session_stored_in_db(self, db):
        sid = start_session(db, "cursor", "fix bug")
        with get_connection(db) as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row is not None
        assert row["llm_name"] == "cursor"
        assert row["working_on"] == "fix bug"
        assert row["status"] == "active"

    def test_previous_session_interrupted(self, db):
        sid1 = start_session(db, "claude", "task 1")
        sid2 = start_session(db, "claude", "task 2")
        with get_connection(db) as conn:
            row1 = conn.execute("SELECT status FROM sessions WHERE id = ?", (sid1,)).fetchone()
        assert row1["status"] == "interrupted"


class TestSaveSession:
    def test_saves_summary(self, db):
        sid = start_session(db, "aider", "refactor")
        result = save_session(db, sid, summary="Done refactoring", conversation_context="Next: tests")
        assert result is True
        with get_connection(db) as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row["summary"] == "Done refactoring"
        assert row["conversation_context"] == "Next: tests"

    def test_returns_false_for_unknown_id(self, db):
        result = save_session(db, "nonexistent-id", summary="test")
        assert result is False

    def test_saves_files_modified(self, db):
        sid = start_session(db, "codex", "edit files")
        save_session(db, sid, files_modified="src/a.py, src/b.py")
        with get_connection(db) as conn:
            row = conn.execute("SELECT files_modified FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert "src/a.py" in row["files_modified"]


class TestEndSession:
    def test_marks_as_completed(self, db):
        sid = start_session(db, "claude", "task")
        result = end_session(db, sid, summary="All done")
        assert result is True
        with get_connection(db) as conn:
            row = conn.execute("SELECT status, ended_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row["status"] == "completed"
        assert row["ended_at"] is not None

    def test_returns_false_for_unknown(self, db):
        assert end_session(db, "bad-id") is False


class TestListSessions:
    def test_lists_all(self, db):
        start_session(db, "claude", "task a")
        start_session(db, "cursor", "task b")
        sessions = list_sessions(db)
        assert len(sessions) >= 2

    def test_filters_by_status(self, db):
        sid = start_session(db, "claude", "task")
        end_session(db, sid)
        active = list_sessions(db, status="active")
        completed = list_sessions(db, status="completed")
        assert all(s["status"] == "active" for s in active)
        assert any(s["id"] == sid for s in completed)


class TestHandoff:
    def test_shows_interrupted_sessions(self, db):
        sid = start_session(db, "claude", "implement feature")
        save_session(db, sid, summary="halfway done", conversation_context="next: write tests")
        handoff = get_handoff_info(db)
        assert any(s["id"] == sid for s in handoff)

    def test_completed_sessions_not_in_handoff(self, db):
        sid = start_session(db, "claude", "task")
        end_session(db, sid)
        handoff = get_handoff_info(db)
        assert not any(s["id"] == sid for s in handoff)
