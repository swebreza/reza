# Universal Memory Platform Master Plan

> **For agentic workers:** This is a master plan, not a green-light to start coding every phase at once. Before implementing any phase, write a dedicated design spec and a dedicated implementation plan for that phase. Use `brainstorming` before design work, `writing-plans` before code work, and `plugin-creator` before scaffolding the Codex plugin surface.

**Goal:** Turn `reza` into a durable, searchable, cross-LLM memory system that automatically captures conversations from Claude Code, Codex, Cursor, Aider, Kilocode, and future tools, then lets any user or LLM resume work through fast search and thread-aware handoff.

**Architecture:** Keep the system local-first and SQLite-backed. Split the product into four clear planes: capture adapters, normalized storage, retrieval APIs, and editor/plugin integrations. The immediate priority is not new surface area; it is making sure turns are always captured, schema migrations self-heal, search stays fast, and cross-tool continuity is explicit instead of accidental.

**Tech Stack:** Python CLI, SQLite/FTS5, watchdog-based watcher, JSON/markdown transcript ingestion, npm shim, future VS Code extension (TypeScript), future Codex plugin scaffold.

---

## Current Truth

`reza` already has useful foundations:

- Raw turn storage in `conversation_turns`
- Full-text search via `conversation_turns_fts`
- Session handoff for a single session
- Claude Code auto-sync via `reza sync-claude`
- File-drop ingestion via `.reza/handoffs/`
- File locks and conflict detection

The gaps are the reason the product still feels unreliable:

- Universal auto-sync is not implemented; Claude is special-cased
- Cross-tool threads do not exist yet
- GUI tools still depend on manual export/drop flows
- Retrieval is still mostly session-level, not thread-level
- Docs currently promise more than the CLI actually ships
- The current `current_session` file is too blunt for real multi-tool continuity

The master plan must close those gaps in that order. The product should become trustworthy before it becomes broader.

## Product Requirements

The system being built from here forward must satisfy these rules:

- Every captured conversation must be durable, append-only, and easy to re-index.
- Search must be first-class. Users and LLMs should retrieve relevant context without replaying an entire chat.
- Session continuity must survive tool switches, context limits, restarts, and old databases.
- Local-first is the default. The database remains usable offline and without any cloud dependency.
- Tool-specific integrations are adapters, not core logic. The core model must stay tool-agnostic.
- VS Code and Codex integration should sit on top of the same storage and retrieval primitives instead of inventing a parallel data model.

## Recommended System Shape

### 1. Capture Plane

Create an adapter layer under `reza/adapters/` so every supported tool follows the same contract:

- discover conversation source files or export locations
- parse turns into a normalized `{role, content, timestamp, source}` shape
- resolve or create the correct `reza` session
- sync incrementally and idempotently

Planned adapter files:

- `reza/adapters/__init__.py`
- `reza/adapters/base.py`
- `reza/adapters/claude.py`
- `reza/adapters/codex_cli.py`
- `reza/adapters/aider.py`
- `reza/adapters/cursor.py`
- `reza/adapters/kilocode.py`
- `reza/adapters/codex_desktop.py`

Recommendation:

- Treat Claude Code, Codex CLI, and Aider as first-wave adapters because they have realistic file-based capture paths.
- Treat Cursor, Kilocode, and Codex Desktop as drop-zone adapters first, then upgrade them to direct adapters only after their storage paths are proven stable.

### 2. Storage Plane

The database must model both raw conversation data and continuity metadata.

Keep and harden:

- `sessions`
- `conversation_turns`
- `conversation_turns_fts`
- `handoff_drops`

Add next:

- `threads`
- `sessions.thread_id`
- `conversation_sources`
- `sync_checkpoints`

Recommended responsibilities:

- `threads`: one logical task across tools
- `conversation_sources`: external tool/session identity, source file, adapter name
- `sync_checkpoints`: last ingested position, last hash, last sync time for idempotent adapters

Primary files to modify in this track:

- `reza/schema.py`
- `reza/session.py`
- `reza/turns.py`
- `reza/ingest.py`
- `reza/claude_sync.py`
- `tests/test_session.py`
- `tests/test_turns.py`
- `tests/test_ingest.py`
- `tests/test_claude_sync.py`

### 3. Retrieval Plane

Search and handoff should be designed for LLM use, not just human inspection.

The retrieval layer should answer four questions fast:

1. What thread was I working on?
2. What did we say about topic X?
3. Which files were involved?
4. What is the shortest high-signal packet to resume work?

Planned retrieval features:

- thread-aware handoff instead of only session-aware handoff
- search filters by thread, session, tool, file, date
- snippet-based search output with score and source metadata
- compact machine-readable handoff packets for editor integrations
- search-first continuation flows such as `reza session handoff --search "jwt middleware"`

Primary files in this track:

