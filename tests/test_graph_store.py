"""Tests for the graph store module."""

import sqlite3
import pytest
from pathlib import Path

from reza.schema import init_schema, GRAPH_SCHEMA
from reza.graph.store import GraphStore, GraphNode, GraphEdge
from reza.graph.parser import NodeInfo, EdgeInfo


@pytest.fixture
def db_path(tmp_path):
    """Create a fresh DB with full schema including graph tables."""
    db = tmp_path / ".reza" / "context.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    conn.close()
    return db


@pytest.fixture
def store(db_path):
    s = GraphStore(db_path)
    yield s
    s.close()


class TestGraphStoreWrite:
    def test_upsert_node(self, store):
        node = NodeInfo(
            kind="Function", name="login", file_path="src/auth.py",
            line_start=10, line_end=20, language="python",
        )
        node_id = store.upsert_node(node)
        assert node_id > 0

    def test_upsert_node_deduplicates(self, store):
        node = NodeInfo(
            kind="Function", name="login", file_path="src/auth.py",
            line_start=10, line_end=20, language="python",
        )
        id1 = store.upsert_node(node)
        id2 = store.upsert_node(node)
        assert id1 == id2

    def test_upsert_edge(self, store):
        edge = EdgeInfo(
            kind="CALLS", source="src/api.py::handle_request",
            target="src/auth.py::login", file_path="src/api.py", line=15,
        )
        edge_id = store.upsert_edge(edge)
        assert edge_id > 0

    def test_upsert_edge_deduplicates(self, store):
        edge = EdgeInfo(
            kind="CALLS", source="src/api.py::handle",
            target="src/auth.py::login", file_path="src/api.py", line=15,
        )
        id1 = store.upsert_edge(edge)
        id2 = store.upsert_edge(edge)
        assert id1 == id2

    def test_store_file_nodes_edges(self, store):
        nodes = [
            NodeInfo(kind="File", name="auth.py", file_path="src/auth.py",
                     line_start=1, line_end=50, language="python"),
            NodeInfo(kind="Function", name="login", file_path="src/auth.py",
                     line_start=5, line_end=20, language="python"),
        ]
        edges = [
            EdgeInfo(kind="CONTAINS", source="src/auth.py",
                     target="src/auth.py::login", file_path="src/auth.py", line=5),
        ]
        store.store_file_nodes_edges("src/auth.py", nodes, edges, fhash="abc123")
        retrieved = store.get_nodes_by_file("src/auth.py")
        assert len(retrieved) == 2

    def test_remove_file_data(self, store):
        nodes = [
            NodeInfo(kind="File", name="x.py", file_path="x.py",
                     line_start=1, line_end=10, language="python"),
        ]
        store.store_file_nodes_edges("x.py", nodes, [], fhash="aaa")
        assert len(store.get_nodes_by_file("x.py")) == 1
        store.remove_file_data("x.py")
        store.commit()
        assert len(store.get_nodes_by_file("x.py")) == 0

    def test_metadata(self, store):
        store.set_metadata("test_key", "test_value")
        assert store.get_metadata("test_key") == "test_value"
        assert store.get_metadata("nonexistent") is None


class TestGraphStoreRead:
    def _populate(self, store):
        nodes = [
            NodeInfo(kind="File", name="auth.py", file_path="src/auth.py",
                     line_start=1, line_end=50, language="python"),
            NodeInfo(kind="Class", name="AuthService", file_path="src/auth.py",
                     line_start=3, line_end=40, language="python"),
            NodeInfo(kind="Function", name="login", file_path="src/auth.py",
                     line_start=5, line_end=20, language="python",
                     parent_name="AuthService", params="(user, pwd)"),
            NodeInfo(kind="Function", name="logout", file_path="src/auth.py",
                     line_start=22, line_end=35, language="python",
                     parent_name="AuthService"),
        ]
        edges = [
            EdgeInfo(kind="CONTAINS", source="src/auth.py",
                     target="src/auth.py::AuthService", file_path="src/auth.py"),
            EdgeInfo(kind="CONTAINS", source="src/auth.py::AuthService",
                     target="src/auth.py::AuthService::login", file_path="src/auth.py"),
            EdgeInfo(kind="CONTAINS", source="src/auth.py::AuthService",
                     target="src/auth.py::AuthService::logout", file_path="src/auth.py"),
        ]
        store.store_file_nodes_edges("src/auth.py", nodes, edges, fhash="abc")

    def test_get_node(self, store):
        self._populate(store)
        node = store.get_node("src/auth.py::AuthService")
        assert node is not None
        assert node.kind == "Class"
        assert node.name == "AuthService"

    def test_get_nodes_by_file(self, store):
        self._populate(store)
        nodes = store.get_nodes_by_file("src/auth.py")
        assert len(nodes) == 4
        kinds = {n.kind for n in nodes}
        assert "File" in kinds
        assert "Class" in kinds
        assert "Function" in kinds

    def test_get_edges_by_source(self, store):
        self._populate(store)
        edges = store.get_edges_by_source("src/auth.py::AuthService")
        assert len(edges) == 2
        assert all(e.kind == "CONTAINS" for e in edges)

    def test_get_edges_by_target(self, store):
        self._populate(store)
        edges = store.get_edges_by_target("src/auth.py::AuthService::login")
        assert len(edges) == 1
        assert edges[0].kind == "CONTAINS"

    def test_search_nodes(self, store):
        self._populate(store)
        results = store.search_nodes("login")
        assert len(results) >= 1
        assert any(n.name == "login" for n in results)

    def test_search_nodes_no_results(self, store):
        self._populate(store)
        results = store.search_nodes("zzz_nonexistent_zzz")
        assert len(results) == 0

    def test_get_stats(self, store):
        self._populate(store)
        stats = store.get_stats()
        assert stats.total_nodes == 4
        assert stats.total_edges == 3
        assert "python" in stats.languages
        assert stats.files_count == 1
        assert "Class" in stats.nodes_by_kind
        assert "CONTAINS" in stats.edges_by_kind

    def test_get_edges_among(self, store):
        self._populate(store)
        qns = {
            "src/auth.py::AuthService",
            "src/auth.py::AuthService::login",
            "src/auth.py::AuthService::logout",
        }
        edges = store.get_edges_among(qns)
        assert len(edges) == 2

    def test_get_all_nodes_excludes_files(self, store):
        self._populate(store)
        nodes = store.get_all_nodes(exclude_files=True)
        assert all(n.kind != "File" for n in nodes)

    def test_get_all_nodes_includes_files(self, store):
        self._populate(store)
        nodes = store.get_all_nodes(exclude_files=False)
        assert any(n.kind == "File" for n in nodes)
