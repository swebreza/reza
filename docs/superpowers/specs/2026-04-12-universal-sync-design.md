# Universal Conversation Sync — Design Spec
**Date:** 2026-04-12
**Status:** Approved
**Scope:** Make reza automatically capture full chat history from any AI tool — Cursor, Codex CLI, Aider, Kilocode, Codex Desktop, Claude Code — with zero developer action after one-time setup. Introduce cross-tool conversation threads so a session started in Cursor and continued in Claude and Codex is treated as one logical unit.

---

## Problem

The Claude Code Stop hook proved the concept: auto-sync conversation turns with zero tokens and zero developer action. But it only works for Claude Code. Every other tool requires manual `reza ingest` or `reza session turns add`. The system should be universal — one setup, all tools, same database, same handoff quality regardless of which tool you're in.

Additionally, reza currently treats each tool's session independently. When a developer moves Cursor → Claude Desktop → Codex Desktop → Cursor, there are four disconnected sessions. `reza session handoff` shows only the most recent interrupted session, not the full cross-tool conversation thread. The result: context is still lost at tool boundaries.

---

## Goals

1. **Universal auto-sync** — every tool's conversation is saved automatically after one-time setup
2. **Single entry point** — `reza watch` handles file sync AND conversation sync, no extra daemon
3. **Cross-tool threads** — sessions belonging to the same logical task are linked by `thread_id`
4. **Seamless handoff** — `reza session handoff` returns the full thread history across all tools
5. **Graceful degradation** — tools whose file paths can't be resolved fall back to drop-zone silently

---

## Decisions

| Question | Decision |
|----------|----------|
| Architecture | Approach C: universal polling daemon + per-tool adapters inside `reza watch` |
| Sync mechanism | File-watch (watchdog) for CLI tools; drop-zone fallback for GUI tools with inaccessible storage |
| Config storage | `.reza/adapters.json` — written by `reza install-hooks`, read by `reza watch` |
| Thread linking | All three modes: auto (high confidence), semi-auto (medium confidence), explicit (`--continue` flag) |
| Thread storage | New `thread_id` TEXT column on `sessions` table; new `threads` table for metadata |
| Handoff scope | Default: full thread (all sessions). `--session-only` flag for single-session view |

---

## Schema Changes

### New column on `sessions`

```sql
ALTER TABLE sessions ADD COLUMN thread_id TEXT REFERENCES threads(id);
```

### New `threads` table

```sql
CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,           -- e.g. "thread-jwt-auth-a1b2c3"
    title       TEXT,                       -- human label, set on first session or auto-derived
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    status      TEXT DEFAULT 'active'       -- active | completed | archived
);

CREATE INDEX IF NOT EXISTS idx_sessions_thread ON sessions(thread_id);
```

### New `.reza/adapters.json` (not DB — flat file)

Written by `reza install-hooks`. Read by `reza watch` at startup.

```json
{
  "adapters": {
    "claude":        { "enabled": true,  "paths": ["~/.claude/projects/"] },
    "aider":         { "enabled": true,  "paths": ["<project>/.aider.chat.history.md"] },
    "codex-cli":     { "enabled": true,  "paths": ["~/.codex/conversations/"] },
    "cursor":        { "enabled": false, "reason": "path not found — use drop-zone" },
    "kilocode":      { "enabled": false, "reason": "path not found — use drop-zone" },
    "codex-desktop": { "enabled": false, "reason": "path not found — use drop-zone" }
  }
}
```

---

## New Module: `reza/adapters/`

### BaseAdapter (`reza/adapters/__init__.py`)

```python
class BaseAdapter:
    tool_name: str                    # "aider", "codex-cli", etc.

    def find_conversation_files(self, project_dir: Path, config: dict) -> list[Path]:
        """Return all conversation files this adapter should watch."""

    def parse_turns(self, file_path: Path) -> list[dict]:
        """Parse file into [{role, content}] list. Must be idempotent."""

    def get_session_hint(self, file_path: Path) -> str | None:
        """Return llm_name hint for session resolution (e.g. 'aider')."""
```

### AdapterRegistry (`reza/adapters/__init__.py`)

```python
class AdapterRegistry:
    def load(self, adapters_json: Path) -> None
    def find_adapter(self, changed_path: Path) -> BaseAdapter | None
    def all_watched_paths(self, project_dir: Path) -> list[Path]
```

### Adapters

