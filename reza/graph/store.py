"""SQLite-backed code knowledge graph store.

Stores code structure as nodes (File, Class, Function, Type, Test) and
edges (CALLS, IMPORTS_FROM, INHERITS, CONTAINS, TESTED_BY, REFERENCES).
Shares reza's context.db for unified conversation + code awareness.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .parser import NodeInfo, EdgeInfo

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    id: int
    kind: str
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    language: str
    parent_name: Optional[str]
    params: Optional[str]
    return_type: Optional[str]
    is_test: bool
    file_hash: Optional[str]
    extra: dict


@dataclass
class GraphEdge:
    id: int
    kind: str
    source_qualified: str
    target_qualified: str
    file_path: str
    line: int
    extra: dict
    confidence: float = 1.0
    confidence_tier: str = "EXTRACTED"


@dataclass
class GraphStats:
    total_nodes: int
    total_edges: int
    nodes_by_kind: dict[str, int]
    edges_by_kind: dict[str, int]
    languages: list[str]
    files_count: int
    last_updated: Optional[str]


class GraphStore:
    """SQLite-backed code knowledge graph using reza's shared context.db."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(
            str(self.db_path), timeout=30, check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        # Perf: WAL + NORMAL sync is safe (durable to OS crash, not power loss)
        # and 5–20x faster on Windows NTFS than FULL.
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA cache_size=-65536")  # ~64 MiB page cache
        self._ensure_tables()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _ensure_tables(self) -> None:
        """Ensure graph tables exist (idempotent)."""
        try:
            self._conn.execute("SELECT 1 FROM code_nodes LIMIT 1")
        except sqlite3.OperationalError:
            from ..schema import GRAPH_SCHEMA
            self._conn.executescript(GRAPH_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- Write operations ---

    def _make_qualified(self, node: NodeInfo) -> str:
        fp = node.file_path.replace("\\", "/")
        if node.parent_name:
            return f"{fp}::{node.parent_name}::{node.name}"
        return f"{fp}::{node.name}"

    def upsert_node(self, node: NodeInfo, file_hash: str = "") -> int:
        now = time.time()
        qualified = self._make_qualified(node)
        extra = json.dumps(node.extra) if node.extra else "{}"

        self._conn.execute(
            """INSERT INTO code_nodes
               (kind, name, qualified_name, file_path, line_start, line_end,
                language, parent_name, params, return_type, is_test,
                file_hash, extra, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(qualified_name) DO UPDATE SET
                kind=excluded.kind, name=excluded.name,
                file_path=excluded.file_path, line_start=excluded.line_start,
                line_end=excluded.line_end, language=excluded.language,
                parent_name=excluded.parent_name, params=excluded.params,
                return_type=excluded.return_type,
                is_test=excluded.is_test, file_hash=excluded.file_hash,
                extra=excluded.extra, updated_at=excluded.updated_at
            """,
            (
                node.kind, node.name, qualified, node.file_path,
                node.line_start, node.line_end, node.language,
                node.parent_name, node.params, node.return_type,
                int(node.is_test), file_hash, extra, now,
            ),
        )
        row = self._conn.execute(
            "SELECT id FROM code_nodes WHERE qualified_name = ?", (qualified,)
        ).fetchone()
        return row["id"]

    def upsert_edge(self, edge: EdgeInfo) -> int:
        now = time.time()
        extra_dict = edge.extra if edge.extra else {}
        confidence = float(extra_dict.get("confidence", 1.0))
        confidence_tier = str(extra_dict.get("confidence_tier", "EXTRACTED"))
        extra = json.dumps(extra_dict)

        existing = self._conn.execute(
            """SELECT id FROM code_edges
               WHERE kind=? AND source_qualified=? AND target_qualified=?
               AND file_path=? AND line=?""",
            (edge.kind, edge.source, edge.target, edge.file_path, edge.line),
        ).fetchone()

        if existing:
            self._conn.execute(
                "UPDATE code_edges SET extra=?, confidence=?, confidence_tier=?,"
                " updated_at=? WHERE id=?",
                (extra, confidence, confidence_tier, now, existing["id"]),
            )
            return existing["id"]

        self._conn.execute(
            """INSERT INTO code_edges
               (kind, source_qualified, target_qualified, file_path, line, extra,
                confidence, confidence_tier, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (edge.kind, edge.source, edge.target, edge.file_path, edge.line,
             extra, confidence, confidence_tier, now),
        )
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _delete_graph_rows_for_file(self, file_path: str) -> None:
        """Delete rows for one file without committing (for use inside a transaction)."""
        self._conn.execute("DELETE FROM code_nodes WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM code_edges WHERE file_path = ?", (file_path,))

    def remove_file_data(self, file_path: str) -> None:
        """Delete all graph data for a file and commit immediately."""
        self._delete_graph_rows_for_file(file_path)
        self._conn.commit()

    def store_file_nodes_edges(
        self, file_path: str, nodes: list[NodeInfo], edges: list[EdgeInfo],
        fhash: str = "",
    ) -> None:
        """Atomically replace all graph data for a file."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._delete_graph_rows_for_file(file_path)
            for node in nodes:
                self.upsert_node(node, file_hash=fhash)
            for edge in edges:
                self.upsert_edge(edge)
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def bulk_store_files(
        self,
        items: list[tuple[str, list[NodeInfo], list[EdgeInfo], str]],
    ) -> None:
        """Atomically replace graph data for **many files** in one transaction.

        Massively faster than calling :meth:`store_file_nodes_edges` per file
        because SQLite commits once (one fsync) instead of once per file. On
        Windows NTFS this is often a 10–50× speedup for large builds.

        Edges use ``INSERT OR REPLACE`` keyed on the natural tuple
        ``(kind, source, target, file_path, line)`` — no per-edge SELECT.

        items: list of (file_path, nodes, edges, file_hash)
        """
        if not items:
            return

        now = time.time()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for file_path, _, _, _ in items:
                self._delete_graph_rows_for_file(file_path)

            for _, nodes, _, fhash in items:
                if not nodes:
                    continue
                payloads = []
                for n in nodes:
                    qualified = self._make_qualified(n)
                    extra = json.dumps(n.extra) if n.extra else "{}"
                    payloads.append(
                        (
                            n.kind, n.name, qualified, n.file_path,
                            n.line_start, n.line_end, n.language,
                            n.parent_name, n.params, n.return_type,
                            int(n.is_test), fhash, extra, now,
                        )
                    )
                self._conn.executemany(
                    """INSERT INTO code_nodes
                       (kind, name, qualified_name, file_path, line_start, line_end,
                        language, parent_name, params, return_type, is_test,
                        file_hash, extra, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(qualified_name) DO UPDATE SET
                        kind=excluded.kind, name=excluded.name,
                        file_path=excluded.file_path, line_start=excluded.line_start,
                        line_end=excluded.line_end, language=excluded.language,
                        parent_name=excluded.parent_name, params=excluded.params,
                        return_type=excluded.return_type,
                        is_test=excluded.is_test, file_hash=excluded.file_hash,
                        extra=excluded.extra, updated_at=excluded.updated_at
                    """,
                    payloads,
                )

            for _, _, edges, _ in items:
                if not edges:
                    continue
                epayloads = []
                for e in edges:
                    extra_dict = e.extra if e.extra else {}
                    confidence = float(extra_dict.get("confidence", 1.0))
                    tier = str(extra_dict.get("confidence_tier", "EXTRACTED"))
                    extra = json.dumps(extra_dict)
                    epayloads.append(
                        (
                            e.kind, e.source, e.target, e.file_path, e.line,
                            extra, confidence, tier, now,
                        )
                    )
                self._conn.executemany(
                    """INSERT INTO code_edges
                       (kind, source_qualified, target_qualified, file_path, line,
                        extra, confidence, confidence_tier, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    epayloads,
                )

            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def set_metadata(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO code_graph_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def get_metadata(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM code_graph_meta WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def commit(self) -> None:
        self._conn.commit()

    # --- Read operations ---

    def get_node(self, qualified_name: str) -> Optional[GraphNode]:
        row = self._conn.execute(
            "SELECT * FROM code_nodes WHERE qualified_name = ?", (qualified_name,)
        ).fetchone()
        return self._row_to_node(row) if row else None

    def get_nodes_by_file(self, file_path: str) -> list[GraphNode]:
        rows = self._conn.execute(
            "SELECT * FROM code_nodes WHERE file_path = ?", (file_path,)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_all_nodes(self, exclude_files: bool = True) -> list[GraphNode]:
        if exclude_files:
            rows = self._conn.execute(
                "SELECT * FROM code_nodes WHERE kind != 'File'"
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM code_nodes").fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_edges_by_source(self, qualified_name: str) -> list[GraphEdge]:
        rows = self._conn.execute(
            "SELECT * FROM code_edges WHERE source_qualified = ?", (qualified_name,)
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def get_edges_by_target(self, qualified_name: str) -> list[GraphEdge]:
        rows = self._conn.execute(
            "SELECT * FROM code_edges WHERE target_qualified = ?", (qualified_name,)
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def search_nodes(self, query: str, limit: int = 20) -> list[GraphNode]:
        """Search code nodes by name using FTS5 with LIKE fallback."""
        words = query.split()
        if not words:
            return []

        try:
            if len(words) == 1:
                fts_query = '"' + query.replace('"', '""') + '"'
            else:
                fts_query = " AND ".join(
                    '"' + w.replace('"', '""') + '"' for w in words
                )
            rows = self._conn.execute(
                "SELECT n.* FROM code_nodes_fts f "
                "JOIN code_nodes n ON f.node_id = n.id "
                "WHERE code_nodes_fts MATCH ? LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            if rows:
                return [self._row_to_node(r) for r in rows]
        except Exception:
            pass

        conditions: list[str] = []
        params: list[Any] = []
        for word in words:
            w = word.lower()
            conditions.append(
                "(LOWER(name) LIKE ? OR LOWER(qualified_name) LIKE ?)"
            )
            params.extend([f"%{w}%", f"%{w}%"])

        where = " AND ".join(conditions)
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM code_nodes WHERE {where} LIMIT ?", params  # nosec B608
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_stats(self) -> GraphStats:
        total_nodes = self._conn.execute(
            "SELECT COUNT(*) FROM code_nodes"
        ).fetchone()[0]
        total_edges = self._conn.execute(
            "SELECT COUNT(*) FROM code_edges"
        ).fetchone()[0]

        nodes_by_kind = {}
        for row in self._conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM code_nodes GROUP BY kind"
        ).fetchall():
            nodes_by_kind[row["kind"]] = row["cnt"]

        edges_by_kind = {}
        for row in self._conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM code_edges GROUP BY kind"
        ).fetchall():
            edges_by_kind[row["kind"]] = row["cnt"]

        languages = [
            row[0] for row in self._conn.execute(
                "SELECT DISTINCT language FROM code_nodes WHERE language IS NOT NULL "
                "AND language != ''"
            ).fetchall()
        ]

        files_count = self._conn.execute(
            "SELECT COUNT(*) FROM code_nodes WHERE kind = 'File'"
        ).fetchone()[0]

        last_updated = self.get_metadata("last_build_time")

        return GraphStats(
            total_nodes=total_nodes,
            total_edges=total_edges,
            nodes_by_kind=nodes_by_kind,
            edges_by_kind=edges_by_kind,
            languages=languages,
            files_count=files_count,
            last_updated=last_updated,
        )

    def get_edges_among(self, qualified_names: set[str]) -> list[GraphEdge]:
        """Get all edges between the given set of qualified names."""
        if not qualified_names:
            return []
        batch_size = 450
        qn_list = list(qualified_names)
        all_edges: list[GraphEdge] = []
        for i in range(0, len(qn_list), batch_size):
            batch = qn_list[i:i + batch_size]
            placeholders = ",".join("?" for _ in batch)
            rows = self._conn.execute(
                f"SELECT * FROM code_edges WHERE source_qualified IN ({placeholders}) "  # nosec B608
                f"AND target_qualified IN ({placeholders})",
                batch + batch,
            ).fetchall()
            all_edges.extend(self._row_to_edge(r) for r in rows)
        return all_edges

    # --- Helpers ---

    def _row_to_node(self, row) -> GraphNode:
        extra = {}
        try:
            extra = json.loads(row["extra"]) if row["extra"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        return GraphNode(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            file_path=row["file_path"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            language=row["language"] or "",
            parent_name=row["parent_name"],
            params=row["params"],
            return_type=row["return_type"],
            is_test=bool(row["is_test"]),
            file_hash=row["file_hash"],
            extra=extra,
        )

    def _row_to_edge(self, row) -> GraphEdge:
        extra = {}
        try:
            extra = json.loads(row["extra"]) if row["extra"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        return GraphEdge(
            id=row["id"],
            kind=row["kind"],
            source_qualified=row["source_qualified"],
            target_qualified=row["target_qualified"],
            file_path=row["file_path"],
            line=row["line"],
            extra=extra,
            confidence=row["confidence"],
            confidence_tier=row["confidence_tier"],
        )
