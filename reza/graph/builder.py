"""Graph builder — full and incremental code graph construction.

Walks the project directory, parses supported files with Tree-sitter,
and stores structural nodes/edges in the graph store. Incremental mode
uses SHA-256 hashes to skip unchanged files.
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .parser import (
    SUPPORTED_EXTENSIONS,
    detect_language,
    file_hash,
    parse_file,
)
from .store import GraphStore

logger = logging.getLogger(__name__)

IGNORE_DIRS = {
    ".git", ".svn", ".hg", ".reza", "__pycache__", "node_modules",
    ".venv", "venv", ".env", "env", ".tox", ".mypy_cache", ".pytest_cache",
    "dist", "build", ".next", ".nuxt", "target", "vendor", ".idea",
    ".vscode", ".cursor", "coverage", ".nyc_output", "egg-info",
}


def _git_tracked_files(project_dir: str) -> Optional[set[str]]:
    """Return set of git-tracked file paths (relative), or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {
                line.strip() for line in result.stdout.splitlines() if line.strip()
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _discover_files(project_dir: str) -> list[str]:
    """Discover all parseable source files in the project."""
    root = Path(project_dir).resolve()
    git_files = _git_tracked_files(project_dir)

    results: list[str] = []

    if git_files is not None:
        for rel_path in git_files:
            full = root / rel_path
            if full.suffix.lower() in SUPPORTED_EXTENSIONS and full.is_file():
                results.append(str(full))
    else:
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
                continue
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                results.append(str(path))

    return sorted(results)


def build_graph(
    project_dir: str,
    db_path: str | Path,
    incremental: bool = False,
) -> dict:
    """Build or update the code knowledge graph.

    Args:
        project_dir: Root directory of the project.
        db_path: Path to the reza context.db.
        incremental: If True, skip files whose hash hasn't changed.

    Returns:
        dict with keys: parsed, skipped, errors, total_nodes, total_edges, elapsed_s
    """
    start = time.monotonic()
    root = Path(project_dir).resolve()

    files = _discover_files(str(root))
    store = GraphStore(db_path)

    parsed = 0
    skipped = 0
    errors = 0

    existing_hashes: dict[str, str] = {}
    if incremental:
        for node in store.get_all_nodes(exclude_files=False):
            if node.kind == "File" and node.file_hash:
                existing_hashes[node.file_path] = node.file_hash

    existing_files_in_graph: set[str] = set()
    if incremental:
        for node in store.get_all_nodes(exclude_files=False):
            if node.kind == "File":
                existing_files_in_graph.add(node.file_path)

    current_files: set[str] = set()

    for abs_path in files:
        try:
            rel_path = str(Path(abs_path).relative_to(root)).replace("\\", "/")
        except ValueError:
            continue

        current_files.add(rel_path)
        fhash = file_hash(abs_path)

        if incremental and rel_path in existing_hashes:
            if existing_hashes[rel_path] == fhash:
                skipped += 1
                continue

        try:
            nodes, edges = parse_file(abs_path)
        except Exception as e:
            logger.warning("Parse error %s: %s", abs_path, e)
            errors += 1
            continue

        for n in nodes:
            n.file_path = rel_path
        for e in edges:
            e.file_path = rel_path

        try:
            store.store_file_nodes_edges(rel_path, nodes, edges, fhash=fhash)
            parsed += 1
        except Exception as e:
            logger.warning("Store error %s: %s", abs_path, e)
            errors += 1

    if incremental:
        removed_files = existing_files_in_graph - current_files
        for rf in removed_files:
            store.remove_file_data(rf)
            store.commit()

    now = datetime.now(timezone.utc).isoformat()
    store.set_metadata("last_build_time", now)
    store.set_metadata("project_dir", str(root))

    if not incremental:
        store.set_metadata("full_build_time", now)

    stats = store.get_stats()
    store.close()

    elapsed = time.monotonic() - start
    return {
        "parsed": parsed,
        "skipped": skipped,
        "errors": errors,
        "total_nodes": stats.total_nodes,
        "total_edges": stats.total_edges,
        "elapsed_s": round(elapsed, 2),
    }


def update_single_file(
    file_path: str,
    project_dir: str,
    db_path: str | Path,
) -> dict:
    """Incrementally update the graph for a single changed file.

    Returns dict with: file, parsed, nodes_count, edges_count
    """
    root = Path(project_dir).resolve()
    abs_path = Path(file_path).resolve()

    try:
        rel_path = str(abs_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return {"file": file_path, "parsed": False, "reason": "outside project"}

    if not abs_path.exists():
        store = GraphStore(db_path)
        store.remove_file_data(rel_path)
        store.commit()
        store.close()
        return {"file": rel_path, "parsed": False, "reason": "deleted"}

    lang = detect_language(str(abs_path))
    if not lang:
        return {"file": rel_path, "parsed": False, "reason": "unsupported language"}

    fhash = file_hash(str(abs_path))

    store = GraphStore(db_path)
    existing = store.get_nodes_by_file(rel_path)
    if existing:
        file_nodes = [n for n in existing if n.kind == "File"]
        if file_nodes and file_nodes[0].file_hash == fhash:
            store.close()
            return {"file": rel_path, "parsed": False, "reason": "unchanged"}

    try:
        nodes, edges = parse_file(str(abs_path))
    except Exception as e:
        store.close()
        return {"file": rel_path, "parsed": False, "reason": f"parse error: {e}"}

    for n in nodes:
        n.file_path = rel_path
    for e in edges:
        e.file_path = rel_path

    store.store_file_nodes_edges(rel_path, nodes, edges, fhash=fhash)
    store.close()

    return {
        "file": rel_path,
        "parsed": True,
        "nodes_count": len(nodes),
        "edges_count": len(edges),
    }