| File | Tool | Format | Path |
|------|------|--------|------|
| `claude.py` | Claude Code | jsonl | `~/.claude/projects/HASH/*.jsonl` |
| `aider.py` | Aider | markdown (`> ` prefix) | `<project>/.aider.chat.history.md` |
| `codex_cli.py` | Codex CLI | jsonl (Claude-compatible) | `~/.codex/conversations/*.jsonl` |
| `cursor.py` | Cursor | unknown (research at install time) | drop-zone fallback |
| `kilocode.py` | Kilocode | unknown | drop-zone fallback |
| `codex_desktop.py` | Codex Desktop | unknown | drop-zone fallback |

Each adapter with `enabled: false` in `adapters.json` is skipped silently. Its drop-zone (`reza watch` already watches `.reza/handoffs/`) remains available.

---

## Cross-Tool Thread Linking

### Thread ID format

```
thread-<slug>-<8hex>
e.g. thread-jwt-auth-a1b2c3d4
```

Slug is auto-derived from the first session's `working_on` field (first 3 words, lowercased, hyphenated). Falls back to `thread-<8hex>` if `working_on` is empty.

### Three linking modes (all coexist)

#### Mode A — Automatic (high confidence)
Fires silently when ALL conditions are true:
- Same project (same `.reza/context.db`)
- There is a recent interrupted/active session in the same thread (< 2 hours ago)
- The new session's `working_on` has > 50% word overlap with the thread title OR is empty

Behavior: new session gets same `thread_id`, no prompt. Prints: `[reza] Continuing thread: jwt-auth-thread`

#### Mode B — Semi-automatic (medium confidence)
Fires when:
- Same project
- There is a recent interrupted session (< 8 hours ago)
- Confidence doesn't meet Mode A threshold

Behavior: `reza session start` prints a single prompt:
```
Continue thread 'jwt-auth-thread'? [Y/n]
```
Y → links. N → new thread. Non-interactive (CI/pipe): defaults to N.

#### Mode C — Explicit (always available, no guessing)
```bash
reza session start --llm cursor --task "add checkout" --continue          # links to most recent active thread
reza session start --llm cursor --task "add checkout" --thread thread-abc # links to specific thread
reza session start --llm cursor --task "unrelated work"                   # no --continue = new thread
```

---

## Updated `reza watch` Architecture

```
reza watch (single process)
│
├── FileWatcher (existing watchdog handler)
│   └── source files → files / changes tables
│
├── HandoffWatcher (existing)
│   └── .reza/handoffs/*.md|json → ingest_file()
│
└── ConversationWatcher (new watchdog handler)
    ├── reads AdapterRegistry from .reza/adapters.json at startup
    ├── registers watch paths for all enabled adapters
    └── on_modified(path):
        adapter = registry.find_adapter(path)
        turns   = adapter.parse_turns(path)
        sync_turns_incremental(db, resolve_session(adapter, path), turns)
```

`sync_turns_incremental` is the same idempotent function already used by `claude_sync.py` — count existing turns, append only the new tail.

---

## Updated Handoff — Thread-Aware

```bash
reza session handoff                        # full thread (default)
reza session handoff --session-only         # single session view (old behavior)
reza session handoff --thread thread-abc    # specific thread
reza session handoff --budget 8000          # token budget applies across all thread sessions
```

### Thread handoff output (markdown)

```markdown
# Thread Handoff: jwt-auth-thread
**Sessions:** cursor-abc → claude-def → codex-ghi → cursor-jkl
**Total turns:** 94  |  **Budget applied:** 8000 tokens  |  **Oldest turns dropped:** 31

## What Was Being Done
JWT authentication implementation

## Sessions in This Thread
- [cursor-abc]    Cursor       2026-04-12 09:00  completed
- [claude-def]    Claude Code  2026-04-12 11:30  interrupted
- [codex-ghi]     Codex        2026-04-12 14:00  interrupted
- [cursor-jkl]    Cursor       2026-04-12 15:22  active

## Full Conversation (most recent first, budget-truncated)
**assistant [codex]:** Next step is wiring the refresh token endpoint...
**user:** Can you also handle token expiry on the frontend?
...

## Files Modified (across all sessions)
- auth/models.py
- auth/views.py
- src/components/Login.jsx

## Pick Up From Here
Next step is wiring the refresh token endpoint...
```

---

## New CLI Commands

### `reza install-hooks`

```bash
reza install-hooks              # auto-detect all installed tools
reza install-hooks --tool aider # register one tool only
reza install-hooks --list       # show detected tools and their status
reza install-hooks --uninstall  # remove all adapter registrations
```

Auto-detection logic per tool:
- Check if binary exists in PATH (`aider`, `codex`, etc.)
- Check if known config/data paths exist
- Write result to `.reza/adapters.json`

