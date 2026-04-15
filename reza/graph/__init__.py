"""Code knowledge graph — structural code awareness for reza.

Parses source files into AST nodes and edges using Tree-sitter,
stores them in the shared context.db, and provides blast-radius
impact analysis for token-efficient LLM context.

Requires optional dependencies: pip install reza[graph]
"""

from .store import GraphStore
from .parser import NodeInfo, EdgeInfo, parse_file, SUPPORTED_EXTENSIONS

__all__ = [
    "GraphStore",
    "NodeInfo",
    "EdgeInfo",
    "parse_file",
    "SUPPORTED_EXTENSIONS",
]
