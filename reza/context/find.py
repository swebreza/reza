"""Unified hybrid search — graph nodes + chat turns + file paths in one call.

Ranking: BM25 relevance (from FTS5) × recency decay. Results are labeled by
source so the LLM (or UI) knows whether a hit is from the code graph, a past
conversation, or a file name match.
"""

from __future__ import annotations

import math
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


Source = Literal["graph", "chat", "file"]


@dataclass
class FindHit:
    source: Source
    score: float
    title: str
    subtitle: str
    snippet: str
    # Source-specific pointers
    qualified_name: Optional[str] = None  # graph
    file_path: Optional[str] = None       # graph / file
    session_id: Optional[str] = None      # chat
    turn_id: Optional[int] = None         # chat
    timestamp: Optional[str] = None       # chat / file
    kind: Optional[str] = None            # graph node kind
    line_start: Optional[int] = None      # graph
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FTS_SAFE_WORD = re.compile(r"[A-Za-z0-9_]+")


def _to_fts_query(text: str) -> Optional[str]:
    """Convert a user query into a safe FTS5 MATCH expression.

    Strips punctuation, keeps word tokens, joins with AND. Returns None if no
    usable tokens (caller should fall back to LIKE).
    """
    words = _FTS_SAFE_WORD.findall(text)
    if not words:
        return None
    return " AND ".join(f'"{w}"' for w in words)


def _recency_weight(
    when_iso: Optional[str], *, half_life_hours: float = 168.0
) -> float:
    """Exponential decay. 1.0 = now, 0.5 = one half-life ago, etc."""
    if not when_iso:
        return 0.3  # unknown → mild boost only
    try:
        t = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
        age_h = max(0.0, (time.time() - t.timestamp()) / 3600.0)
    except (ValueError, OSError):
        return 0.3
    return 0.5 ** (age_h / half_life_hours)


def _combine(bm25: float, recency: float) -> float:
    """Lower BM25 means more relevant (SQLite FTS5 convention).

    We invert so higher = better, then multiply by recency boost.
    Clamp BM25 component to avoid domination by giant negatives.
    """
    rel = 1.0 / (1.0 + max(0.0, bm25))
    # Recency contributes up to +0.5 boost; relevance is primary.
    return rel * (1.0 + 0.5 * recency)


# ---------------------------------------------------------------------------
# Per-source search
# ---------------------------------------------------------------------------


def _search_graph(
    conn: sqlite3.Connection, query: str, limit: int
) -> list[FindHit]:
    fts = _to_fts_query(query)
    hits: list[FindHit] = []
    if fts:
        try:
            rows = conn.execute(
                """SELECT n.*, bm25(code_nodes_fts) AS bm25
                   FROM code_nodes_fts f
                   JOIN code_nodes n ON n.id = f.node_id
                   WHERE code_nodes_fts MATCH ?
                   ORDER BY bm25 ASC
                   LIMIT ?""",
                (fts, limit * 2),
            ).fetchall()
            for r in rows:
                recency = _recency_weight(
                    _iso_from_epoch(r["updated_at"]) if r["updated_at"] else None
                )
                hits.append(
                    FindHit(
                        source="graph",
                        score=_combine(r["bm25"] or 0.0, recency),
                        title=r["name"],
                        subtitle=f"{r['kind']} · {r['file_path']}",
                        snippet=f"L{r['line_start']}-{r['line_end']}"
                        + (f" · parent={r['parent_name']}" if r["parent_name"] else ""),
                        qualified_name=r["qualified_name"],
                        file_path=r["file_path"],
                        kind=r["kind"],
                        line_start=r["line_start"],
                    )
                )
            return hits[:limit]
        except sqlite3.OperationalError:
            pass  # fall through to LIKE

    # LIKE fallback
    like = f"%{query.lower()}%"
    rows = conn.execute(
        """SELECT * FROM code_nodes
           WHERE LOWER(name) LIKE ? OR LOWER(qualified_name) LIKE ?
           LIMIT ?""",
        (like, like, limit),
    ).fetchall()
    for r in rows:
        hits.append(
            FindHit(
                source="graph",
                score=0.3,
                title=r["name"],
                subtitle=f"{r['kind']} · {r['file_path']}",
                snippet=f"L{r['line_start']}-{r['line_end']}",
                qualified_name=r["qualified_name"],
                file_path=r["file_path"],
                kind=r["kind"],
                line_start=r["line_start"],
            )
        )
    return hits