### `reza sync-all`

Manual one-shot sync — runs all enabled adapters once. Useful when `reza watch` wasn't running.

```bash
reza sync-all
reza sync-all --tool aider      # one tool only
```

### `reza thread` subgroup

```bash
reza thread list                          # list all threads
reza thread show --id thread-abc          # full thread detail
reza thread link --session cursor-abc --thread thread-xyz   # manually link a session
reza thread title --id thread-abc --title "JWT auth work"   # rename a thread
```

### Extended `reza session start`

```bash
reza session start --llm cursor --task "..." --continue          # Mode C: link to recent thread
reza session start --llm cursor --task "..." --thread thread-abc # Mode C: link to specific thread
reza session start --llm cursor --task "..." --no-thread         # Mode C: force new thread
```

---

## Data Flow — Full Cross-Tool Example

```
09:00 — Developer starts in Cursor
  reza session start --llm cursor --task "JWT auth"
  → creates session cursor-abc, thread jwt-auth-a1b2c3d4
  → ConversationWatcher (cursor adapter) watches cursor's file
  → every cursor response auto-synced to conversation_turns

11:30 — Switches to Claude Code
  reza session start --llm claude --task "JWT auth"
  → Mode A fires (< 2hr, same task words) → auto-links to jwt-auth-a1b2c3d4
  → prints: [reza] Continuing thread: jwt-auth-thread
  → Claude Stop hook fires after every response → syncs to same thread

14:00 — Switches to Codex Desktop
  reza session start --llm codex-desktop --task "JWT refresh tokens"
  → Mode B fires (< 8hr, partial word overlap) → prompts: Continue thread? [Y/n]
  → Y → linked to jwt-auth-a1b2c3d4
  → Codex Desktop path unknown → drop-zone fallback
  → Developer drops export to .reza/handoffs/codex-desktop-20260412.json
  → reza watch ingests automatically → turns added to thread

15:22 — Back to Cursor
  reza session start --llm cursor --task "JWT auth frontend"
  → Mode A fires → auto-links to jwt-auth-a1b2c3d4
  → reza session handoff → full 94-turn thread across all 4 tools
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Tool binary not found at install | Adapter disabled, drop-zone fallback noted in output |
| Conversation file path changes between versions | `reza install-hooks` re-detects on re-run |
| Thread auto-link wrong | `reza thread unlink --session ID` to detach; `reza thread link` to re-link |
| Mode B prompt in non-interactive mode | Defaults to N (new thread) |
| Two tools write simultaneously | Each adapter syncs into its own session — no collision; same thread_id |
| `reza watch` not running | `reza sync-all` as manual fallback; docs note this |
| Adapter file format changes between tool versions | Adapter fails gracefully, logs warning, skips sync cycle |

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `reza/schema.py` | Add `threads` table; add `thread_id` column to `sessions` |
| `reza/adapters/__init__.py` | New — `BaseAdapter`, `AdapterRegistry` |
| `reza/adapters/claude.py` | New — refactor `claude_sync.py` into adapter pattern |
| `reza/adapters/aider.py` | New — parse `.aider.chat.history.md` |
| `reza/adapters/codex_cli.py` | New — parse `~/.codex/conversations/*.jsonl` |
| `reza/adapters/cursor.py` | New — research path; drop-zone fallback |
| `reza/adapters/kilocode.py` | New — research path; drop-zone fallback |
| `reza/adapters/codex_desktop.py` | New — research path; drop-zone fallback |
| `reza/threads.py` | New — thread CRUD: create, link, list, show, handoff |
| `reza/watcher.py` | Add `ConversationWatcher` handler; load `AdapterRegistry` |
| `reza/session.py` | `start_session` gains `thread_id` param + auto-link logic |
| `reza/cli.py` | Add `install-hooks`, `sync-all`, `thread` subgroup; extend `session start`, `session handoff` |
| `tests/test_adapters.py` | New — adapter parse tests for aider + codex-cli |
| `tests/test_threads.py` | New — thread create/link/handoff tests |
| `README.md` | Update CLI reference, cross-tool handoff section, how-it-works |
| `integrations/*/README.md` | Update each tool's integration guide |
| `CHANGELOG.md` | Add v0.5.0 entry |

---

## Out of Scope

- No cloud sync — SQLite stays local
- No UI — all CLI
- No LLM API calls — reza never summarizes; AI tools do
- No turn editing — append-only for integrity
- No automatic thread merging — threads are linked manually or by the three modes above
