"""Graph builder — full and incremental code graph construction.

Full builds use **parallel workers** (thread pool) so CPU-bound parsing overlaps I/O.
Hashes come from the same bytes as parsing (``parse_file`` / ``fast_parse_file`` return
SHA-256) — no double-read on full builds.

Incremental builds use a **cheap hash-first** skip (one read when unchanged); changed
files are re-parsed (second read) — unavoidable without mtime/size in DB.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Optional

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
    "__generated__", ".cache", "storybook-static",
}

MAX_GRAPH_FILE_BYTES = 512 * 1024  # 512 KiB

_MINIFIED_SUFFIXES = (
    ".min.js",
    ".min.mjs",
    ".min.cjs",
    ".min.css",
)


def _worker_count() -> int:
    raw = os.environ.get("REZA_GRAPH_WORKERS", "").strip()
    if raw == "0":
        return 1
    if raw.isdigit():
        return max(1, int(raw))
    cpu = os.cpu_count() or 4
    return max(4, min(16, cpu * 2))


def _per_file_timeout() -> float:
    """Max seconds any single file parse may take. Fast=3s, semantic=15s.

    Override with ``REZA_GRAPH_FILE_TIMEOUT_S=<float>``.
    """
    raw = os.environ.get("REZA_GRAPH_FILE_TIMEOUT_S", "").strip()
    try:
        return max(0.5, float(raw)) if raw else 0.0
    except ValueError:
        return 0.0


def _overall_budget_seconds() -> float:
    """Overall wall-clock budget for a full build, 0 = unlimited.

    ``REZA_GRAPH_MAX_SECONDS=<float>``. When exceeded we stop submitting new
    work and commit whatever finished — partial graph is still useful.
    """
    raw = os.environ.get("REZA_GRAPH_MAX_SECONDS", "").strip()
    try:
        return max(0.0, float(raw)) if raw else 0.0
    except ValueError:
        return 0.0


def should_skip_graph_file(path: Path) -> bool:
    """Return True if file should not be parsed (too large or known minified bundle)."""
    name = path.name.lower()
    for suf in _MINIFIED_SUFFIXES:
        if name.endswith(suf):
            return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    return size > MAX_GRAPH_FILE_BYTES


def _git_tracked_files(project_dir: str) -> Optional[set[str]]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,  # lowered: if git hangs, fall back fast to os.walk
        )
        if result.returncode == 0:
            return {
                line.strip() for line in result.stdout.splitlines() if line.strip()
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _discover_files(project_dir: str) -> list[str]:
    """Enumerate source files, pruning IGNORE_DIRS *during* the walk.

    Previously used ``Path.rglob('*')`` which descends into ``node_modules``,
    ``.venv`` etc. and then filters — on a React monorepo that's 200k+ file
    stats before we ever parse anything (looks like a hang). Now we use
    ``os.walk`` with in-place ``dirnames[:] = …`` pruning so the ignored trees
    are **never traversed**. Matches what ``tree`` does, finishes in seconds.
    """
    root = Path(project_dir).resolve()
    git_files = _git_tracked_files(project_dir)

    results: list[str] = []

    if git_files is not None:
        for rel_path in git_files:
            parts = rel_path.replace("\\", "/").split("/")
            if any(part in IGNORE_DIRS for part in parts):
                continue
            full = root / rel_path
            if full.suffix.lower() in SUPPORTED_EXTENSIONS and full.is_file():
                results.append(str(full))
        return sorted(results)

    # No git (or git failed) — fall back to os.walk with dir pruning.
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in place — os.walk honors this for subsequent recursion.
        # Skip dotted dirs (.git, .venv, .cursor, …) and anything in IGNORE_DIRS.
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                results.append(os.path.join(dirpath, fn))

    return sorted(results)


def list_graph_source_files(project_dir: str) -> list[str]:
    return _discover_files(project_dir)


ProgressCallback = Optional[Callable[[int, int, str], None]]


def _parse_job(
    abs_path: str,
    rel_path: str,
    index_mode: str,
) -> tuple[str, str, Optional[list], Optional[list], Optional[str], Optional[str]]:
    """Run in worker thread. Returns (status, rel_path, nodes, edges, fhash, err)."""
    p = Path(abs_path)
    if should_skip_graph_file(p):
        return ("giant", rel_path, None, None, None, None)
    try:
        if index_mode == "fast":
            from .fast_index import fast_parse_file

            nodes, edges, fhash = fast_parse_file(abs_path, rel_path)
        else:
            nodes, edges, fhash = parse_file(abs_path)
        for n in nodes:
            n.file_path = rel_path
        for e in edges:
            e.file_path = rel_path
        return ("ok", rel_path, nodes, edges, fhash, None)
    except Exception as e:
        logger.warning("Parse error %s: %s", abs_path, e)
        return ("err", rel_path, None, None, None, str(e))


def build_graph(
    project_dir: str,
    db_path: str | Path,
    incremental: bool = False,
    *,
    index_mode: Literal["fast", "semantic"] = "fast",
    progress_callback: ProgressCallback = None,
    files: Optional[list[str]] = None,
) -> dict:
    start = time.monotonic()
    root = Path(project_dir).resolve()

    if files is None:
        files = _discover_files(str(root))
    store = GraphStore(db_path)

    if incremental:
        stored = store.get_metadata("graph_index_mode")
        if stored in ("fast", "semantic"):
            index_mode = stored  # type: ignore[assignment]

    parsed = 0
    skipped = 0
    skipped_giant = 0
    errors = 0
    timed_out = 0
    budget_hit = False

    default_timeout = 3.0 if index_mode == "fast" else 15.0
    per_file_timeout = _per_file_timeout() or default_timeout
    overall_budget = _overall_budget_seconds()

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
    total = len(files)
    workers = _worker_count()

    # Parallel full build: parse overlaps across threads; SQLite writes stay serial.
    if not incremental and total > 0 and workers > 1:
        jobs = [(a, str(Path(a).relative_to(root)).replace("\\", "/")) for a in files]
        for _, rel_path in jobs:
            current_files.add(rel_path)

        # Batch DB writes — 1 txn per BATCH_SIZE files instead of 1 per file.
        # This is the single biggest speedup on Windows (fsync per commit).
        batch: list[tuple[str, list, list, str]] = []
        giant_pending: list[str] = []

        def _flush_batch() -> tuple[int, int]:
            nonlocal batch, giant_pending
            ok = 0
            err = 0
            if batch:
                try:
                    store.bulk_store_files(batch)
                    ok = len(batch)
                except Exception as e:
                    logger.warning("Bulk store failed, falling back: %s", e)
                    for fp, nds, eds, fh in batch:
                        try:
                            store.store_file_nodes_edges(fp, nds, eds, fhash=fh)
                            ok += 1
                        except Exception as ee:
                            logger.warning("Store error %s: %s", fp, ee)
                            err += 1
                batch = []
            for fp in giant_pending:
                try:
                    store.remove_file_data(fp)
                except Exception as e:
                    logger.warning("Remove stale graph data %s: %s", fp, e)
            giant_pending = []
            return ok, err

        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(_parse_job, abs_path, rel_path, index_mode): rel_path
                for abs_path, rel_path in jobs
            }
            for fut in as_completed(futures):
                rel_path = futures[fut]
                done += 1

                if overall_budget and (time.monotonic() - start) > overall_budget:
                    budget_hit = True
                    for other in futures:
                        if not other.done():
                            other.cancel()
                    break

                try:
                    status, rp, nodes, edges, fhash, err = fut.result()
                except Exception as e:
                    errors += 1
                    logger.warning("Worker failed %s: %s", rel_path, e)
                    if progress_callback:
                        progress_callback(done, total, rel_path)
                    continue

                if status == "giant":
                    skipped_giant += 1
                    giant_pending.append(rp)
                elif status == "err":
                    errors += 1
                elif status == "ok":
                    assert nodes is not None and edges is not None and fhash is not None
                    batch.append((rp, nodes, edges, fhash))

                if len(batch) >= 50 or len(giant_pending) >= 50:
                    ok_n, err_n = _flush_batch()
                    parsed += ok_n
                    errors += err_n

                if progress_callback:
                    progress_callback(done, total, rp if status != "err" else rel_path)

            ok_n, err_n = _flush_batch()
            parsed += ok_n
            errors += err_n

    else:
        # Sequential: incremental updates, or REZA_GRAPH_WORKERS=0 / single file
        for idx, abs_path in enumerate(files, 1):
            try:
                rel_path = str(Path(abs_path).relative_to(root)).replace("\\", "/")
            except ValueError:
                continue

            current_files.add(rel_path)
            p = Path(abs_path)
            if should_skip_graph_file(p):
                skipped_giant += 1
                try:
                    store.remove_file_data(rel_path)
                except Exception as e:
                    logger.warning("Remove stale graph data %s: %s", rel_path, e)
                if progress_callback:
                    progress_callback(idx, total, rel_path)
                continue

            if incremental and rel_path in existing_hashes:
                fh = file_hash(abs_path)
                if existing_hashes[rel_path] == fh:
                    skipped += 1
                    if progress_callback:
                        progress_callback(idx, total, rel_path)
                    continue

            try:
                if index_mode == "fast":
                    from .fast_index import fast_parse_file

                    nodes, edges, fh = fast_parse_file(abs_path, rel_path)
                else:
                    nodes, edges, fh = parse_file(abs_path)
            except Exception as e:
                logger.warning("Parse error %s: %s", abs_path, e)
                errors += 1
                if progress_callback:
                    progress_callback(idx, total, rel_path)
                continue

            for n in nodes:
                n.file_path = rel_path
            for e in edges:
                e.file_path = rel_path

            try:
                store.store_file_nodes_edges(rel_path, nodes, edges, fhash=fh)
                parsed += 1
            except Exception as e:
                logger.warning("Store error %s: %s", abs_path, e)
                errors += 1

            if progress_callback:
                progress_callback(idx, total, rel_path)

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

    store.set_metadata("graph_index_mode", index_mode)

    stats = store.get_stats()
    store.close()

    elapsed = time.monotonic() - start
    return {
        "parsed": parsed,
        "skipped": skipped,
        "skipped_giant": skipped_giant,
        "timed_out": timed_out,
        "budget_hit": budget_hit,
        "errors": errors,
        "total_nodes": stats.total_nodes,
        "total_edges": stats.total_edges,
        "elapsed_s": round(elapsed, 2),
        "index_mode": index_mode,
        "workers": workers if not incremental else 1,
        "per_file_timeout_s": per_file_timeout,
        "overall_budget_s": overall_budget,
    }


def update_single_file(
    file_path: str,
    project_dir: str,
    db_path: str | Path,
) -> dict:
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

    if should_skip_graph_file(abs_path):
        store = GraphStore(db_path)
        store.remove_file_data(rel_path)
        store.commit()
        store.close()
        return {
            "file": rel_path,
            "parsed": False,
            "reason": "skipped (large or minified bundle)",
        }

    lang = detect_language(str(abs_path))
    if not lang:
        return {"file": rel_path, "parsed": False, "reason": "unsupported language"}

    store = GraphStore(db_path)
    index_mode = store.get_metadata("graph_index_mode") or "fast"

    existing = store.get_nodes_by_file(rel_path)
    if existing:
        file_nodes = [n for n in existing if n.kind == "File"]
        if file_nodes and file_nodes[0].file_hash:
            fh0 = file_hash(str(abs_path))
            if file_nodes[0].file_hash == fh0:
                store.close()
                return {"file": rel_path, "parsed": False, "reason": "unchanged"}

    try:
        if index_mode == "fast":
            from .fast_index import fast_parse_file

            nodes, edges, fh = fast_parse_file(str(abs_path), rel_path)
        else:
            nodes, edges, fh = parse_file(str(abs_path))
    except Exception as e:
        store.close()
        return {"file": rel_path, "parsed": False, "reason": f"parse error: {e}"}

    for n in nodes:
        n.file_path = rel_path
    for e in edges:
        e.file_path = rel_path

    store.store_file_nodes_edges(rel_path, nodes, edges, fhash=fh)
    store.close()

    return {
        "file": rel_path,
        "parsed": True,
        "nodes_count": len(nodes),
        "edges_count": len(edges),
    }