- `reza/turns.py`
- `reza/session.py`
- `reza/threads.py`
- `reza/export.py`
- `reza/query.py`
- `reza/cli.py`
- `tests/test_turns.py`
- `tests/test_session.py`
- `tests/test_threads.py`
- `tests/test_query.py`

### 4. Integration Plane

All user-facing integrations should reuse the same storage and retrieval flows.

Codex plugin surface:

- `plugins/reza-memory/.codex-plugin/plugin.json`
- `plugins/reza-memory/skills/reza-memory/SKILL.md`
- `plugins/reza-memory/scripts/`
- `.agents/plugins/marketplace.json`

VS Code extension surface:

- `extensions/reza-vscode/package.json`
- `extensions/reza-vscode/src/extension.ts`
- `extensions/reza-vscode/src/commands/*.ts`
- `extensions/reza-vscode/src/search/*.ts`
- `extensions/reza-vscode/src/handoff/*.ts`
- `extensions/reza-vscode/README.md`

Recommendation:

- The extension should call the `reza` CLI or a thin local API wrapper first.
- Do not let the extension own SQLite schema logic directly in v1.
- The Codex plugin should be a workflow and integration wrapper, not a second implementation of storage logic.

## Delivery Phases

### Phase 0: Reality Lock

**Objective:** Align the shipped product with reality before adding new promises.

**Problems solved:**

- users cannot tell which features are real versus planned
- failures in persistence feel worse when the docs over-promise

**Files:**

- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `integrations/README.md`
- Modify: `integrations/claude-code/SKILL.md`
- Modify: `integrations/codex/README.md`

**Deliverables:**

- clearly mark shipped versus planned capabilities
- stop advertising `install-hooks`, `sync-all`, and thread commands until they exist
- document the current drop-zone fallback honestly

**Exit criteria:**

- a new user can read the docs and predict the real behavior of the current release

### Phase 1: Persistence Hardening

**Objective:** Make stored memory durable and self-healing.

**Problems solved:**

- old databases missing newer tables
- turns not consistently attributed to the right session
- ingestion and re-sync edge cases

**Files:**

- Modify: `reza/schema.py`
- Modify: `reza/session.py`
- Modify: `reza/turns.py`
- Modify: `reza/ingest.py`
- Modify: `reza/claude_sync.py`
- Modify: `reza/cli.py`
- Modify: `reza/watcher.py`
- Modify: `tests/test_claude_sync.py`
- Modify: `tests/test_ingest.py`
- Modify: `tests/test_session.py`
- Modify: `tests/test_turns.py`

**Deliverables:**

- reliable auto-migration for legacy DBs
- durable sync bookkeeping for every source
- explicit source identity instead of relying only on `current_session`
- idempotent re-sync across restarts

**Exit criteria:**

- re-running a sync never duplicates turns
- restarting the watcher never loses position
- a stale or legacy DB auto-heals without manual repair

### Phase 2: Universal Adapter Framework

**Objective:** Remove Claude-specific architecture from the core product.

**Files:**

- Create: `reza/adapters/__init__.py`
- Create: `reza/adapters/base.py`
- Create: `reza/adapters/claude.py`
- Create: `reza/adapters/codex_cli.py`
- Create: `reza/adapters/aider.py`
- Create: `reza/adapters/cursor.py`
- Create: `reza/adapters/kilocode.py`
- Create: `reza/adapters/codex_desktop.py`
- Modify: `reza/watcher.py`
- Modify: `reza/cli.py`
- Create: `tests/test_adapters.py`

**Deliverables:**

- adapter registry
- one-time configuration file such as `.reza/adapters.json`
- `reza sync-all`
- `reza install-hooks`
- shared incremental sync path used by every adapter

**Exit criteria:**

- Claude Code, Codex CLI, and Aider work without manual `ingest`
- GUI tools degrade cleanly to drop-zone ingestion
- the watcher becomes the always-on memory process for supported tools

### Phase 3: Cross-Tool Threads

**Objective:** Model one logical task across multiple tools and sessions.

**Files:**

- Modify: `reza/schema.py`
- Create: `reza/threads.py`
- Modify: `reza/session.py`
- Modify: `reza/cli.py`
- Modify: `reza/export.py`
- Create: `tests/test_threads.py`

**Deliverables:**

- `threads` table and `thread_id` linkage
- auto-link and explicit-link flows
- thread-aware handoff
- `reza thread list`
- `reza thread show`
- `reza thread link`
- `reza thread title`

**Exit criteria:**

- a task can move Cursor -> Claude -> Codex without becoming three disconnected histories
- handoff returns the thread, not just the latest interrupted session

### Phase 4: Search-First Retrieval

**Objective:** Make chat history easy to search for both humans and LLMs.

**Files:**

