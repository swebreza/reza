"""Tests for the query module."""

import pytest
from pathlib import Path

from reza.init_db import initialize_project
from reza.query import get_overview, find_files, get_recent_changes, get_file_info
from reza.session import start_session
from reza.schema import get_connection


@pytest.fixture
def db(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        '"""Authentication logic — handles JWT and session management."""\n'
        'def login(user, pwd): pass\n'
    )
    (tmp_path / "src" / "api.py").write_text(
        '# REST API route handlers\nfrom flask import Blueprint\n'
    )
    (tmp_path / "README.md").write_text("# Test Project\nA project for testing.\n")
    (tmp_path / "requirements.txt").write_text("flask\n")
    result = initialize_project(str(tmp_path), install_hooks=False)
    return Path(result["db_path"])


class TestGetOverview:
    def test_returns_meta(self, db):
        overview = get_overview(db)
        assert "meta" in overview
        assert "file_count" in overview
        assert overview["file_count"] >= 3

    def test_returns_file_tree(self, db):
        overview = get_overview(db)
        assert "file_tree" in overview
        assert len(overview["file_tree"]) > 0

    def test_returns_active_sessions(self, db):
        start_session(db, "claude", "test task")
        overview = get_overview(db)
        assert len(overview["active_sessions"]) >= 1


class TestFindFiles:
    def test_finds_by_purpose(self, db):
        results = find_files(db, "authentication")
        paths = [r["path"] for r in results]
        assert any("auth" in p for p in paths)

    def test_finds_by_path(self, db):
        results = find_files(db, "api")
        paths = [r["path"] for r in results]
        assert any("api" in p for p in paths)

    def test_empty_query_no_crash(self, db):
        results = find_files(db, "zzznomatchzzz")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_returns_purpose_field(self, db):
        results = find_files(db, "auth")
        assert len(results) > 0
        assert "purpose" in results[0]


class TestGetRecentChanges:
    def test_returns_list(self, db):
        changes = get_recent_changes(db)
        assert isinstance(changes, list)

    def test_limit_respected(self, db):
        changes = get_recent_changes(db, limit=5)
        assert len(changes) <= 5


class TestGetFileInfo:
    def test_finds_exact_path(self, db):
        info = get_file_info(db, "src/auth.py")
        assert info is not None
        assert "auth" in info["path"]

    def test_finds_partial_path(self, db):
        info = get_file_info(db, "auth")
        assert info is not None

    def test_returns_none_for_missing(self, db):
        info = get_file_info(db, "totally_nonexistent_file_xyz.py")
        assert info is None

    def test_includes_line_count(self, db):
        info = get_file_info(db, "auth.py")
        assert info is not None
        assert "line_count" in info
        assert info["line_count"] > 0
