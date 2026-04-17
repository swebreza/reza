"""Neighborhood expansion for a single graph node.

Given a qualified name, returns:
- the node itself
- outgoing edges (what it depends on / calls / inherits from / contains)
- incoming edges (what depends on it / calls it / contains it)
- siblings (nodes in the same parent container)
- optional 2-hop expansion

Designed so an LLM can drill into one specific node and read only its
immediate context instead of the whole graph.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NeighborNode:
    qualified_name: str
    kind: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    language: str = ""
    parent_name: Optional[str] = None


@dataclass
class NeighborEdge:
    kind: str
    source: str
    target: str
    line: int
    confidence_tier: str = "EXTRACTED"


@dataclass
class Neighborhood:
    node: Optional[NeighborNode]
    outgoing: list[NeighborEdge] = field(default_factory=list)
    incoming: list[NeighborEdge] = field(default_factory=list)
    siblings: list[NeighborNode] = field(default_factory=list)
    expanded: list[NeighborNode] = field(default_factory=list)  # 2-hop


def _row_to_node(row: sqlite3.Row) -> NeighborNode:
    return NeighborNode(
        qualified_name=row["qualified_name"],
        kind=row["kind"],
        name=row["name"],
        file_path=row["file_path"],
        line_start=row["line_start"] or 0,
        line_end=row["line_end"] or 0,
        language=row["language"] or "",
        parent_name=row["parent_name"],
    )


def _row_to_edge(row: sqlite3.Row) -> NeighborEdge:
    return NeighborEdge(
        kind=row["kind"],
        source=row["source_qualified"],
        target=row["target_qualified"],
        line=row["line"] or 0,
        confidence_tier=row["confidence_tier"] or "EXTRACTED",
    )


def _resolve_qualified_name(
    conn: sqlite3.Connection, query: str
) -> Optional[NeighborNode]:
    """Accept an exact qualified_name, a bare symbol name, or a file path."""
    row = conn.execute(
        "SELECT * FROM code_nodes WHERE qualified_name = ? LIMIT 1", (query,)
    ).fetchone()
    if row:
        return _row_to_node(row)

    row = conn.execute(
        "SELECT * FROM code_nodes WHERE file_path = ? AND kind='File' LIMIT 1",
        (query.replace("\\", "/"),),
    ).fetchone()
    if row:
        return _row_to_node(row)

    rows = conn.execute(
        "SELECT * FROM code_nodes WHERE name = ? AND kind != 'File' LIMIT 2",
        (query,),
    ).fetchall()
    if len(rows) == 1:
        return _row_to_node(rows[0])
    return None


def get_neighbors(
    conn: sqlite3.Connection,
    qualified_name_or_query: str,
    *,
    hops: int = 1,
    max_edges_per_side: int = 50,
    max_siblings: int = 30,
) -> Neighborhood:
    """Return node + incoming/outgoing + siblings. Optionally 2-hop expand."""
    node = _resolve_qualified_name(conn, qualified_name_or_query)
    nh = Neighborhood(node=node)
    if not node:
        return nh

    qn = node.qualified_name

    # File nodes have qualified_name ``path::filename`` but edges emitted by
    # the parser use the bare ``path`` as source/target — accept both.
    search_keys: tuple[str, ...]
    if node.kind == "File" and node.file_path and node.file_path != qn:
        search_keys = (qn, node.file_path)
    else:
        search_keys = (qn,)

    placeholders = ",".join("?" for _ in search_keys)
    out_rows = conn.execute(
        f"SELECT * FROM code_edges WHERE source_qualified IN ({placeholders})"  # nosec B608
        f" LIMIT ?",
        (*search_keys, max_edges_per_side),
    ).fetchall()
    nh.outgoing = [_row_to_edge(r) for r in out_rows]

    in_rows = conn.execute(
        f"SELECT * FROM code_edges WHERE target_qualified IN ({placeholders})"  # nosec B608
        f" LIMIT ?",
        (*search_keys, max_edges_per_side),
    ).fetchall()
    nh.incoming = [_row_to_edge(r) for r in in_rows]

    # Siblings — same file and same parent_name (or same parent file if File)
    if node.kind == "File":
        sib_rows = conn.execute(
            """SELECT * FROM code_nodes
               WHERE file_path = ? AND kind != 'File' AND parent_name IS NULL
               LIMIT ?""",
            (node.file_path, max_siblings),
        ).fetchall()
    else:
        if node.parent_name is None:
            sib_rows = conn.execute(
                """SELECT * FROM code_nodes
                   WHERE file_path = ? AND kind != 'File'
                     AND parent_name IS NULL
                     AND qualified_name != ?
                   LIMIT ?""",
                (node.file_path, qn, max_siblings),
            ).fetchall()
        else:
            sib_rows = conn.execute(
                """SELECT * FROM code_nodes
                   WHERE file_path = ? AND parent_name = ?
                     AND qualified_name != ?
                   LIMIT ?""",
                (node.file_path, node.parent_name, qn, max_siblings),
            ).fetchall()
    nh.siblings = [_row_to_node(r) for r in sib_rows]

    if hops >= 2:
        seen: set[str] = {qn}
        targets: list[str] = []
        for e in nh.outgoing:
            if e.target not in seen:
                targets.append(e.target)
                seen.add(e.target)
        for e in nh.incoming:
            if e.source not in seen:
                targets.append(e.source)
                seen.add(e.source)
        if targets:
            placeholders = ",".join("?" for _ in targets[:80])
            exp_rows = conn.execute(
                f"SELECT * FROM code_nodes WHERE qualified_name IN ({placeholders})"  # nosec B608
                f" LIMIT 80",
                targets[:80],
            ).fetchall()
            nh.expanded = [_row_to_node(r) for r in exp_rows]

    return nh


def neighborhood_to_dict(nh: Neighborhood) -> dict:
    def n(x: Optional[NeighborNode]) -> Optional[dict]:
        if x is None:
            return None
        return {
            "qualified_name": x.qualified_name,
            "kind": x.kind,
            "name": x.name,
            "file_path": x.file_path,
            "line_start": x.line_start,
            "line_end": x.line_end,
            "language": x.language,
            "parent_name": x.parent_name,
        }

    def e(x: NeighborEdge) -> dict:
        return {
            "kind": x.kind,
            "source": x.source,
            "target": x.target,
            "line": x.line,
            "confidence_tier": x.confidence_tier,
        }

    return {
        "node": n(nh.node),
        "outgoing": [e(x) for x in nh.outgoing],
        "incoming": [e(x) for x in nh.incoming],
        "siblings": [n(x) for x in nh.siblings],
        "expanded": [n(x) for x in nh.expanded],
    }


def render_neighborhood_markdown(nh: Neighborhood) -> str:
    if nh.node is None:
        return "**Not found.** No node matches that name or qualified name.\n"

    lines: list[str] = []
    n = nh.node
    lines.append(f"# `{n.name}` — {n.kind}")
    lines.append(
        f"`{n.qualified_name}`  •  **{n.file_path}** L{n.line_start}-{n.line_end}"
        f"  •  _{n.language or 'unknown'}_"
    )
    if n.parent_name:
        lines.append(f"_parent:_ `{n.parent_name}`")
    lines.append("")

    if nh.outgoing:
        lines.append(f"## Outgoing ({len(nh.outgoing)})")
        for e in nh.outgoing:
            lines.append(f"- **{e.kind}** -> `{e.target}`  _L{e.line}_")
        lines.append("")

    if nh.incoming:
        lines.append(f"## Incoming ({len(nh.incoming)})")
        for e in nh.incoming:
            lines.append(f"- `{e.source}` -> **{e.kind}**  _L{e.line}_")
        lines.append("")

    if nh.siblings:
        lines.append(f"## Siblings ({len(nh.siblings)})")
        for s in nh.siblings:
            lines.append(f"- [{s.kind[0]}] `{s.name}` L{s.line_start}")
        lines.append("")

    if nh.expanded:
        lines.append(f"## 2-hop nodes ({len(nh.expanded)})")
        for s in nh.expanded:
            lines.append(f"- [{s.kind[0]}] `{s.qualified_name}`")
        lines.append("")

    return "\n".join(lines) + "\n"