- Modify: `reza/turns.py`
- Modify: `reza/query.py`
- Modify: `reza/session.py`
- Modify: `reza/export.py`
- Modify: `reza/cli.py`
- Modify: `tests/test_turns.py`
- Modify: `tests/test_query.py`
- Modify: `README.md`

**Deliverables:**

- stronger search ranking and snippet output
- search filters by thread, tool, and file
- machine-readable continuation packet for extension/plugin clients
- `handoff --search` built on the same retrieval path as `session search`

**Exit criteria:**

- an LLM can search for a topic and get a compact, relevant answer packet without scraping the full chat
- a user can find the exact prior discussion that led to a code decision

### Phase 5: Codex Plugin Packaging

**Objective:** Create a first-class Codex integration surface without moving core logic out of `reza`.

**Files:**

- Create: `plugins/reza-memory/.codex-plugin/plugin.json`
- Create: `plugins/reza-memory/skills/reza-memory/SKILL.md`
- Create: `plugins/reza-memory/scripts/`
- Create or modify: `.agents/plugins/marketplace.json`
- Modify: `README.md`

**Deliverables:**

- repo-local plugin scaffold created with `plugin-creator`
- plugin manifest and marketplace entry
- reusable Codex workflow for start/save/search/handoff

**Exit criteria:**

- a Codex user can install the plugin and use `reza` memory workflows without manual repo spelunking

### Phase 6: VS Code Extension MVP

**Objective:** Make the memory system available inside VS Code and compatible forks.

**Files:**

- Create: `extensions/reza-vscode/package.json`
- Create: `extensions/reza-vscode/tsconfig.json`
- Create: `extensions/reza-vscode/src/extension.ts`
- Create: `extensions/reza-vscode/src/commands/startSession.ts`
- Create: `extensions/reza-vscode/src/commands/saveSession.ts`
- Create: `extensions/reza-vscode/src/commands/showHandoff.ts`
- Create: `extensions/reza-vscode/src/commands/searchHistory.ts`
- Create: `extensions/reza-vscode/src/commands/ingestExport.ts`
- Create: `extensions/reza-vscode/src/state/rezaClient.ts`
- Create: `extensions/reza-vscode/README.md`

**Deliverables:**

- session start/save/end from the editor
- history search panel
- handoff viewer
- export/drop-zone ingest command for GUI tools
- extension architecture that works in VS Code and forks like Cursor

**Exit criteria:**

- a developer can search and resume work from inside the editor without touching the terminal
- the extension uses the same underlying `reza` data model as the CLI

### Phase 7: Packaging, Benchmarks, and Release Discipline

**Objective:** Ship the platform as a dependable product, not a promising prototype.

**Files:**

- Modify: `pyproject.toml`
- Modify: `npm/package.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `tests/test_upgrade_paths.py`
- Create: `tests/test_end_to_end_memory.py`
- Create: `docs/benchmarks/`

**Deliverables:**

- upgrade-path tests for old databases
- end-to-end sync tests across multiple tools
- packaging flow for PyPI, npm, and the extension
- benchmark story for search speed, sync latency, and handoff quality

**Exit criteria:**

- releases can be cut without hand-validating every critical workflow
- performance regressions are measurable

## Recommended Execution Order

Do not implement this as one giant branch. Use separate spec -> plan -> implementation cycles in this order:

1. Phase 0 + Phase 1
2. Phase 2
3. Phase 3 + Phase 4
4. Phase 5
5. Phase 6
6. Phase 7

This ordering is strict for one reason: a VS Code extension or Codex plugin sitting on top of unreliable persistence will only make the failure more visible.

## Immediate Next Plans To Write

The next concrete planning documents should be:

1. `docs/superpowers/specs/2026-04-15-persistence-hardening-design.md`
2. `docs/superpowers/plans/2026-04-15-persistence-hardening.md`
3. `docs/superpowers/specs/2026-04-15-adapter-framework-design.md`
4. `docs/superpowers/plans/2026-04-15-adapter-framework.md`
5. `docs/superpowers/specs/2026-04-15-threaded-retrieval-design.md`
6. `docs/superpowers/plans/2026-04-15-threaded-retrieval.md`

## Guardrails

Do not do these early:

- do not add embeddings before thread-aware lexical retrieval is solid
- do not let the VS Code extension bypass the CLI and mutate SQLite directly in v1
- do not promise direct GUI-tool adapters until their storage formats are stable
- do not ship docs that describe commands which do not exist in the release

## Success Definition

This project is successful when:

- conversation turns from supported tools arrive automatically and reliably
- every session belongs to a searchable continuity model
- LLMs can search history instead of replaying it
- handoff quality is stable across tool switches
- the same memory system powers the CLI, Codex plugin, and VS Code extension

## References

- `docs/superpowers/specs/2026-04-10-reza-session-continuity-design.md`
- `docs/superpowers/specs/2026-04-12-universal-sync-design.md`
- `docs/superpowers/plans/2026-04-10-session-continuity.md`
