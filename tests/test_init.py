"""Tests for project initialization."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from reza.init_db import (
    initialize_project,
    extract_purpose,
    detect_framework,
    file_checksum,
    is_indexable,
    scan_files,
)
from reza.schema import find_db_path, get_connection, DB_DIR, DB_NAME


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal fake project for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        '"""Main entry point for the application."""\nprint("hello")\n'
    )
    (tmp_path / "src" / "utils.py").write_text(
        "# Helper utilities\ndef add(a, b): return a + b\n"
    )
    (tmp_path / "README.md").write_text("# My Project\nA test project.\n")
    (tmp_path / "requirements.txt").write_text("flask==3.0\nclick>=8.0\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "big.js").write_text("module.exports = {};")
    return tmp_path


class TestInitializeProject:
    def test_creates_db(self, tmp_project):
        result = initialize_project(str(tmp_project), install_hooks=False)
        db_path = Path(result["db_path"])
        assert db_path.exists()
        assert db_path.name == DB_NAME

    def test_indexes_files(self, tmp_project):
        result = initialize_project(str(tmp_project), install_hooks=False)
        assert result["indexed"] >= 3  # main.py, utils.py, README.md

    def test_skips_node_modules(self, tmp_project):
        result = initialize_project(str(tmp_project), install_hooks=False)
        db_path = Path(result["db_path"])
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM files WHERE path LIKE '%node_modules%'"
            ).fetchone()
        assert row[0] == 0

    def test_detects_python_framework(self, tmp_project):
        result = initialize_project(str(tmp_project), install_hooks=False)
        assert result["meta"]["language"] == "Python"
        assert result["meta"]["framework"] == "Flask"

    def test_stores_project_meta(self, tmp_project):
        result = initialize_project(str(tmp_project), install_hooks=False)
        db_path = Path(result["db_path"])
        with get_connection(db_path) as conn:
            meta = dict(conn.execute("SELECT key, value FROM project_meta").fetchall())
        assert "language" in meta
        assert "framework" in meta
        assert "initialized_at" in meta

    def test_reinit_updates_files(self, tmp_project):
        initialize_project(str(tmp_project), install_hooks=False)
        # Add a new file
        (tmp_project / "src" / "new.py").write_text('"""New file."""\n')
        result2 = initialize_project(str(tmp_project), install_hooks=False)
        assert result2["indexed"] >= 4


class TestExtractPurpose:
    def test_python_docstring(self, tmp_path):
        f = tmp_path / "foo.py"
        f.write_text('"""This is the module purpose."""\npass\n')
        assert extract_purpose(str(f)) == "This is the module purpose."

    def test_markdown_heading(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# My Document\nSome text.\n")
        assert extract_purpose(str(f)) == "My Document"

    def test_python_comment(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("# Helper script for auth\nimport os\n")
        assert "Helper script for auth" in (extract_purpose(str(f)) or "")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        assert extract_purpose(str(f)) is None

    def test_no_purpose(self, tmp_path):
        f = tmp_path / "plain.py"
        f.write_text("x = 1\ny = 2\n")
        # No docstring or comment — returns None or empty
        result = extract_purpose(str(f))
        assert result is None or result == ""


class TestDetectFramework:
    def test_flask(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0\n")
        meta = detect_framework(str(tmp_path))
        assert meta["framework"] == "Flask"
        assert meta["language"] == "Python"

    def test_django(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("django>=4.0\n")
        meta = detect_framework(str(tmp_path))
        assert meta["framework"] == "Django"

    def test_react(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name":"myapp","dependencies":{"react":"^18.0"}}'
        )
        meta = detect_framework(str(tmp_path))
        assert meta["framework"] == "React"
        assert meta["language"] == "JavaScript/TypeScript"

    def test_nextjs(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name":"myapp","dependencies":{"next":"^14.0","react":"^18.0"}}'
        )
        meta = detect_framework(str(tmp_path))
        assert meta["framework"] == "Next.js"

    def test_unknown(self, tmp_path):
        meta = detect_framework(str(tmp_path))
        assert "language" not in meta or meta.get("language") in (None, "Unknown", "")


class TestIsIndexable:
    def test_python_indexable(self, tmp_path):
        f = tmp_path / "foo.py"
        f.touch()
        assert is_indexable(f) is True

    def test_pyc_not_indexable(self, tmp_path):
        f = tmp_path / "foo.pyc"
        f.touch()
        assert is_indexable(f) is False

    def test_image_not_indexable(self, tmp_path):
        f = tmp_path / "logo.png"
        f.touch()
        assert is_indexable(f) is False

    def test_dockerfile_indexable(self, tmp_path):
        f = tmp_path / "Dockerfile"
        f.touch()
        assert is_indexable(f) is True


class TestFindDbPath:
    def test_finds_db_in_current_dir(self, tmp_path):
        db_dir = tmp_path / ".reza"
        db_dir.mkdir()
        db_file = db_dir / "context.db"
        db_file.touch()
        found = find_db_path(str(tmp_path))
        assert found == db_file

    def test_finds_db_in_parent(self, tmp_path):
        db_dir = tmp_path / ".reza"
        db_dir.mkdir()
        db_file = db_dir / "context.db"
        db_file.touch()
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)
        found = find_db_path(str(subdir))
        assert found == db_file

    def test_returns_none_when_no_db(self, tmp_path):
        found = find_db_path(str(tmp_path))
        assert found is None
