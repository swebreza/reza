"""Subtree walk — everything contained under a given file or class.

Given a file path or qualified name, return a hierarchical tree of all
CONTAINS-reachable descendants. Useful when the LLM says "show me everything
in ``auth/session.py``" or "show me the methods of ``UserService``".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubtreeNode:
    qualified_name: str
    kind: str
    name: str
    line_start: int
    line_end: int
    children: list["SubtreeNode"] = field(default_factory=list)


@dataclass
class Subtree:
    root: Optional[SubtreeNode]
    file_path: str = ""
    language: str = ""
    total_nodes: int = 0


def _node_from_row(row: sqlite3.Row) -> SubtreeNode:
    return SubtreeNode(
        qualified_name=row["qualified_name"],
        kind=row["kind"],
        name=row["name"],
        line_start=row["line_start"] or 0,
        line_end=row["line_end"] or 0,
    )


def get_subtree(
    conn: sqlite3.Connection,
    path_or_qn: str,
    *,
    max_nodes: int = 500,
) -> Subtree:
    """Walk CONTAINS edges from the given root, build hierarchical tree."""
    path = path_or_qn.replace("\\", "/")

    root_row = conn.execute(
        "SELECT * FROM code_nodes WHERE qualified_name = ? LIMIT 1",
        (path_or_qn,),
    ).fetchone()
    if not root_row:
        root_row = conn.execute(
            "SELECT * FROM code_nodes WHERE file_path = ? AND kind = 'File' LIMIT 1",
            (path,),
        ).fetchone()

    if not root_row:
        return Subtree(root=None)

    root_qn = root_row["qualified_name"]
    file_path = root_row["file_path"]
    language = root_row["language"] or ""

    # NOTE: CONTAINS edges from File nodes use the bare file_path as
    # ``source_qualified`` (not ``path::filename``). So when we start from a
    # File node we also seed the bare path as an alternate identity.
    collected: dict[str, SubtreeNode] = {root_qn: _node_from_row(root_row)}
    frontier: list[str] = [root_qn]
    file_aliases: dict[str, str] = {}
    if root_row["kind"] == "File" and file_path and file_path != root_qn:
        file_aliases[file_path] = root_qn
        frontier.append(file_path)
    depth_guard = 0
    while frontier and len(collected) < max_nodes and depth_guard < 8:
        depth_guard += 1
        placeholders = ",".join("?" for _ in frontier)
        edge_rows = conn.execute(
            f"""SELECT e.source_qualified, e.target_qualified, n.*
                FROM code_edges e
                JOIN code_nodes n ON n.qualified_name = e.target_qualified
                WHERE e.kind = 'CONTAINS'
                  AND e.source_qualified IN ({placeholders})""",  # nosec B608
            frontier,
        ).fetchall()
        next_frontier: list[str] = []
        for r in edge_rows:
            tgt = r["target_qualified"]
            if tgt in collected or len(collected) >= max_nodes:
                continue
            child = _node_from_row(r)
            collected[tgt] = child
            src_qn = r["source_qualified"]
            parent = collected.get(src_qn) or collected.get(
                file_aliases.get(src_qn, "")
            )
            if parent:
                parent.children.append(child)
            next_frontier.append(tgt)
        frontier = next_frontier

    # Sort children by line_start
    for node in collected.values():
        node.children.sort(key=lambda x: (x.line_start, x.name))

    return Subtree(
        root=collected[root_qn],
        file_path=file_path,
        language=language,
        total_nodes=len(collected),
    )


def subtree_to_dict(st: Subtree) -> dict:
    def _walk(n: Optional[SubtreeNode]) -> Optional[dict]:
        if n is None:
            return None
        return {
            "qualified_name": n.qualified_name,
            "kind": n.kind,
            "name": n.name,
            "line_start": n.line_start,
            "line_end": n.line_end,
            "children": [_walk(c) for c in n.children],
        }

    return {
        "file_path": st.file_path,
        "language": st.language,
        "total_nodes": st.total_nodes,
        "root": _walk(st.root),
    }


def render_subtree_markdown(st: Subtree) -> str:
    if st.root is None:
        return "**Not found.**\n"

    lines: list[str] = []
    lines.append(f"# Subtree of `{st.root.qualified_name}`")
    lines.append(
        f"**{st.file_path}**  •  _{st.language or 'unknown'}_  "
        f"•  {st.total_nodes:,} node(s)\n"
    )

    def _walk(n: SubtreeNode, depth: int) -> None:
        marker = "F" if n.kind == "File" else n.kind[0]
        indent = "  " * depth
        lines.append(
            f"{indent}- [{marker}] `{n.name}` _L{n.line_start}-{n.line_end}_"
        )
        for c in n.children:
            _walk(c, depth + 1)

    _walk(st.root, 0)
    return "\n".join(lines) + "\n"
