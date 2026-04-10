"""Tests for parallel agent conflict detection — claim, release, conflicts."""

import pytest
from pathlib import Path

from reza.init_db import initialize_project
from reza.session import start_session, end_session
from reza.claim import (
    claim_file, release_file, release_session_locks,
    get_lock, list_locks, check_conflict,
    list_conflicts, resolve_conflict, resolve_file_conflicts,
)
from reza.schema import get_connection


@pytest.fixture
def db(tmp_path):
    result = initialize_project(str(tmp_path), install_hooks=False)
    return Path(result["db_path"])


@pytest.fixture
def two_sessions(db):
    """Create two active sessions for different LLMs."""
    sid_a = start_session(db, "claude", "task a")
    sid_b = start_session(db, "cursor", "task b")
    # start_session marks previous same-LLM sessions interrupted — force both active
    with get_connection(db) as conn:
        conn.execute("UPDATE sessions SET status='active' WHERE id IN (?, ?)", (sid_a, sid_b))
    return sid_a, sid_b


# ─────────────────────────────────────────────
# Claiming
# ─────────────────────────────────────────────

class TestClaimFile:
    def test_claim_succeeds_on_unlocked_file(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        result = claim_file(db, "src/auth.py", sid_a)
        assert result["claimed"] is True
        assert result["conflict"] is False
        assert result["owner"] == sid_a

    def test_claim_is_idempotent_for_same_session(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        result = claim_file(db, "src/auth.py", sid_a)
        assert result["claimed"] is True
        assert result["conflict"] is False

    def test_claim_fails_when_locked_by_other_session(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        result = claim_file(db, "src/auth.py", sid_b)
        assert result["claimed"] is False
        assert result["conflict"] is True
        assert result["owner"] == sid_a
        assert result["llm"] == "claude"

    def test_conflict_logged_on_failed_claim(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/auth.py", sid_b)
        open_conflicts = list_conflicts(db)
        assert len(open_conflicts) == 1
        assert open_conflicts[0]["file_path"] == "src/auth.py"
        assert open_conflicts[0]["session_a"] == sid_a
        assert open_conflicts[0]["session_b"] == sid_b

    def test_lock_stored_in_db(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/models.py", sid_a)
        lock = get_lock(db, "src/models.py")
        assert lock is not None
        assert lock["session_id"] == sid_a
        assert lock["llm_name"] == "claude"

    def test_no_lock_returns_none(self, db):
        assert get_lock(db, "src/nonexistent.py") is None


# ─────────────────────────────────────────────
# Releasing
# ─────────────────────────────────────────────

class TestReleaseFile:
    def test_release_removes_lock(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        released = release_file(db, "src/auth.py", sid_a)
        assert released is True
        assert get_lock(db, "src/auth.py") is None

    def test_release_wrong_session_does_nothing(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        released = release_file(db, "src/auth.py", sid_b)
        assert released is False
        assert get_lock(db, "src/auth.py") is not None

    def test_release_without_session_removes_any_lock(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        released = release_file(db, "src/auth.py")
        assert released is True
        assert get_lock(db, "src/auth.py") is None

    def test_release_nonexistent_lock_returns_false(self, db):
        assert release_file(db, "src/ghost.py") is False

    def test_release_session_locks_removes_all(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/models.py", sid_a)
        claim_file(db, "src/api.py", sid_b)

        count = release_session_locks(db, sid_a)
        assert count == 2
        assert get_lock(db, "src/auth.py") is None
        assert get_lock(db, "src/models.py") is None
        # Cursor's lock untouched
        assert get_lock(db, "src/api.py") is not None

    def test_session_end_auto_releases_locks(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/models.py", sid_a)
        end_session(db, sid_a)
        assert get_lock(db, "src/auth.py") is None
        assert get_lock(db, "src/models.py") is None


# ─────────────────────────────────────────────
# Conflict detection
# ─────────────────────────────────────────────

class TestCheckConflict:
    def test_no_conflict_when_file_not_locked(self, db, two_sessions):
        sid_a, _ = two_sessions
        result = check_conflict(db, "src/unlocked.py", sid_a)
        assert result is None

    def test_no_conflict_when_same_session_writes(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        result = check_conflict(db, "src/auth.py", sid_a)
        assert result is None

    def test_conflict_detected_when_different_session_writes(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        result = check_conflict(db, "src/auth.py", sid_b)
        assert result is not None
        assert result["lock_owner"] == sid_a
        assert result["lock_owner_llm"] == "claude"
        assert result["writing_session"] == sid_b
        assert result["writing_llm"] == "cursor"

    def test_conflict_logged_to_db(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        check_conflict(db, "src/auth.py", sid_b)
        conflicts = list_conflicts(db)
        assert any(c["file_path"] == "src/auth.py" for c in conflicts)

    def test_no_conflict_when_session_id_none(self, db, two_sessions):
        sid_a, _ = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        result = check_conflict(db, "src/auth.py", None)
        assert result is None


# ─────────────────────────────────────────────
# Listing & resolving conflicts
# ─────────────────────────────────────────────

class TestConflictManagement:
    def test_list_conflicts_empty(self, db):
        assert list_conflicts(db) == []

    def test_list_conflicts_unresolved_only(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/auth.py", sid_b)  # creates conflict
        conflicts = list_conflicts(db, unresolved_only=True)
        assert len(conflicts) == 1
        assert conflicts[0]["resolved"] == 0

    def test_list_all_conflicts(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/auth.py", sid_b)
        conflict_id = list_conflicts(db)[0]["id"]
        resolve_conflict(db, conflict_id)
        all_conflicts = list_conflicts(db, unresolved_only=False)
        assert len(all_conflicts) == 1
        assert all_conflicts[0]["resolved"] == 1

    def test_resolve_conflict_by_id(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/auth.py", sid_b)
        conflict_id = list_conflicts(db)[0]["id"]
        result = resolve_conflict(db, conflict_id, resolved_by="test")
        assert result is True
        assert list_conflicts(db, unresolved_only=True) == []

    def test_resolve_nonexistent_conflict(self, db):
        assert resolve_conflict(db, 9999) is False

    def test_resolve_file_conflicts(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/auth.py", sid_b)
        count = resolve_file_conflicts(db, "src/auth.py", resolved_by="test")
        assert count == 1
        assert list_conflicts(db, unresolved_only=True) == []

    def test_multiple_conflicts_different_files(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/auth.py", sid_b)
        claim_file(db, "src/models.py", sid_a)
        claim_file(db, "src/models.py", sid_b)
        conflicts = list_conflicts(db)
        assert len(conflicts) == 2


# ─────────────────────────────────────────────
# List locks
# ─────────────────────────────────────────────

class TestListLocks:
    def test_list_all_locks(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/api.py", sid_b)
        locks = list_locks(db)
        assert len(locks) == 2

    def test_filter_by_session(self, db, two_sessions):
        sid_a, sid_b = two_sessions
        claim_file(db, "src/auth.py", sid_a)
        claim_file(db, "src/api.py", sid_b)
        locks = list_locks(db, session_id=sid_a)
        assert len(locks) == 1
        assert locks[0]["file_path"] == "src/auth.py"

    def test_empty_when_no_locks(self, db):
        assert list_locks(db) == []
