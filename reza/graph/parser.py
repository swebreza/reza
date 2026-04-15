"""Tree-sitter based multi-language code parser.

Extracts structural nodes (classes, functions, imports, types) and edges
(calls, inheritance, contains) from source files. Adapted from the
code-review-graph project's parser architecture.

Requires: pip install reza[graph]
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class NodeInfo:
    kind: str  # File, Class, Function, Type, Test
    name: str
    file_path: str
    line_start: int
    line_end: int
    language: str = ""
    parent_name: Optional[str] = None
    params: Optional[str] = None
    return_type: Optional[str] = None
    modifiers: Optional[str] = None
    is_test: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class EdgeInfo:
    kind: str  # CALLS, IMPORTS_FROM, INHERITS, CONTAINS, TESTED_BY, REFERENCES
    source: str
    target: str
    file_path: str
    line: int = 0
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Language extension mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
}

SUPPORTED_EXTENSIONS = set(EXTENSION_TO_LANGUAGE.keys())

# Node type mappings per language (tree-sitter node types)
_CLASS_TYPES: dict[str, set[str]] = {
    "python": {"class_definition"},
    "javascript": {"class_declaration", "class"},
    "typescript": {"class_declaration", "class"},
    "tsx": {"class_declaration", "class"},
    "go": {"type_declaration"},
    "rust": {"struct_item", "enum_item", "impl_item", "trait_item"},
    "java": {"class_declaration", "interface_declaration", "enum_declaration"},
    "ruby": {"class", "module"},
    "c": {"struct_specifier"},
    "cpp": {"class_specifier", "struct_specifier"},
    "csharp": {"class_declaration", "interface_declaration"},
    "kotlin": {"class_declaration", "object_declaration"},
    "swift": {"class_declaration", "struct_declaration", "protocol_declaration"},
    "php": {"class_declaration", "interface_declaration"},
}

_FUNCTION_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "arrow_function", "method_definition"},
    "typescript": {"function_declaration", "arrow_function", "method_definition"},
    "tsx": {"function_declaration", "arrow_function", "method_definition"},
    "go": {"function_declaration", "method_declaration"},
    "rust": {"function_item"},
    "java": {"method_declaration", "constructor_declaration"},
    "ruby": {"method", "singleton_method"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
    "csharp": {"method_declaration", "constructor_declaration"},
    "kotlin": {"function_declaration"},
    "swift": {"function_declaration"},
    "php": {"function_definition", "method_declaration"},
}

_IMPORT_TYPES: dict[str, set[str]] = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
    "go": {"import_declaration"},
    "rust": {"use_declaration"},
    "java": {"import_declaration"},
    "ruby": {"call"},  # require/require_relative
    "c": {"preproc_include"},
    "cpp": {"preproc_include"},
    "csharp": {"using_directive"},
    "kotlin": {"import_header"},
    "swift": {"import_declaration"},
    "php": {"namespace_use_declaration"},
}

_CALL_TYPES: dict[str, set[str]] = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "tsx": {"call_expression"},
    "go": {"call_expression"},
    "rust": {"call_expression"},
    "java": {"method_invocation"},
    "ruby": {"call", "method_call"},
    "c": {"call_expression"},
    "cpp": {"call_expression"},
    "csharp": {"invocation_expression"},
    "kotlin": {"call_expression"},
    "swift": {"call_expression"},
    "php": {"function_call_expression", "member_call_expression"},
}

_TEST_PATTERNS = re.compile(
    r"(^test_|_test$|Test$|Spec$|_spec$|\.test\.|\.spec\.)", re.IGNORECASE
)

_TEST_FUNCTION_PATTERNS = re.compile(
    r"^(test_|test[A-Z])", re.IGNORECASE
)


def detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def file_hash(file_path: str) -> str:
    """SHA-256 hash of file contents for change detection."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _get_parser(language: str):
    """Get a tree-sitter parser for the given language."""
    try:
        import tree_sitter_language_pack as tslp
    except ImportError:
        raise ImportError(
            "tree-sitter-language-pack is required for graph features. "
            "Install with: pip install reza[graph]"
        )
    return tslp.get_parser(language)


def _get_node_name(node, source_bytes: bytes) -> str:
    """Extract the name identifier from a tree-sitter node."""
    for child in node.children:
        if child.type in ("identifier", "name", "type_identifier", "property_identifier"):
            return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return ""


