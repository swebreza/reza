# Changelog

All notable changes to reza are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.3.0] — 2026-04-12

### Added

- `reza session turns add` — append conversation turns to a session (single turn or bulk from JSON file)
- `reza session turns list` — list all turns for a session
- `reza session search <query>` — full-text search across all conversation history using FTS5 + BM25 ranking; supports `--id` (session filter), `--limit`, `--json`
- `reza ingest <file>` — ingest `.md` or `.json` transcript files as conversation turns; auto-creates session from filename prefix; prevents double-import
- `reza session handoff` extended — new `--id`, `--format markdown|json`, `--budget`, `--search` flags; renders structured markdown brief ready to paste into any AI tool
- `reza watch` — auto-ingests files dropped into `.reza/handoffs/` in real time
- FTS5 `conversation_turns_fts` virtual table with Porter + Unicode61 stemming for accurate multilingual search
- DELETE and UPDATE sync triggers keep FTS index consistent with base table
- `reza upgrade` backfills FTS index for existing turn data

### Changed

- `reza session handoff --json` is now deprecated in favour of `--format json`

---

## [0.2.0] — 2026-04-11

### Added

- `conversation_turns` table — structured per-turn conversation history linked to sessions (role, content, token_est, turn_index)
- `handoff_drops` table — tracks ingested file drops to prevent double-import
- `reza/turns.py` — new module: `add_turn`, `add_turns_bulk`, `list_turns`, `turns_within_budget` (budget-aware retrieval drops oldest turns first)
- `reza/ingest.py` — new module: parse and ingest `.md` and `.json` transcript files as conversation turns; `reza ingest` file-drop workflow
- `.reza/handoffs/` directory auto-created on `reza init` and `reza upgrade`
- `reza upgrade` now runs schema migration so existing installations get new tables without re-init
- `UNIQUE(session_id, turn_index)` constraint ensures turn ordering integrity

### Changed

- `reza upgrade` applies `init_schema` before re-scanning (idempotent migration)

---

## [0.1.0] — 2024-04-10

### Added

- `reza init` — initialize context database, scan project files, install git hooks
- `reza status` — quick project overview
- `reza watch` — real-time file watcher using `watchdog`
- `reza query` — search context database (overview, find, recent, sessions, file info)
- `reza session` — session management (start, save, end, list, handoff)
- `reza export` — export context to markdown, JSON, or compact LLM prompt format
- `reza hooks` — install / uninstall pre-commit git hook
- `reza upgrade` — re-scan all files
- 6-table SQLite schema: `project_meta`, `files`, `dependencies`, `sessions`, `changes`, `conflicts`
- Purpose extraction from Python docstrings, JSDoc, Markdown headings, and first comments
- Framework detection: Django, FastAPI, Flask, React, Vue, Next.js, Nuxt, Svelte, Astro, Express, Go, Rust, Maven, Gradle, Rails
- Cross-LLM handoff via `reza session handoff`
- Integrations for: Claude Code, Cursor, Kilocode, Aider, Continue.dev, GitHub Copilot, Codeium/Windsurf, OpenAI Codex
- JSON output mode for all query commands (`--json`)
- Full test suite with pytest

---

## Future

- [ ] VS Code extension with sidebar context view
- [ ] Web UI for browsing `.reza/context.db`
- [ ] AST-based purpose extraction (more accurate than regex)
- [ ] `reza diff` — show what changed between sessions
- [ ] Team sync via shared DB (opt-in)
- [ ] `reza annotate` — let LLMs write notes directly to file records