def _search_chat(
    conn: sqlite3.Connection, query: str, limit: int
) -> list[FindHit]:
    fts = _to_fts_query(query)
    if not fts:
        return []
    try:
        rows = conn.execute(
            """SELECT ct.id as turn_id, ct.session_id, ct.role, ct.content,
                      ct.recorded_at,
                      bm25(conversation_turns_fts) AS bm25
               FROM conversation_turns_fts f
               JOIN conversation_turns ct ON ct.id = f.turn_id
               WHERE conversation_turns_fts MATCH ?
               ORDER BY bm25 ASC
               LIMIT ?""",
            (fts, limit * 2),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    hits: list[FindHit] = []
    for r in rows:
        when = r["recorded_at"]
        recency = _recency_weight(when)
        content = r["content"] or ""
        snippet = content.strip().replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:220] + "…"
        hits.append(
            FindHit(
                source="chat",
                score=_combine(r["bm25"] or 0.0, recency),
                title=f"{r['role']}: {snippet[:80]}",
                subtitle=f"session {r['session_id']} · {when or ''}",
                snippet=snippet,
                session_id=r["session_id"],
                turn_id=r["turn_id"],
                timestamp=when,
            )
        )
    return hits[:limit]


def _search_files(
    conn: sqlite3.Connection, query: str, limit: int
) -> list[FindHit]:
    try:
        like = f"%{query.lower()}%"
        rows = conn.execute(
            """SELECT path, file_type, line_count, size_bytes, last_modified
               FROM files
               WHERE LOWER(path) LIKE ?
               ORDER BY last_modified DESC
               LIMIT ?""",
            (like, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    hits: list[FindHit] = []
    for r in rows:
        recency = _recency_weight(r["last_modified"])
        q = query.lower()
        name = r["path"].rsplit("/", 1)[-1]
        base_rel = 0.9 if q in name.lower() else 0.4
        hits.append(
            FindHit(
                source="file",
                score=base_rel * (1.0 + 0.5 * recency),
                title=name,
                subtitle=f"{r['file_type'] or 'file'} · {r['path']}",
                snippet=(
                    f"{r['line_count'] or 0:,} lines · "
                    f"{r['size_bytes'] or 0:,} bytes"
                ),
                file_path=r["path"],
                timestamp=r["last_modified"],
            )
        )
    return hits


def _iso_from_epoch(val: float) -> Optional[str]:
    try:
        return (
            datetime.fromtimestamp(val, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
    except (OSError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def unified_find(
    conn: sqlite3.Connection,
    query: str,
    *,
    sources: tuple[Source, ...] = ("graph", "chat", "file"),
    limit: int = 20,
    per_source_limit: Optional[int] = None,
) -> list[FindHit]:
    """Run hybrid BM25+recency search across selected sources and merge.

    Returns a ranked, deduplicated list of :class:`FindHit`. Each hit is
    labelled with ``source`` so callers can group/style them.
    """
    per = per_source_limit or max(5, math.ceil(limit * 1.5 / len(sources)))

    all_hits: list[FindHit] = []
    if "graph" in sources:
        all_hits.extend(_search_graph(conn, query, per))
    if "chat" in sources:
        all_hits.extend(_search_chat(conn, query, per))
    if "file" in sources:
        all_hits.extend(_search_files(conn, query, per))

    # Dedupe: same file_path+qualified_name/turn_id is the same hit
    seen: set[tuple] = set()
    dedup: list[FindHit] = []
    for h in sorted(all_hits, key=lambda x: x.score, reverse=True):
        key = (h.source, h.qualified_name or h.turn_id or h.file_path)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(h)
        if len(dedup) >= limit:
            break
    return dedup


def hits_to_dict(hits: list[FindHit]) -> list[dict]:
    out: list[dict] = []
    for h in hits:
        out.append(
            {
                "source": h.source,
                "score": round(h.score, 4),
                "title": h.title,
                "subtitle": h.subtitle,
                "snippet": h.snippet,
                "qualified_name": h.qualified_name,
                "file_path": h.file_path,
                "session_id": h.session_id,
                "turn_id": h.turn_id,
                "timestamp": h.timestamp,
                "kind": h.kind,
                "line_start": h.line_start,
            }
        )
    return out


def render_hits_markdown(hits: list[FindHit], *, query: str = "") -> str:
    if not hits:
        return f"_No results for `{query}`._\n"
    lines: list[str] = []
    if query:
        lines.append(f"# Results for `{query}` ({len(hits)})\n")
    for h in hits:
        badge = {
            "graph": "G",
            "chat": "C",
            "file": "F",
        }[h.source]
        lines.append(f"## [{badge}] {h.title}  _(score {h.score:.2f})_")
        lines.append(f"{h.subtitle}")
        if h.snippet:
            lines.append(f"> {h.snippet}")
        if h.qualified_name:
            lines.append(f"`qn:` `{h.qualified_name}`")
        lines.append("")
    return "\n".join(lines) + "\n"
