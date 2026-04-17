"""Tiny shared helpers for token-budgeted output."""

from __future__ import annotations


def est_tokens(text: str) -> int:
    """Cheap token estimator: ~4 characters per token (GPT-ish)."""
    return max(1, len(text) // 4)


def trim_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate ``text`` to ``max_tokens`` (approx). Returns (text, truncated)."""
    if max_tokens <= 0:
        return text, False
    limit_chars = max_tokens * 4
    if len(text) <= limit_chars:
        return text, False
    return text[:limit_chars].rstrip() + "\n\n…(truncated)\n", True
