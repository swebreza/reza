"""Blast-radius impact analysis via SQLite recursive CTEs.

Given a set of changed files, traces all reachable nodes through
the code graph edges to find the minimal set of impacted files,
functions, and tests. This is the core token-saving mechanism:
LLMs read only blast-radius files instead of the full codebase.
"""

from __future__ import annotations

import logging
from typing import Any

from .store import GraphStore, GraphNode, GraphEdge

logger = logging.getLogger(__name__)

MAX_IMPACT_DEPTH = 3
MAX_IMPACT_NODES = 500


def get_impact_radius(
    store: GraphStore,
    changed_files: list[str],
    max_depth: int = MAX_IMPACT_DEPTH,
    max_nodes: int = MAX_IMPACT_NODES,
) -> dict[str, Any]:
    """Compute the blast radius from changed files using recursive CTE.

    Walks edges bidirectionally from seed nodes (nodes in changed files)
    up to max_depth hops. Returns:
        - changed_nodes: nodes directly in changed files
        - impacted_nodes: nodes reachable via edges
        - impacted_files: set of affected file paths
        - edges: connecting edges between all involved nodes
        - test_gaps: impacted nodes with no TESTED_BY coverage
        - truncated: whether results were capped
    """
    if not changed_files:
        return _empty_result()

    conn = store._conn

    seeds: set[str] = set()
    for f in changed_files:
        nodes = store.get_nodes_by_file(f)
        for n in nodes:
            seeds.add(n.qualified_name)

    if not seeds:
        return _empty_result()

    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _impact_seeds (qn TEXT PRIMARY KEY)"
    )
    conn.execute("DELETE FROM _impact_seeds")

    batch_size = 450
    seed_list = list(seeds)
    for i in range(0, len(seed_list), batch_size):
        batch = seed_list[i:i + batch_size]
        placeholders = ",".join("(?)" for _ in batch)
        conn.execute(
            f"INSERT OR IGNORE INTO _impact_seeds (qn) VALUES {placeholders}",  # nosec B608
            batch,
        )

    cte_sql = """
    WITH RECURSIVE impacted(node_qn, depth) AS (
        SELECT qn, 0 FROM _impact_seeds
        UNION
        SELECT e.target_qualified, i.depth + 1
        FROM impacted i
        JOIN code_edges e ON e.source_qualified = i.node_qn
        WHERE i.depth < ?
        UNION
        SELECT e.source_qualified, i.depth + 1
        FROM impacted i
        JOIN code_edges e ON e.target_qualified = i.node_qn
        WHERE i.depth < ?
    )
    SELECT DISTINCT node_qn, MIN(depth) AS min_depth
    FROM impacted
    GROUP BY node_qn
    LIMIT ?
    """
    rows = conn.execute(
        cte_sql, (max_depth, max_depth, max_nodes + len(seeds)),
    ).fetchall()

    impacted_qns: set[str] = set()
    for r in rows:
        qn = r[0]
        if qn not in seeds:
            impacted_qns.add(qn)

    changed_nodes = _batch_get_nodes(store, seeds)
    impacted_nodes = _batch_get_nodes(store, impacted_qns)

    total_impacted = len(impacted_nodes)
    truncated = total_impacted > max_nodes
    if truncated:
        impacted_nodes = impacted_nodes[:max_nodes]

    impacted_files = sorted({n.file_path for n in impacted_nodes})

    relevant_edges: list[GraphEdge] = []
    all_qns = seeds | {n.qualified_name for n in impacted_nodes}
    if all_qns:
        relevant_edges = store.get_edges_among(all_qns)

    test_gaps = _find_test_gaps(store, changed_nodes + impacted_nodes)

    return {
        "changed_nodes": changed_nodes,
        "impacted_nodes": impacted_nodes,
        "impacted_files": impacted_files,
        "edges": relevant_edges,
        "test_gaps": test_gaps,
        "truncated": truncated,
        "total_impacted": total_impacted,
    }


def get_compact_context(
    store: GraphStore,
    changed_files: list[str],
    max_depth: int = MAX_IMPACT_DEPTH,
) -> dict[str, Any]:
    """Return a token-compact context summary for LLM consumption.

    Instead of full node objects, returns minimal structural info:
    file paths, function signatures, and edge summaries.
    """
    impact = get_impact_radius(store, changed_files, max_depth=max_depth)

    file_summaries: dict[str, list[str]] = {}
    for node in impact["changed_nodes"] + impact["impacted_nodes"]:
        if node.kind == "File":
            continue
        fp = node.file_path
        sig = _node_signature(node)
        file_summaries.setdefault(fp, []).append(sig)

    edge_summary: list[str] = []
    for edge in impact["edges"]:
        src_short = edge.source_qualified.rsplit("::", 1)[-1]
        tgt_short = edge.target_qualified.rsplit("::", 1)[-1]
        edge_summary.append(f"{src_short} --{edge.kind}--> {tgt_short}")

    return {
        "changed_files": changed_files,
        "impacted_files": impact["impacted_files"],
        "file_signatures": file_summaries,
        "edge_summary": edge_summary[:50],
        "test_gaps": [g["name"] for g in impact["test_gaps"]],
        "total_nodes_in_radius": impact["total_impacted"],
        "truncated": impact["truncated"],
    }


def _node_signature(node: GraphNode) -> str:
    """Build a compact signature string for a node."""
    parts = [node.kind.lower(), node.name]
    if node.params:
        parts.append(node.params)
    if node.return_type:
        parts.append(f"-> {node.return_type}")
    if node.is_test:
        parts.append("[test]")
    return " ".join(parts)


def _batch_get_nodes(
    store: GraphStore, qualified_names: set[str]
) -> list[GraphNode]:
    """Batch fetch nodes by qualified name."""
    if not qualified_names:
        return []
    results: list[GraphNode] = []
    batch_size = 450
    qn_list = list(qualified_names)
    conn = store._conn
    for i in range(0, len(qn_list), batch_size):
        batch = qn_list[i:i + batch_size]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"SELECT * FROM code_nodes WHERE qualified_name IN ({placeholders})",  # nosec B608
            batch,
        ).fetchall()
        results.extend(store._row_to_node(r) for r in rows)
    return results


def _find_test_gaps(
    store: GraphStore, nodes: list[GraphNode]
) -> list[dict]:
    """Find nodes that have no TESTED_BY edge (test coverage gaps)."""
    gaps = []
    conn = store._conn
    for node in nodes:
        if node.kind in ("File", "Test") or node.is_test:
            continue
        row = conn.execute(
            "SELECT 1 FROM code_edges WHERE target_qualified = ? AND kind = 'TESTED_BY' LIMIT 1",
            (node.qualified_name,),
        ).fetchone()
        if not row:
            gaps.append({
                "name": node.name,
                "qualified_name": node.qualified_name,
                "file_path": node.file_path,
                "kind": node.kind,
            })
    return gaps


def _empty_result() -> dict[str, Any]:
    return {
        "changed_nodes": [],
        "impacted_nodes": [],
        "impacted_files": [],
        "edges": [],
        "test_gaps": [],
        "truncated": False,
        "total_impacted": 0,
    }
