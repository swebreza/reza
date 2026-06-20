"""Privacy and redaction helpers for stored conversation memory."""

from __future__ import annotations

import re


_ASSIGNMENT_SECRET_RE = re.compile(
    r"\b(api[_-]?key|token|secret|password|access[_-]?token)\s*=\s*([^\s,;]+)",
    re.IGNORECASE,
)
_STANDALONE_SECRET_RES = [
    re.compile(r"\bsk-(?:live|test)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
]

BUILT_IN_RULES = {
    "assignment_secrets": r"\b(api[_-]?key|token|secret|password|access[_-]?token)\s*=",
    "openai_keys": "sk-live/sk-test",
    "github_tokens": "ghp_/github_pat_",
    "slack_tokens": "xox*",
}


def redact_text(text: str) -> str:
    """Return text with common credentials replaced before storage/search."""
    if not text:
        return text

    def _assignment_repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}=[REDACTED]"

    redacted = _ASSIGNMENT_SECRET_RE.sub(_assignment_repl, text)
    for pattern in _STANDALONE_SECRET_RES:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def audit_privacy() -> dict:
    """Return the active built-in privacy posture."""
    return {
        "redaction_enabled": True,
        "built_in_rules": list(BUILT_IN_RULES),
        "cloud_sync": False,
        "network_interception": False,
    }
