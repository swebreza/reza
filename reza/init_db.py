"""Project initialization — creates the database, scans files, installs git hooks."""

import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schema import DB_DIR, DB_NAME, get_db_path, init_schema, get_connection

# Directories to skip entirely
IGNORE_DIRS = {
    ".git", ".reza", ".svn", ".hg",
    "node_modules", "__pycache__", ".venv", "venv", "env", ".env",
    "dist", "build", "out", ".next", ".nuxt", ".output",
    "coverage", ".nyc_output", ".coverage",
    ".pytest_cache", ".mypy_cache", ".tox", ".ruff_cache",
    ".idea", ".vscode",
    "migrations",
}

# File extensions to skip
IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".ico", ".webp", ".avif",
    ".mp4", ".mp3", ".wav", ".ogg", ".flac", ".avi", ".mov",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".lock",
}

# Extensions that are likely source code or config
TEXT_EXTENSIONS = {
    ".py", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".mts", ".cts",
    ".vue", ".svelte", ".astro",
    ".html", ".htm", ".xml", ".xsl",
    ".css", ".scss", ".sass", ".less", ".styl",
    ".json", ".json5", ".jsonc",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config",
    ".md", ".mdx", ".txt", ".rst", ".adoc",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".go", ".rs", ".java", ".kt", ".kts", ".swift",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
    ".rb", ".php", ".lua", ".r", ".m", ".sql",
    ".ex", ".exs", ".erl", ".hrl",
    ".clj", ".cljs", ".scala",
    ".env.example", ".env.sample",
    ".graphql", ".gql",
    ".proto",
    ".tf", ".tfvars",
    ".dockerfile",
}

# Filenames without extensions that are always text
TEXT_FILENAMES = {
    "Dockerfile", "Makefile", "Procfile", "Jenkinsfile", "Vagrantfile",
    "Gemfile", "Rakefile", "Guardfile",
    ".gitignore", ".gitattributes", ".dockerignore", ".eslintrc",
    ".prettierrc", ".babelrc", ".editorconfig",
    "LICENSE", "LICENCE", "NOTICE", "AUTHORS", "CONTRIBUTORS",
}


def file_checksum(filepath: str) -> str:
    """MD5 of the first 64 KB of a file (fast, good enough for change detection)."""
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            h.update(f.read(65536))
    except (OSError, PermissionError):
        pass
    return h.hexdigest()


