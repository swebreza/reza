"""Tests for conversation turn storage and budget retrieval."""

import pytest
from pathlib import Path

from reza.init_db import initialize_project
from reza.session import start_session
from reza.turns import add_turn, add_turns_bulk, list_turns, turns_within_budget


@pytest.fixture
def db(tmp_path):
    result = initialize_project(str(tmp_path), install_hooks=False)
    return Path(result["db_path"])


@pytest.fixture
def session_id(db):
    return start_session(db, "claude", "test task")


class TestAddTurn:
    def test_adds_single_turn(self, db, session_id):
        row_id = add_turn(db, session_id, "user", "hello world", token_est=2, turn_index=0)
        assert isinstance(row_id, int)
        turns = list_turns(db, session_id)
        assert len(turns) == 1
        assert turns[0]["role"] == "user"
        assert turns[0]["content"] == "hello world"
        assert turns[0]["token_est"] == 2

    def test_auto_estimates_tokens_when_zero(self, db, session_id):
        add_turn(db, session_id, "assistant", "a" * 40, turn_index=0)
        turns = list_turns(db, session_id)
        # 40 chars // 4 = 10 tokens
        assert turns[0]["token_est"] == 10

    def test_invalid_role_raises(self, db, session_id):
        with pytest.raises(ValueError, match="Invalid role"):
            add_turn(db, session_id, "bot", "hello", turn_index=0)

    def test_unknown_session_raises(self, db):
        with pytest.raises(ValueError, match="Session not found"):
            add_turn(db, "nonexistent-id", "user", "hello", turn_index=0)


class TestAddTurnsBulk:
    def test_inserts_multiple_turns(self, db, session_id):
        turns = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        count = add_turns_bulk(db, session_id, turns)
        assert count == 3
        stored = list_turns(db, session_id)
        assert len(stored) == 3
        assert stored[0]["content"] == "first"
        assert stored[2]["content"] == "third"

    def test_bulk_continues_index_from_existing(self, db, session_id):
        add_turn(db, session_id, "user", "existing", turn_index=0)
        add_turns_bulk(db, session_id, [{"role": "assistant", "content": "new"}])
        stored = list_turns(db, session_id)
        assert stored[-1]["turn_index"] == 1

    def test_empty_list_returns_zero(self, db, session_id):
        assert add_turns_bulk(db, session_id, []) == 0

    def test_unknown_session_raises(self, db):
        with pytest.raises(ValueError, match="Session not found"):
            add_turns_bulk(db, "bad-id", [{"role": "user", "content": "x"}])


class TestListTurns:
    def test_returns_turns_in_order(self, db, session_id):
        add_turn(db, session_id, "user", "A", turn_index=0)
        add_turn(db, session_id, "assistant", "B", turn_index=1)
        add_turn(db, session_id, "user", "C", turn_index=2)
        turns = list_turns(db, session_id)
        assert [t["content"] for t in turns] == ["A", "B", "C"]

    def test_empty_session_returns_empty_list(self, db, session_id):
        assert list_turns(db, session_id) == []


class TestTurnsWithinBudget:
    def test_returns_all_turns_when_under_budget(self, db, session_id):
        add_turns_bulk(db, session_id, [
            {"role": "user", "content": "x" * 40, "token_est": 10},
            {"role": "assistant", "content": "y" * 40, "token_est": 10},
        ])
        result = turns_within_budget(db, session_id, budget_tokens=100)
        assert len(result) == 2

    def test_drops_oldest_turns_first(self, db, session_id):
        add_turns_bulk(db, session_id, [
            {"role": "user", "content": "old", "token_est": 50},
            {"role": "assistant", "content": "new", "token_est": 50},
        ])
        # budget=60 only fits the newest turn
        result = turns_within_budget(db, session_id, budget_tokens=60)
        assert len(result) == 1
        assert result[0]["content"] == "new"

    def test_empty_session_returns_empty(self, db, session_id):
        assert turns_within_budget(db, session_id, budget_tokens=1000) == []

    def test_preserves_chronological_order_in_result(self, db, session_id):
        add_turns_bulk(db, session_id, [
            {"role": "user", "content": "first", "token_est": 5},
            {"role": "assistant", "content": "second", "token_est": 5},
            {"role": "user", "content": "third", "token_est": 5},
        ])
        result = turns_within_budget(db, session_id, budget_tokens=12)
        # fits 'second' (5) + 'third' (5) = 10 <= 12; 'first' would make 15 > 12
        assert len(result) == 2
        assert result[0]["content"] == "second"
        assert result[1]["content"] == "third"


class TestSearchTurns:
    def test_finds_matching_turns(self, db, session_id):
        add_turns_bulk(db, session_id, [
            {"role": "user", "content": "how do I reset the password"},
            {"role": "assistant", "content": "go to the forgot password page"},
            {"role": "user", "content": "what about two factor authentication"},
        ])
        from reza.turns import search_turns
        results = search_turns(db, "password", session_id=session_id)
        assert len(results) >= 1
        assert any("password" in r["content"].lower() for r in results)

    def test_returns_empty_for_no_match(self, db, session_id):
        from reza.turns import search_turns
        add_turns_bulk(db, session_id, [
            {"role": "user", "content": "hello world"},
        ])
        results = search_turns(db, "authentication")
        assert results == []

    def test_porter_stemming_matches_variants(self, db, session_id):
        from reza.turns import search_turns
        add_turns_bulk(db, session_id, [
            {"role": "assistant", "content": "the authentication flow is complete"},
        ])
        # "authenticate" should match "authentication" via porter stemmer
        results = search_turns(db, "authenticate", session_id=session_id)
        assert len(results) >= 1

    def test_respects_session_id_filter(self, db):
        from reza.turns import search_turns
        from reza.session import start_session
        sid1 = start_session(db, "claude", "session 1")
        sid2 = start_session(db, "codex", "session 2")
        add_turns_bulk(db, sid1, [{"role": "user", "content": "fix the login page"}])
        add_turns_bulk(db, sid2, [{"role": "user", "content": "fix the logout page"}])
        results = search_turns(db, "login", session_id=sid1)
        assert all(r["session_id"] == sid1 for r in results)
        assert len(results) == 1

    def test_returns_empty_for_blank_query(self, db, session_id):
        from reza.turns import search_turns
        results = search_turns(db, "   ")
        assert results == []

    def test_limit_is_respected(self, db, session_id):
        from reza.turns import search_turns
        add_turns_bulk(db, session_id, [
            {"role": "user", "content": f"token number {i}"} for i in range(10)
        ])
        results = search_turns(db, "token", session_id=session_id, limit=3)
        assert len(results) <= 3
