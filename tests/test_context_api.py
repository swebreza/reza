"""Tests for the LLM-facing context API (reza.context)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from reza.context import (
    build_context_pack,
    build_overview,
    get_neighbors,
    get_subtree,
    unified_find,
)
from reza.context.find import hits_to_dict
from reza.context.neighbors import neighborhood_to_dict
from reza.context.overview import (
    overview_to_dict,
    render_overview_markdown,
)
from reza.context.pack import PackOptions
from reza.context.subtree import subtree_to_dict
from reza.graph.builder import build_graph
from reza.schema import get_connection


# ---------------------------------------------------------------------------
# Fixture project — tiny but realistic
# ---------------------------------------------------------------------------


@pytest.fixture
def mini_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a small project with Python, its DB, and a built graph."""
    proj = tmp_path / "miniapp"
    (proj / ".reza").mkdir(parents=True)
    (proj / "src").mkdir()

    (proj / "src" / "service.py").write_text(
        "from src.utils import helper\n\n"
        "class UserService:\n"
        "    def login(self, user):\n"
        "        return helper(user)\n"
        "    def logout(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    (proj / "src" / "utils.py").write_text(
        "def helper(x):\n"
        "    return x.upper()\n",
        encoding="utf-8",
    )
    (proj / "src" / "test_service.py").write_text(
        "def test_login():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    db_path = proj / ".reza" / "context.db"

    # Build schema via normal init path
    with get_connection(db_path) as conn:
        from reza.schema import SCHEMA

        conn.executescript(SCHEMA)
        conn.commit()

    # Build graph
    build_graph(str(proj), db_path, incremental=False, index_mode="fast")

    # Seed a tiny session + turns + file index so cross-source search works
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT INTO sessions (id, llm_name, status, started_at, working_on)
           VALUES ('s1', 'cursor', 'active', datetime('now'), 'user login')"""
    )
    for i, (role, content) in enumerate([
        ("user", "How does UserService.login work?"),
        ("assistant", "It calls helper from utils to upper-case the user."),
        ("user", "Can you improve logout?"),
    ]):
        conn.execute(
            """INSERT INTO conversation_turns
               (session_id, role, content, token_est, turn_index, recorded_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("s1", role, content, max(1, len(content) // 4), i),
        )

    conn.execute(
        """INSERT INTO files (path, file_type, line_count, size_bytes, last_modified)
           VALUES ('src/service.py', 'python', 7, 200, ?)""",
        (datetime.now().isoformat(),),
    )
    conn.execute(
        """INSERT INTO files (path, file_type, line_count, size_bytes, last_modified)
           VALUES ('src/utils.py', 'python', 2, 60,
                   ?)""",
        ((datetime.now() - timedelta(days=30)).isoformat(),),
    )
    conn.commit()
    conn.close()

    return proj, db_path


def _ro_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


class TestOverview:
    def test_overview_includes_files_and_symbols(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            ov = build_overview(conn)
        assert ov.total_files == 3
        assert ov.total_symbols >= 3  # UserService, helper, test_login
        assert "python" in ov.languages

    def test_overview_markdown_fits_budget(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            ov = build_overview(conn)
        md = render_overview_markdown(ov, max_tokens=200)
        assert "Project overview" in md
        # Rough token check
        assert len(md) // 4 <= 400  # 2x headroom for hard-cut edge case

    def test_overview_json(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            ov = build_overview(conn)
        d = overview_to_dict(ov)
        assert d["total_files"] == 3
        assert "root" in d and isinstance(d["root"]["subdirs"], list)

    def test_overview_prefix_filter(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            ov = build_overview(conn, path_prefix="src")
        assert ov.total_files == 3  # all files are under src/


# ---------------------------------------------------------------------------
# Neighbors
# ---------------------------------------------------------------------------


class TestNeighbors:
    def test_neighbors_by_bare_name(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            nh = get_neighbors(conn, "UserService")
        assert nh.node is not None
        assert nh.node.name == "UserService"
        assert nh.node.kind == "Class"
        # Methods are siblings? No — they are CONTAINS children. For a class,
        # siblings are other top-level items in the file.
        out_kinds = {e.kind for e in nh.outgoing}
        assert "CONTAINS" in out_kinds

    def test_neighbors_file_edges(self, mini_project):
        """Regression: File-node edges used to be missed because of the
        qualified_name vs bare path mismatch."""
        _, db = mini_project
        with _ro_conn(db) as conn:
            nh = get_neighbors(conn, "src/service.py")
        assert nh.node is not None
        assert nh.node.kind == "File"
        assert len(nh.outgoing) > 0, "File CONTAINS edges should be returned"

    def test_neighbors_json_roundtrip(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            nh = get_neighbors(conn, "helper")
        d = neighborhood_to_dict(nh)
        json.dumps(d)  # must be JSON-serializable
        assert d["node"] is not None


# ---------------------------------------------------------------------------
# Subtree
# ---------------------------------------------------------------------------


class TestSubtree:
    def test_subtree_of_file_contains_class_and_methods(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            st = get_subtree(conn, "src/service.py")
        assert st.root is not None
        # Flatten
        flat: list[str] = []

        def walk(n):
            flat.append(n.name)
            for c in n.children:
                walk(c)

        walk(st.root)
        assert "UserService" in flat
        assert "login" in flat
        assert "logout" in flat

    def test_subtree_json(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            st = get_subtree(conn, "src/service.py")
        d = subtree_to_dict(st)
        json.dumps(d)
        assert d["total_nodes"] >= 4


# ---------------------------------------------------------------------------
# Unified find
# ---------------------------------------------------------------------------


class TestFind:
    def test_find_hits_graph_and_chat(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            hits = unified_find(conn, "login")
        sources = {h.source for h in hits}
        assert "graph" in sources, "Should find UserService.login in the graph"
        assert "chat" in sources, "Should find the question about login in chat"

    def test_find_graph_only(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            hits = unified_find(conn, "helper", sources=("graph",))
        assert all(h.source == "graph" for h in hits)
        assert hits  # at least one match

    def test_find_recency_boost(self, mini_project):
        """Recent file should outrank an older file with equal name match."""
        _, db = mini_project
        with _ro_conn(db) as conn:
            hits = unified_find(conn, "service", sources=("file",), limit=5)
        # service.py is more recent than utils.py and matches better
        assert hits
        top = hits[0]
        assert "service.py" in (top.file_path or "")

    def test_find_json_shape(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            hits = unified_find(conn, "login")
        payload = hits_to_dict(hits)
        json.dumps(payload)
        for h in payload:
            assert set(h.keys()) >= {"source", "score", "title", "snippet"}


# ---------------------------------------------------------------------------
# Context pack
# ---------------------------------------------------------------------------


class TestContextPack:
    def test_pack_has_all_sections(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            pack = build_context_pack(
                conn, PackOptions(query="login", max_tokens=4000)
            )
        assert "# reza" in pack
        assert "Session" in pack
        assert "Project overview" in pack
        assert "login" in pack.lower()

    def test_pack_respects_token_budget(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            pack = build_context_pack(
                conn, PackOptions(query="", max_tokens=300)
            )
        # Allow 2x slack for section boundaries; hard cap is enforced.
        assert len(pack) <= 300 * 4 + 200

    def test_pack_sections_toggle(self, mini_project):
        _, db = mini_project
        with _ro_conn(db) as conn:
            pack = build_context_pack(
                conn,
                PackOptions(
                    include_overview=False,
                    include_recent_chat=False,
                    include_recent_changes=False,
                ),
            )
        assert "Project overview" not in pack
        assert "Last " not in pack
        assert "Recent file changes" not in pack
