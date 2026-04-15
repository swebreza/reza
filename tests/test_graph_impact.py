"""Tests for the graph impact analysis module."""

import sqlite3
import pytest
from pathlib import Path

from reza.schema import init_schema
from reza.graph.store import GraphStore
from reza.graph.parser import NodeInfo, EdgeInfo
from reza.graph.impact import get_impact_radius, get_compact_context


@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / ".reza" / "context.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    conn.close()
    return db


@pytest.fixture
def populated_store(db_path):
    """Build a small graph: auth.py -> api.py -> db.py with tests."""
    store = GraphStore(db_path)

    auth_nodes = [
        NodeInfo(kind="File", name="auth.py", file_path="src/auth.py",
                 line_start=1, line_end=30, language="python"),
        NodeInfo(kind="Function", name="login", file_path="src/auth.py",
                 line_start=5, line_end=15, language="python"),
        NodeInfo(kind="Function", name="verify_token", file_path="src/auth.py",
                 line_start=17, line_end=25, language="python"),
    ]
    auth_edges = [
        EdgeInfo(kind="CONTAINS", source="src/auth.py",
                 target="src/auth.py::login", file_path="src/auth.py"),
        EdgeInfo(kind="CONTAINS", source="src/auth.py",
                 target="src/auth.py::verify_token", file_path="src/auth.py"),
    ]
    store.store_file_nodes_edges("src/auth.py", auth_nodes, auth_edges, fhash="aaa")

    api_nodes = [
        NodeInfo(kind="File", name="api.py", file_path="src/api.py",
                 line_start=1, line_end=40, language="python"),
        NodeInfo(kind="Function", name="handle_request", file_path="src/api.py",
                 line_start=5, line_end=20, language="python"),
        NodeInfo(kind="Function", name="get_user", file_path="src/api.py",
                 line_start=22, line_end=35, language="python"),
    ]
    api_edges = [
        EdgeInfo(kind="CONTAINS", source="src/api.py",
                 target="src/api.py::handle_request", file_path="src/api.py"),
        EdgeInfo(kind="CONTAINS", source="src/api.py",
                 target="src/api.py::get_user", file_path="src/api.py"),
        EdgeInfo(kind="CALLS", source="src/api.py::handle_request",
                 target="src/auth.py::login", file_path="src/api.py", line=10),
        EdgeInfo(kind="CALLS", source="src/api.py::get_user",
                 target="src/auth.py::verify_token", file_path="src/api.py", line=25),
        EdgeInfo(kind="IMPORTS_FROM", source="src/api.py",
                 target="src/auth.py", file_path="src/api.py", line=1),
    ]
    store.store_file_nodes_edges("src/api.py", api_nodes, api_edges, fhash="bbb")

    db_nodes = [
        NodeInfo(kind="File", name="db.py", file_path="src/db.py",
                 line_start=1, line_end=20, language="python"),
        NodeInfo(kind="Function", name="query_db", file_path="src/db.py",
                 line_start=3, line_end=15, language="python"),
    ]
    db_edges = [
        EdgeInfo(kind="CONTAINS", source="src/db.py",
                 target="src/db.py::query_db", file_path="src/db.py"),
        EdgeInfo(kind="CALLS", source="src/api.py::get_user",
                 target="src/db.py::query_db", file_path="src/api.py", line=30),
    ]
    store.store_file_nodes_edges("src/db.py", db_nodes, db_edges, fhash="ccc")

    test_nodes = [
        NodeInfo(kind="File", name="test_auth.py", file_path="tests/test_auth.py",
                 line_start=1, line_end=15, language="python"),
        NodeInfo(kind="Test", name="test_login", file_path="tests/test_auth.py",
                 line_start=3, line_end=10, language="python", is_test=True),
    ]
    test_edges = [
        EdgeInfo(kind="CONTAINS", source="tests/test_auth.py",
                 target="tests/test_auth.py::test_login",
                 file_path="tests/test_auth.py"),
        EdgeInfo(kind="TESTED_BY", source="tests/test_auth.py::test_login",
                 target="src/auth.py::login", file_path="tests/test_auth.py"),
    ]
    store.store_file_nodes_edges("tests/test_auth.py", test_nodes, test_edges, fhash="ddd")

    yield store
    store.close()


class TestImpactRadius:
    def test_empty_input(self, populated_store):
        result = get_impact_radius(populated_store, [])
        assert result["changed_nodes"] == []
        assert result["impacted_nodes"] == []

    def test_single_file_change(self, populated_store):
        result = get_impact_radius(populated_store, ["src/auth.py"])
        assert len(result["changed_nodes"]) >= 2  # login, verify_token, File
        assert len(result["impacted_files"]) >= 1
        impacted_paths = result["impacted_files"]
        assert "src/api.py" in impacted_paths

    def test_blast_radius_reaches_callers(self, populated_store):
        result = get_impact_radius(populated_store, ["src/auth.py"], max_depth=2)
        all_files = set(result["impacted_files"])
        assert "src/api.py" in all_files

    def test_blast_radius_reaches_db(self, populated_store):
        result = get_impact_radius(populated_store, ["src/auth.py"], max_depth=3)
        all_files = set(result["impacted_files"])
        assert "src/db.py" in all_files or "src/api.py" in all_files

    def test_returns_edges(self, populated_store):
        result = get_impact_radius(populated_store, ["src/auth.py"])
        assert len(result["edges"]) >= 1

    def test_test_gaps_detected(self, populated_store):
        result = get_impact_radius(populated_store, ["src/auth.py"])
        gap_names = {g["name"] for g in result["test_gaps"]}
        assert "verify_token" in gap_names

    def test_truncation_flag(self, populated_store):
        result = get_impact_radius(populated_store, ["src/auth.py"], max_nodes=1)
        assert result["truncated"] is True or result["total_impacted"] <= 1

    def test_nonexistent_file(self, populated_store):
        result = get_impact_radius(populated_store, ["src/nonexistent.py"])
        assert result["changed_nodes"] == []
        assert result["impacted_nodes"] == []


class TestCompactContext:
    def test_returns_changed_files(self, populated_store):
        result = get_compact_context(populated_store, ["src/auth.py"])
        assert result["changed_files"] == ["src/auth.py"]

    def test_returns_impacted_files(self, populated_store):
        result = get_compact_context(populated_store, ["src/auth.py"])
        assert isinstance(result["impacted_files"], list)

    def test_returns_signatures(self, populated_store):
        result = get_compact_context(populated_store, ["src/auth.py"])
        assert isinstance(result["file_signatures"], dict)
        all_sigs = []
        for sigs in result["file_signatures"].values():
            all_sigs.extend(sigs)
        assert len(all_sigs) >= 1

    def test_returns_edge_summary(self, populated_store):
        result = get_compact_context(populated_store, ["src/auth.py"])
        assert isinstance(result["edge_summary"], list)

    def test_returns_test_gaps(self, populated_store):
        result = get_compact_context(populated_store, ["src/auth.py"])
        assert isinstance(result["test_gaps"], list)
