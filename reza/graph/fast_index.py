"""Fast, bounded-work indexer for the code graph (no Tree-sitter).

Full-repo Tree-sitter walks every AST node and extracts every call edge — fine for
small repos, but can feel \"infinite\" on large JS/React codebases (huge ASTs, huge
edge counts). Tools like ctags and many IDE maps use **regex / line heuristics** first.

This module indexes **files, top-level-ish classes/functions, and import lines** in
O(bytes) per file with predictable caps. It is the **default** for `reza graph build`.

Use `reza graph build --semantic` when you want the slower Tree-sitter pass (CALL
edges, nested structure).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable, Optional

from .parser import EdgeInfo, NodeInfo, detect_language, _is_test_node

# Keep reads bounded (same order of magnitude as semantic skip threshold).
MAX_FAST_READ_BYTES = 512 * 1024

# ---------------------------------------------------------------------------
# Line matchers: (regex, kind: Class|Function, name_group_index)
# ---------------------------------------------------------------------------

def _py_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(
        r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*(class|def)\s+(\w+)",
        line,
    )
    if m:
        kind = "Class" if m.group(1) == "class" else "Function"
        return kind, m.group(2)
    return None


def _js_family_line(line: str) -> Optional[tuple[str, str]]:
    # export function foo / export async function foo / function foo
    m = re.match(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*[\(:]",
        line,
    )
    if m:
        return "Function", m.group(1)
    m = re.match(
        r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)",
        line,
    )
    if m:
        return "Class", m.group(1)
    # const Foo = ( or function( for components — conservative
    m = re.match(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?[\(\w]",
        line,
    )
    if m:
        return "Function", m.group(1)
    return None


def _go_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(", line)
    if m:
        return "Function", m.group(1)
    return None


def _rust_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(", line)
    if m:
        return "Function", m.group(1)
    m = re.match(r"^\s*(?:pub\s+)?(?:unsafe\s+)?struct\s+(\w+)", line)
    if m:
        return "Class", m.group(1)  # treat struct as class-like
    return None


def _java_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(
        r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?"
        r"(?:class|interface|enum)\s+(\w+)",
        line,
    )
    if m:
        return "Class", m.group(1)
    return None


def _csharp_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(
        r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?"
        r"(?:partial\s+)?(?:class|interface|struct|record)\s+(\w+)",
        line,
    )
    if m:
        return "Class", m.group(1)
    return None


def _ruby_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^\s*class\s+(\w+)", line)
    if m:
        return "Class", m.group(1)
    m = re.match(r"^\s*def\s+(\w+)", line)
    if m:
        return "Function", m.group(1)
    return None


def _php_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)", line)
    if m:
        return "Class", m.group(1)
    m = re.match(r"^\s*function\s+(\w+)\s*\(", line)
    if m:
        return "Function", m.group(1)
    return None


def _cpp_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^\s*(?:class|struct)\s+(\w+)", line)
    if m:
        return "Class", m.group(1)
    return None


def _c_line(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^\s*(?:static\s+)?(?:inline\s+)?\w[\w\s\*]+\s+(\w+)\s*\([^)]*\)\s*\{", line)
    if m and m.group(1) not in {"if", "else", "for", "while", "switch", "return"}:
        return "Function", m.group(1)
    return None


def _pick_scanner(language: str) -> Optional[Callable[[str], Optional[tuple[str, str]]]]:
    if language == "python":
        return _py_line
    if language in ("javascript", "typescript", "tsx"):
        return _js_family_line
    if language == "go":
        return _go_line
    if language == "rust":
        return _rust_line
    if language == "java":
        return _java_line
    if language == "csharp":
        return _csharp_line
    if language == "ruby":
        return _ruby_line
    if language == "php":
        return _php_line
    if language == "cpp":
        return _cpp_line
    if language == "c":
        return _c_line
    return None


def _import_edges(rel_path: str, file_qn: str, lines: list[str], language: str) -> list[EdgeInfo]:
    edges: list[EdgeInfo] = []
    cap = 40
    for i, line in enumerate(lines, start=1):
        if len(edges) >= cap:
            break
        t = line.strip()
        if language == "python":
            if t.startswith("import ") or t.startswith("from "):
                tgt = t[:200]
                edges.append(
                    EdgeInfo(
                        kind="IMPORTS_FROM",
                        source=file_qn,
                        target=tgt,
                        file_path=rel_path,
                        line=i,
                        extra={"confidence_tier": "HEURISTIC", "fast": True},
                    )
                )
        elif language in ("javascript", "typescript", "tsx"):
            if t.startswith("import ") or ("export " in t and " from " in t):
                tgt = t[:200]
                edges.append(
                    EdgeInfo(
                        kind="IMPORTS_FROM",
                        source=file_qn,
                        target=tgt,
                        file_path=rel_path,
                        line=i,
                        extra={"confidence_tier": "HEURISTIC", "fast": True},
                    )
                )
        elif language == "go" and t.startswith("import "):
            edges.append(
                EdgeInfo(
                    kind="IMPORTS_FROM",
                    source=file_qn,
                    target=t[:200],
                    file_path=rel_path,
                    line=i,
                    extra={"confidence_tier": "HEURISTIC", "fast": True},
                )
            )
        elif language == "rust" and t.startswith("use "):
            edges.append(
                EdgeInfo(
                    kind="IMPORTS_FROM",
                    source=file_qn,
                    target=t[:200],
                    file_path=rel_path,
                    line=i,
                    extra={"confidence_tier": "HEURISTIC", "fast": True},
                )
            )
    return edges


def fast_parse_file(abs_path: str, rel_path: str) -> tuple[list[NodeInfo], list[EdgeInfo], str]:
    """Regex/line-based index: bounded CPU per file, no Tree-sitter.

    For ``.py`` files we dispatch to :func:`reza.graph.py_ast_fast.py_ast_parse_file`
    which uses CPython's built-in ``ast`` (much faster and more accurate than regex
    for Python). For every other language we use the cheap regex scanner below.

    Returns (nodes, edges, content_sha256) from the same bytes read (single I/O).
    """
    language = detect_language(abs_path)
    if not language:
        return [], [], ""

    if language == "python":
        from .py_ast_fast import py_ast_parse_file
        return py_ast_parse_file(abs_path, rel_path)

    p = Path(abs_path)
    try:
        size = p.stat().st_size
    except OSError:
        return [], [], ""

    if size > MAX_FAST_READ_BYTES:
        # Caller should have skipped; defensive empty graph except File stub handled in builder
        return [], [], ""

    try:
        raw = p.read_bytes()[:MAX_FAST_READ_BYTES]
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return [], [], ""

    content_hash = hashlib.sha256(raw).hexdigest()

    lines = text.splitlines()
    rel = rel_path.replace("\\", "/")
    file_qn = rel

    nodes: list[NodeInfo] = []
    edges: list[EdgeInfo] = []

    nodes.append(
        NodeInfo(
            kind="File",
            name=p.name,
            file_path=rel,
            line_start=1,
            line_end=len(lines),
            language=language,
        )
    )

    scanner = _pick_scanner(language)
    seen: set[str] = set()

    if scanner:
        for i, line in enumerate(lines, start=1):
            hit = scanner(line)
            if not hit:
                continue
            kind_str, base_name = hit
            is_test = _is_test_node(base_name, abs_path)
            if kind_str == "Function" and is_test:
                node_kind = "Test"
            else:
                node_kind = kind_str

            name = base_name
            qkey = base_name
            if qkey in seen:
                name = f"{base_name}__L{i}"
                qkey = name
            seen.add(qkey)

            qn = f"{file_qn}::{name}"
            nodes.append(
                NodeInfo(
                    kind=node_kind,
                    name=name,
                    file_path=rel,
                    line_start=i,
                    line_end=i,
                    language=language,
                    parent_name=None,
                    is_test=is_test,
                )
            )
            edges.append(
                EdgeInfo(
                    kind="CONTAINS",
                    source=file_qn,
                    target=qn,
                    file_path=rel,
                    line=i,
                )
            )

    edges.extend(_import_edges(rel, file_qn, lines, language))
    return nodes, edges, content_hash
