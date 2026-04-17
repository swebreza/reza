"""Whole-project map — the LLM's first call on a new session.

Returns a compact structure showing every indexed file grouped by directory,
with top-level classes / functions per file. Token-budgeted: when the project
is larger than the budget allows, we progressively collapse detail
(symbols → file list → directory list).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OverviewNode:
    kind: str  # "Class" | "Function" | "Test"
    name: str
    line_start: int
    line_end: int


@dataclass
class OverviewFile:
    path: str
    language: str
    line_count: int
    size_bytes: int
    symbols: list[OverviewNode] = field(default_factory=list)


@dataclass
class OverviewDir:
    path: str
    files: list[OverviewFile] = field(default_factory=list)
    subdirs: list["OverviewDir"] = field(default_factory=list)


@dataclass
class Overview:
    root: OverviewDir
    total_files: int
    total_symbols: int
    languages: list[str]
    truncated: bool = False
    truncation_note: str = ""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_files_and_symbols(
    conn: sqlite3.Connection, path_prefix: Optional[str] = None
) -> tuple[dict[str, OverviewFile], list[str]]:
    """Load every File node + its top-level symbols from code_nodes.

    ``path_prefix`` filters by file_path (forward-slashed).
    """
    prefix_filter = ""
    params: list[str] = []
    if path_prefix:
        prefix_filter = "AND file_path LIKE ?"
        params.append(path_prefix.rstrip("/") + "/%")

    # First pass: File nodes
    rows = conn.execute(
        f"""SELECT file_path, language, line_end
            FROM code_nodes
            WHERE kind = 'File' {prefix_filter}
            ORDER BY file_path""",  # nosec B608 (prefix_filter built above)
        params,
    ).fetchall()

    files: dict[str, OverviewFile] = {}
    languages: set[str] = set()
    for r in rows:
        fp = r["file_path"]
        files[fp] = OverviewFile(
            path=fp,
            language=r["language"] or "",
            line_count=r["line_end"] or 0,
            size_bytes=0,
        )
        if r["language"]:
            languages.add(r["language"])

    # Second pass: top-level symbols (parent_name IS NULL)
    sym_rows = conn.execute(
        f"""SELECT kind, name, file_path, line_start, line_end, parent_name
            FROM code_nodes
            WHERE kind IN ('Class', 'Function', 'Test')
              AND parent_name IS NULL
              {prefix_filter}
            ORDER BY file_path, line_start""",  # nosec B608
        params,
    ).fetchall()

    for r in sym_rows:
        fp = r["file_path"]
        if fp not in files:
            continue
        files[fp].symbols.append(
            OverviewNode(
                kind=r["kind"],
                name=r["name"],
                line_start=r["line_start"] or 0,
                line_end=r["line_end"] or 0,
            )
        )

    # Merge size_bytes / line_count from `files` table if present (more accurate)
    try:
        for r in conn.execute(
            "SELECT path, line_count, size_bytes FROM files"
        ).fetchall():
            p = r["path"].replace("\\", "/")
            if p in files:
                if r["line_count"]:
                    files[p].line_count = r["line_count"]
                if r["size_bytes"]:
                    files[p].size_bytes = r["size_bytes"]
    except sqlite3.OperationalError:
        pass

    return files, sorted(languages)


def _group_into_tree(files: dict[str, OverviewFile]) -> OverviewDir:
    """Build a directory tree from a flat file map."""
    root = OverviewDir(path="")
    by_dir: dict[str, OverviewDir] = {"": root}

    for path, of in sorted(files.items()):
        parts = path.split("/")
        dir_parts = parts[:-1]
        for i in range(len(dir_parts)):
            dpath = "/".join(dir_parts[: i + 1])
            if dpath not in by_dir:
                node = OverviewDir(path=dpath)
                by_dir[dpath] = node
                parent_path = "/".join(dir_parts[:i])
                by_dir[parent_path].subdirs.append(node)
        parent_path = "/".join(dir_parts)
        by_dir[parent_path].files.append(of)

    return root


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_overview(
    conn: sqlite3.Connection,
    *,
    path_prefix: Optional[str] = None,
    max_symbols_per_file: int = 8,
) -> Overview:
    """Build a structured project overview.

    Apply token budgeting externally via :func:`render_overview_markdown` /
    :func:`overview_to_dict` which both respect ``max_tokens``.
    """
    files, languages = _load_files_and_symbols(conn, path_prefix=path_prefix)

    total_symbols = 0
    for of in files.values():
        if len(of.symbols) > max_symbols_per_file:
            of.symbols = of.symbols[:max_symbols_per_file]
        total_symbols += len(of.symbols)

    root = _group_into_tree(files)
    return Overview(
        root=root,
        total_files=len(files),
        total_symbols=total_symbols,
        languages=languages,
    )


# ---------------------------------------------------------------------------
# Rendering — markdown (human + LLM) and JSON (tool calls)
# ---------------------------------------------------------------------------


def overview_to_dict(ov: Overview) -> dict:
    def _dir_dict(d: OverviewDir) -> dict:
        return {
            "path": d.path,
            "files": [
                {
                    "path": f.path,
                    "language": f.language,
                    "lines": f.line_count,
                    "size_bytes": f.size_bytes,
                    "symbols": [
                        {
                            "kind": s.kind,
                            "name": s.name,
                            "line_start": s.line_start,
                            "line_end": s.line_end,
                        }
                        for s in f.symbols
                    ],
                }
                for f in d.files
            ],
            "subdirs": [_dir_dict(s) for s in d.subdirs],
        }

    return {
        "total_files": ov.total_files,
        "total_symbols": ov.total_symbols,
        "languages": ov.languages,
        "truncated": ov.truncated,
        "truncation_note": ov.truncation_note,
        "root": _dir_dict(ov.root),
    }


def render_overview_markdown(ov: Overview, *, max_tokens: int = 3000) -> str:
    """Render markdown tree, pruning detail progressively to fit ``max_tokens``.

    Prune order: (1) per-file symbols, (2) individual files in dense dirs,
    (3) collapse dirs to a single "N files" line.
    """
    for detail in ("full", "no-symbols", "dirs-only"):
        rendered = _render(ov, detail=detail)
        approx = len(rendered) // 4
        if approx <= max_tokens:
            if detail != "full":
                ov.truncated = True
                ov.truncation_note = f"reduced to '{detail}' to fit {max_tokens}-token budget"
            return rendered

    # Still too big — hard cut
    rendered = _render(ov, detail="dirs-only")
    cut = rendered[: max_tokens * 4].rstrip()
    ov.truncated = True
    ov.truncation_note = f"hard-truncated to {max_tokens}-token budget"
    return cut + "\n\n…(truncated)\n"


def _render(ov: Overview, *, detail: str) -> str:
    lines: list[str] = []
    lines.append("# Project overview\n")
    lines.append(
        f"- **Files indexed:** {ov.total_files:,}  "
        f"• **Symbols:** {ov.total_symbols:,}  "
        f"• **Languages:** {', '.join(ov.languages) or '(none)'}\n"
    )

    def _walk(d: OverviewDir, depth: int) -> None:
        if d.path:
            lines.append(f"{'  ' * (depth - 1)}- **{d.path}/**")
        for sub in sorted(d.subdirs, key=lambda x: x.path):
            _walk(sub, depth + 1)
        for f in d.files:
            indent = "  " * depth
            line_info = f"({f.line_count:,} lines)" if f.line_count else ""
            if detail == "dirs-only":
                continue
            lines.append(f"{indent}- `{_basename(f.path)}` {line_info}")
            if detail == "full" and f.symbols:
                for s in f.symbols:
                    marker = "T" if s.kind == "Test" else s.kind[0]
                    lines.append(
                        f"{indent}  - [{marker}] `{s.name}` "
                        f"L{s.line_start}-{s.line_end}"
                    )
        if detail == "dirs-only" and d.files:
            indent = "  " * depth
            lines.append(f"{indent}- _({len(d.files)} files)_")

    _walk(ov.root, depth=0)
    return "\n".join(lines) + "\n"


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]
