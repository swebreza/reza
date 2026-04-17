"""Ultra-fast Python indexer using the stdlib ``ast`` module.

No Tree-sitter, no regex heuristics — parses a Python file with ``ast.parse`` and
walks the tree to emit File / Class / Function / Test nodes and CONTAINS /
INHERITS / IMPORTS_FROM / CALLS edges.

Typical speed: **0.5–3 ms per file** on commodity hardware. Good enough to index
10k-file Python projects in seconds.

Used only for ``.py`` files. JS/TS/JSX/TSX fall back to the regex fast index.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .parser import NodeInfo, EdgeInfo, _TEST_FUNCTION_PATTERNS, _TEST_PATTERNS


def _is_test(name: str, file_path: str) -> bool:
    if _TEST_FUNCTION_PATTERNS.match(name):
        return True
    if _TEST_PATTERNS.search(Path(file_path).stem):
        return True
    return False


def _qn(file_qn: str, name: str, parent: str | None) -> str:
    if parent:
        return f"{file_qn}::{parent}::{name}"
    return f"{file_qn}::{name}"


def py_ast_parse_file(
    abs_path: str, rel_path: str
) -> tuple[list[NodeInfo], list[EdgeInfo], str]:
    """Parse a Python file with ``ast``; return (nodes, edges, sha256)."""
    try:
        source_bytes = Path(abs_path).read_bytes()
    except OSError:
        return [], [], ""

    content_hash = hashlib.sha256(source_bytes).hexdigest()

    try:
        text = source_bytes.decode("utf-8", errors="replace")
        tree = ast.parse(text, filename=abs_path)
    except (SyntaxError, ValueError):
        # Still return a File node so graph reflects the file exists.
        file_qn = rel_path
        return (
            [
                NodeInfo(
                    kind="File",
                    name=Path(abs_path).name,
                    file_path=rel_path,
                    line_start=1,
                    line_end=max(1, source_bytes.count(b"\n") + 1),
                    language="python",
                )
            ],
            [],
            content_hash,
        )

    rel = rel_path.replace("\\", "/")
    file_qn = rel

    nodes: list[NodeInfo] = [
        NodeInfo(
            kind="File",
            name=Path(abs_path).name,
            file_path=rel,
            line_start=1,
            line_end=getattr(tree, "end_lineno", 1) or 1,
            language="python",
        )
    ]
    edges: list[EdgeInfo] = []

    def _import_target(node: ast.AST) -> list[str]:
        out: list[str] = []
        if isinstance(node, ast.Import):
            for n in node.names:
                out.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                out.append(mod)
        return out

    def _class_bases(node: ast.ClassDef) -> list[str]:
        bases: list[str] = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b) if hasattr(ast, "unparse") else b.id)  # type: ignore[attr-defined]
            except Exception:
                pass
        return bases

    def _format_params(args: ast.arguments) -> str:
        try:
            return "(" + ", ".join(a.arg for a in args.args) + ")"
        except Exception:
            return "()"

    def _walk(node: ast.AST, parent_class: str | None, enclosing_fn: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for tgt in _import_target(child):
                    edges.append(
                        EdgeInfo(
                            kind="IMPORTS_FROM",
                            source=file_qn,
                            target=tgt,
                            file_path=rel,
                            line=getattr(child, "lineno", 0) or 0,
                        )
                    )

            elif isinstance(child, ast.ClassDef):
                name = child.name
                qn = _qn(file_qn, name, None)
                is_test = _is_test(name, abs_path)
                nodes.append(
                    NodeInfo(
                        kind="Class",
                        name=name,
                        file_path=rel,
                        line_start=child.lineno,
                        line_end=getattr(child, "end_lineno", child.lineno) or child.lineno,
                        language="python",
                        parent_name=parent_class,
                        is_test=is_test,
                    )
                )
                edges.append(
                    EdgeInfo(
                        kind="CONTAINS",
                        source=file_qn,
                        target=qn,
                        file_path=rel,
                        line=child.lineno,
                    )
                )
                for base in _class_bases(child):
                    edges.append(
                        EdgeInfo(
                            kind="INHERITS",
                            source=qn,
                            target=base,
                            file_path=rel,
                            line=child.lineno,
                        )
                    )
                _walk(child, parent_class=name, enclosing_fn=enclosing_fn)

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                is_test = _is_test(name, abs_path)
                node_kind = "Test" if is_test else "Function"
                qn = _qn(file_qn, name, parent_class)
                nodes.append(
                    NodeInfo(
                        kind=node_kind,
                        name=name,
                        file_path=rel,
                        line_start=child.lineno,
                        line_end=getattr(child, "end_lineno", child.lineno) or child.lineno,
                        language="python",
                        parent_name=parent_class,
                        params=_format_params(child.args),
                        is_test=is_test,
                    )
                )
                container = _qn(file_qn, parent_class, None) if parent_class else file_qn
                edges.append(
                    EdgeInfo(
                        kind="CONTAINS",
                        source=container,
                        target=qn,
                        file_path=rel,
                        line=child.lineno,
                    )
                )
                if is_test:
                    edges.append(
                        EdgeInfo(
                            kind="TESTED_BY",
                            source=qn,
                            target=container,
                            file_path=rel,
                            line=child.lineno,
                        )
                    )
                _walk(child, parent_class=parent_class, enclosing_fn=name)

            elif isinstance(child, ast.Call) and enclosing_fn:
                func = child.func
                call_name = None
                if isinstance(func, ast.Name):
                    call_name = func.id
                elif isinstance(func, ast.Attribute):
                    try:
                        call_name = func.attr
                    except Exception:
                        call_name = None
                if call_name:
                    caller = _qn(file_qn, enclosing_fn, parent_class)
                    edges.append(
                        EdgeInfo(
                            kind="CALLS",
                            source=caller,
                            target=call_name,
                            file_path=rel,
                            line=getattr(child, "lineno", 0) or 0,
                            extra={"confidence_tier": "INFERRED"},
                        )
                    )
                _walk(child, parent_class=parent_class, enclosing_fn=enclosing_fn)

            else:
                _walk(child, parent_class=parent_class, enclosing_fn=enclosing_fn)

    _walk(tree, parent_class=None, enclosing_fn=None)
    return nodes, edges, content_hash
