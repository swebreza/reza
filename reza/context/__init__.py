"""LLM-facing context APIs.

Compact, token-budgeted views over the combined code graph + conversation
history + file index. Designed so an LLM (or anything that can run a CLI / tool
call) can:

1. Get the **whole project structure** cheaply (``overview``).
2. Zoom into a **specific node and its neighborhood** (``neighbors``).
3. Walk a **subtree** of a file/class (``subtree``).
4. Do a **hybrid ranked search** across graph + chat + files (``find``).
5. Produce a **paste-ready handoff pack** for the next LLM (``context_pack``).
"""

from .overview import build_overview
from .neighbors import get_neighbors
from .subtree import get_subtree
from .find import unified_find
from .pack import build_context_pack

__all__ = [
    "build_overview",
    "get_neighbors",
    "get_subtree",
    "unified_find",
    "build_context_pack",
]
