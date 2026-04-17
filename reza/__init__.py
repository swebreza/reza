"""
reza — Universal LLM Context Database

Instant project awareness for Claude, Cursor, Codex, Aider, Kilocode,
and any AI coding tool. Index your project once, never re-explain it again.

Usage:
    reza init        # Index your project
    reza watch       # Start real-time file sync
    reza query       # Query project context
    reza session     # Manage LLM sessions
    reza status      # Quick project overview
    reza export      # Export context to markdown/JSON
"""

__version__ = "0.5.0"
__author__ = "Suweb Reza"
__license__ = "MIT"

from .schema import get_connection, find_db_path, get_db_path

__all__ = ["get_connection", "find_db_path", "get_db_path", "__version__"]
