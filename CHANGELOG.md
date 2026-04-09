# Changelog

All notable changes to reza are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