def extract_purpose(filepath: str) -> Optional[str]:
    """Extract a short human-readable description from a source file."""
    path = Path(filepath)
    ext = path.suffix.lower()
    name = path.name

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read(3000)
    except (OSError, PermissionError):
        return None

    if not content.strip():
        return None

    # Python: module docstring
    if ext == ".py":
        m = re.search(r'^"""(.*?)"""', content, re.DOTALL)
        if not m:
            m = re.search(r"^'''(.*?)'''", content, re.DOTALL)
        if m:
            first = m.group(1).strip().split("\n")[0].strip()
            if first:
                return first[:200]

    # Markdown / RST: first heading
    if ext in {".md", ".mdx", ".rst", ".txt"}:
        m = re.search(r"^#{1,3}\s+(.+)", content, re.MULTILINE)
        if m:
            return m.group(1).strip()[:200]

    # JS/TS: JSDoc block comment
    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}:
        m = re.search(r"/\*\*\s*(.*?)\*/", content, re.DOTALL)
        if m:
            lines = [ln.strip().lstrip("*").strip() for ln in m.group(1).split("\n")]
            first = next((ln for ln in lines if ln and not ln.startswith("@")), None)
            if first:
                return first[:200]

    # Generic: first meaningful comment
    comment_patterns = [
        (r"^#\s+(.+)", {".py", ".rb", ".sh", ".bash", ".zsh", ".fish", ".yaml", ".yml", ".toml", ".r"}),
        (r"^//\s+(.+)", {".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".rs", ".php"}),
        (r"^--\s+(.+)", {".sql", ".lua"}),
        (r"<!--\s*(.+?)\s*-->", {".html", ".htm", ".xml", ".svg"}),
    ]
    for pattern, exts in comment_patterns:
        if ext in exts:
            m = re.search(pattern, content, re.MULTILINE)
            if m:
                return m.group(1).strip()[:200]

    # Fallback: filename as hint
    stem = path.stem.replace("_", " ").replace("-", " ")
    if name in {"index.js", "index.ts", "index.py", "main.py", "main.go", "main.rs"}:
        return f"Entry point — {stem}"

    return None


def detect_framework(project_dir: str) -> Dict[str, str]:
    """Detect project language, framework, and key metadata."""
    meta: Dict[str, str] = {}
    base = Path(project_dir)

    # Node.js
    pkg = base / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            meta["name"] = data.get("name", "")
            meta["language"] = "JavaScript/TypeScript"
            if "next" in deps:
                meta["framework"] = "Next.js"
            elif "nuxt" in deps:
                meta["framework"] = "Nuxt"
            elif "react" in deps:
                meta["framework"] = "React"
            elif "vue" in deps:
                meta["framework"] = "Vue"
            elif "svelte" in deps:
                meta["framework"] = "Svelte"
            elif "astro" in deps:
                meta["framework"] = "Astro"
            elif "express" in deps:
                meta["framework"] = "Express"
            elif "fastify" in deps:
                meta["framework"] = "Fastify"
            else:
                meta["framework"] = "Node.js"
        except (json.JSONDecodeError, OSError):
            pass

    # Python
    for req_file in ["requirements.txt", "Pipfile", "setup.cfg", "pyproject.toml"]:
        candidate = base / req_file
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8", errors="ignore").lower()
                meta["language"] = "Python"
                if "django" in content:
                    meta["framework"] = "Django"
                elif "fastapi" in content:
                    meta["framework"] = "FastAPI"
                elif "flask" in content:
                    meta["framework"] = "Flask"
                elif "tornado" in content:
                    meta["framework"] = "Tornado"
                elif "aiohttp" in content:
                    meta["framework"] = "aiohttp"
                else:
                    meta.setdefault("framework", "Python")
            except OSError:
                pass
            break

    # Go
    if (base / "go.mod").exists():
        meta["language"] = "Go"
        meta.setdefault("framework", "Go")

    # Rust
    if (base / "Cargo.toml").exists():
        meta["language"] = "Rust"
        meta.setdefault("framework", "Rust/Cargo")

    # Java / Kotlin
    if (base / "pom.xml").exists():
        meta["language"] = "Java"
        meta.setdefault("framework", "Maven")
    elif (base / "build.gradle").exists() or (base / "build.gradle.kts").exists():
        meta["language"] = "Kotlin/Java"
        meta.setdefault("framework", "Gradle")

    # Ruby
    if (base / "Gemfile").exists():
        meta["language"] = "Ruby"
        content = (base / "Gemfile").read_text(errors="ignore").lower()
        meta["framework"] = "Rails" if "rails" in content else "Ruby"

    # PHP
    if (base / "composer.json").exists():
        meta["language"] = "PHP"
        meta.setdefault("framework", "PHP")

    # Infrastructure flags
    if (base / "Dockerfile").exists():
        meta["has_docker"] = "true"
    if any((base / f).exists() for f in ("docker-compose.yml", "docker-compose.yaml")):
        meta["has_compose"] = "true"
    if any((base / f).exists() for f in ("terraform.tf", "main.tf")):
        meta["has_terraform"] = "true"

    return meta


def count_lines(filepath: str) -> int:
    """Count lines in a text file."""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except (OSError, PermissionError):
        return 0


def is_indexable(path: Path) -> bool:
    """Return True if this file should be indexed."""
    if path.suffix.lower() in IGNORE_EXTENSIONS:
        return False
    if path.name in TEXT_FILENAMES:
        return True
    ext = path.suffix.lower()
    return ext in TEXT_EXTENSIONS


def scan_files(conn, project_dir: str, extra_ignore: Optional[List[str]] = None) -> Tuple[int, int]:
    """Walk the project and insert/update all indexable files. Returns (indexed, skipped)."""
    base = Path(project_dir).resolve()
    ignore_dirs = IGNORE_DIRS.copy()
    if extra_ignore:
        ignore_dirs.update(extra_ignore)

    indexed = 0
    skipped = 0

    for root, dirs, files in os.walk(str(base)):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]

        for filename in files:
            filepath = Path(root) / filename
            if not is_indexable(filepath):
                skipped += 1
                continue

            rel_path = str(filepath.relative_to(base)).replace("\\", "/")
            try:
                stat_info = filepath.stat()
                size = stat_info.st_size
                mtime = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
            except OSError:
                skipped += 1
                continue

            purpose = extract_purpose(str(filepath))
            lines = count_lines(str(filepath))
            checksum = file_checksum(str(filepath))
            file_type = filepath.suffix.lower().lstrip(".") or filepath.name

            conn.execute(
                """
                INSERT INTO files (path, file_type, line_count, size_bytes, purpose, last_modified, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    file_type    = excluded.file_type,
                    line_count   = excluded.line_count,
                    size_bytes   = excluded.size_bytes,
                    purpose      = excluded.purpose,
                    last_modified = excluded.last_modified,
                    checksum     = excluded.checksum,
                    indexed_at   = datetime('now')
                """,
                (rel_path, file_type, lines, size, purpose, mtime, checksum),
            )
            indexed += 1

    return indexed, skipped


def install_git_hooks(project_dir: str) -> bool:
    """Install pre-commit git hook for automatic DB updates. Returns True on success."""
    hooks_dir = Path(project_dir) / ".git" / "hooks"
    if not hooks_dir.exists():
        return False

    hook_path = hooks_dir / "pre-commit"
    hook_script = (
        "#!/bin/sh\n"
        "# reza: update context DB on commit\n"
        "if command -v reza >/dev/null 2>&1; then\n"
        "  reza update --staged --silent\n"
        "fi\n"
    )

    # If hook exists, append rather than overwrite
    if hook_path.exists():
        existing = hook_path.read_text()
        if "reza" in existing:
            return True  # Already installed
        hook_path.write_text(existing.rstrip() + "\n\n" + hook_script)
    else:
        hook_path.write_text(hook_script)

    # Make executable on Unix
    if sys.platform != "win32":
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return True


def initialize_project(
    project_dir: str,
    extra_ignore: Optional[List[str]] = None,
    install_hooks: bool = True,
) -> Dict:
    """Full initialization: create DB, scan files, set metadata, install hooks."""
    project_dir = str(Path(project_dir).resolve())
    db_path = get_db_path(project_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    init_schema(conn)

    # Detect and store project metadata
    meta = detect_framework(project_dir)
    meta["project_dir"] = project_dir
    meta["initialized_at"] = datetime.now().isoformat()
    meta["reza_version"] = "0.1.0"
    meta.setdefault("name", Path(project_dir).name)
    meta.setdefault("language", "Unknown")
    meta.setdefault("framework", "Unknown")

    for key, value in meta.items():
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    conn.commit()

    # Scan files
    indexed, skipped = scan_files(conn, project_dir, extra_ignore)
    conn.commit()
    conn.close()

    # Update .gitignore — suggest ignoring .reza
    gitignore = Path(project_dir) / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".reza/" not in content and ".reza" not in content:
            with open(str(gitignore), "a") as f:
                f.write("\n# reza context database (generated — safe to commit or ignore)\n# .reza/\n")

    hook_installed = False
    if install_hooks:
        hook_installed = install_git_hooks(project_dir)

    return {
        "db_path": str(db_path),
        "indexed": indexed,
        "skipped": skipped,
        "meta": meta,
        "hook_installed": hook_installed,
    }