def _get_node_text(node, source_bytes: bytes) -> str:
    """Get the full text of a node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_params(node, source_bytes: bytes) -> Optional[str]:
    """Extract parameter list from a function node."""
    for child in node.children:
        if child.type in ("parameters", "formal_parameters", "parameter_list"):
            return _get_node_text(child, source_bytes)
    return None


def _extract_return_type(node, source_bytes: bytes) -> Optional[str]:
    """Extract return type annotation if present."""
    for child in node.children:
        if child.type in ("type", "return_type", "type_annotation"):
            return _get_node_text(child, source_bytes)
    return None


def _is_test_node(name: str, file_path: str) -> bool:
    """Determine if a node is a test based on naming conventions."""
    if _TEST_FUNCTION_PATTERNS.match(name):
        return True
    if _TEST_PATTERNS.search(Path(file_path).stem):
        return True
    return False


def _extract_call_name(node, source_bytes: bytes) -> Optional[str]:
    """Extract the function/method name from a call expression."""
    for child in node.children:
        if child.type == "identifier":
            return _get_node_text(child, source_bytes)
        if child.type in ("member_expression", "attribute"):
            return _get_node_text(child, source_bytes)
        if child.type in ("field_expression", "scoped_identifier"):
            return _get_node_text(child, source_bytes)
    func = node.child_by_field_name("function")
    if func:
        return _get_node_text(func, source_bytes)
    return None


def _extract_import_target(node, source_bytes: bytes, language: str) -> Optional[str]:
    """Extract the import target module/path."""
    text = _get_node_text(node, source_bytes).strip()
    if language == "python":
        if node.type == "import_from_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    return _get_node_text(child, source_bytes)
        elif node.type == "import_statement":
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    name_node = child
                    if child.type == "aliased_import":
                        for sub in child.children:
                            if sub.type == "dotted_name":
                                name_node = sub
                                break
                    return _get_node_text(name_node, source_bytes)
    elif language in ("javascript", "typescript", "tsx"):
        for child in node.children:
            if child.type == "string":
                raw = _get_node_text(child, source_bytes)
                return raw.strip("'\"")
    elif language == "go":
        for child in node.children:
            if child.type == "import_spec_list":
                specs = []
                for spec in child.children:
                    if spec.type == "import_spec":
                        for sub in spec.children:
                            if sub.type == "interpreted_string_literal":
                                specs.append(
                                    _get_node_text(sub, source_bytes).strip('"')
                                )
                return ", ".join(specs) if specs else None
            if child.type == "import_spec":
                for sub in child.children:
                    if sub.type == "interpreted_string_literal":
                        return _get_node_text(sub, source_bytes).strip('"')
    elif language == "rust":
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier", "use_list"):
                return _get_node_text(child, source_bytes)
    return text


def _extract_inheritance(node, source_bytes: bytes, language: str) -> list[str]:
    """Extract base classes / interfaces from a class node."""
    bases = []
    if language == "python":
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type in ("identifier", "attribute"):
                        bases.append(_get_node_text(arg, source_bytes))
    elif language in ("javascript", "typescript", "tsx", "java", "csharp", "kotlin"):
        for child in node.children:
            if child.type in ("class_heritage", "superclass", "superinterfaces",
                              "extends_clause", "implements_clause"):
                for sub in child.children:
                    if sub.type in ("identifier", "type_identifier", "generic_type"):
                        bases.append(_get_node_text(sub, source_bytes))
    elif language == "go":
        for child in node.children:
            if child.type == "type_spec":
                for sub in child.children:
                    if sub.type == "struct_type":
                        for field_node in sub.children:
                            if field_node.type == "field_declaration_list":
                                for f in field_node.children:
                                    if f.type == "field_declaration":
                                        if len(f.children) == 1:
                                            bases.append(
                                                _get_node_text(f.children[0], source_bytes)
                                            )
    elif language == "rust":
        for child in node.children:
            if child.type in ("trait_bounds", "type_identifier"):
                bases.append(_get_node_text(child, source_bytes))
    return bases


def parse_file(file_path: str) -> tuple[list[NodeInfo], list[EdgeInfo]]:
    """Parse a source file and extract structural nodes and edges.

    Returns (nodes, edges) where nodes are code entities (files, classes,
    functions, etc.) and edges are relationships (calls, imports, etc.).
    """
    language = detect_language(file_path)
    if not language:
        return [], []

    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
    except OSError:
        logger.warning("Cannot read file: %s", file_path)
        return [], []

    try:
        parser = _get_parser(language)
    except Exception as e:
        logger.warning("No parser for %s: %s", language, e)
        return [], []

    tree = parser.parse(source_bytes)
    root = tree.root_node

    rel_path = file_path.replace("\\", "/")
    nodes: list[NodeInfo] = []
    edges: list[EdgeInfo] = []
    file_qn = rel_path

    nodes.append(NodeInfo(
        kind="File",
        name=Path(file_path).name,
        file_path=rel_path,
        line_start=1,
        line_end=root.end_point[0] + 1,
        language=language,
    ))

    class_types = _CLASS_TYPES.get(language, set())
    func_types = _FUNCTION_TYPES.get(language, set())
    import_types = _IMPORT_TYPES.get(language, set())
    call_types = _CALL_TYPES.get(language, set())

    enclosing_class: Optional[str] = None

    def _make_qualified(name: str, parent: Optional[str] = None) -> str:
        if parent:
            return f"{file_qn}::{parent}::{name}"
        return f"{file_qn}::{name}"

    def _walk(node, parent_class: Optional[str] = None):
        nonlocal enclosing_class

        if node.type in class_types:
            name = _get_node_name(node, source_bytes)
            if not name:
                name = f"<anon_class_L{node.start_point[0] + 1}>"
            qn = _make_qualified(name)
            is_test = _is_test_node(name, file_path)

            nodes.append(NodeInfo(
                kind="Class",
                name=name,
                file_path=rel_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                language=language,
                parent_name=parent_class,
                is_test=is_test,
            ))

            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=file_qn,
                target=qn,
                file_path=rel_path,
                line=node.start_point[0] + 1,
            ))

            bases = _extract_inheritance(node, source_bytes, language)
            for base in bases:
                edges.append(EdgeInfo(
                    kind="INHERITS",
                    source=qn,
                    target=base,
                    file_path=rel_path,
                    line=node.start_point[0] + 1,
                ))

            old_class = enclosing_class
            enclosing_class = name
            for child in node.children:
                _walk(child, parent_class=name)
            enclosing_class = old_class
            return

        if node.type in func_types:
            name = _get_node_name(node, source_bytes)
            if not name:
                name = f"<anon_fn_L{node.start_point[0] + 1}>"
            qn = _make_qualified(name, parent_class)
            is_test = _is_test_node(name, file_path)
            params = _extract_params(node, source_bytes)
            ret_type = _extract_return_type(node, source_bytes)

            node_kind = "Test" if is_test else "Function"
            nodes.append(NodeInfo(
                kind=node_kind,
                name=name,
                file_path=rel_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                language=language,
                parent_name=parent_class,
                params=params,
                return_type=ret_type,
                is_test=is_test,
            ))

            container = _make_qualified(parent_class) if parent_class else file_qn
            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=container,
                target=qn,
                file_path=rel_path,
                line=node.start_point[0] + 1,
            ))

            if is_test:
                edges.append(EdgeInfo(
                    kind="TESTED_BY",
                    source=qn,
                    target=container,
                    file_path=rel_path,
                    line=node.start_point[0] + 1,
                ))

            for child in node.children:
                _walk(child, parent_class)
            return

        if node.type in import_types:
            target = _extract_import_target(node, source_bytes, language)
            if target:
                edges.append(EdgeInfo(
                    kind="IMPORTS_FROM",
                    source=file_qn,
                    target=target,
                    file_path=rel_path,
                    line=node.start_point[0] + 1,
                ))

        if node.type in call_types:
            call_name = _extract_call_name(node, source_bytes)
            if call_name:
                caller = _make_qualified(
                    _find_enclosing_func(node, source_bytes, func_types) or "<module>",
                    parent_class,
                )
                edges.append(EdgeInfo(
                    kind="CALLS",
                    source=caller,
                    target=call_name,
                    file_path=rel_path,
                    line=node.start_point[0] + 1,
                    extra={"confidence_tier": "INFERRED"},
                ))

        for child in node.children:
            _walk(child, parent_class)

    _walk(root)
    return nodes, edges


def _find_enclosing_func(
    node, source_bytes: bytes, func_types: set[str]
) -> Optional[str]:
    """Walk up the tree to find the enclosing function name."""
    current = node.parent
    while current:
        if current.type in func_types:
            return _get_node_name(current, source_bytes) or None
        current = current.parent
    return None
