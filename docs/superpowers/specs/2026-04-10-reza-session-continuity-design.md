# Reza Session Continuity — Design Spec
**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Enhance `reza` with structured conversation history, file-drop ingestion, and token-budget-aware handoff export

---

## Problem

Reza already tracks LLM sessions (start/save/end/handoff), but `conversation_context` is a free-text blob. When Claude Code hits its context limit mid-task, there is no structured way to capture what was said, and no way for Codex or Cursor to pick up precisely where it left off. The result: developers re-explain context manually every time they switch tools.

---

## Goal

Enable seamless session continuity across AI tools (Claude Code → Codex → Cursor → etc.) by:
1. Storing structured conversation turns in reza's SQLite database
2. Accepting conversation transcripts via file drop (for tools without native reza integration)
3. Exporting a token-budget-aware handoff brief in markdown (for humans/AI prompts) or JSON (for machine consumers)

---

## Decisions

| Question | Decision |
|----------|----------|
| Where to build? | Enhance existing `reza` project (`Desktop/reza`) |
| Context ingestion | Both: structured CLI API + file drop to `.reza/handoffs/` |
| Who summarizes? | The AI tool summarizes before saving (`reza session save --summary "..."`) |
| Handoff output format | Both: markdown (default) + JSON via `--format json` |
| Architecture approach | Approach A: extend schema with `conversation_turns` table |

---

## Schema Changes

Add two tables to `reza/schema.py`:

```sql
-- Structured conversation turns
CREATE TABLE IF NOT EXISTS conversation_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    token_est   INTEGER DEFAULT 0,
    turn_index  INTEGER NOT NULL,
    recorded_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Tracks ingested file drops (prevents double-import)
CREATE TABLE IF NOT EXISTS handoff_drops (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT UNIQUE NOT NULL,
    session_id  TEXT,
    ingested_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_index   ON conversation_turns(session_id, turn_index);
```

The existing `conversation_context` TEXT column on `sessions` is kept as-is — it holds the AI-written summary. The new `conversation_turns` table holds structured turn-by-turn history. They are complementary: summary for quick handoff, turns for full fidelity.

---

## New Module: `reza/turns.py`

Owns all conversation turn logic:

- `add_turn(db, session_id, role, content, token_est, turn_index)` — append one turn
- `add_turns_bulk(db, session_id, turns: list[dict])` — batch insert from parsed file
- `list_turns(db, session_id)` — return all turns ordered by turn_index
- `turns_within_budget(db, session_id, budget_tokens)` — return most-recent turns whose cumulative `token_est` fits within budget (oldest dropped first)

---

## New Module: `reza/ingest.py`

Parses and imports file-drop transcripts:

**Supported formats:**

1. **Markdown** (`.md`) — turns delimited by HTML comment markers:
   ```markdown
   <!-- role: user -->
   What should I do next?

   <!-- role: assistant -->
   Apply the gold palette to Login.jsx first...
   ```

2. **JSON** (`.json`) — standard messages array:
   ```json
   [
     {"role": "user", "content": "What should I do next?"},
     {"role": "assistant", "content": "Apply the gold palette to Login.jsx first..."}
   ]
   ```

Functions:
- `parse_markdown_transcript(file_path)` → `list[dict]`
- `parse_json_transcript(file_path)` → `list[dict]`
- `ingest_file(db, file_path, session_id=None)` — parse, create session if needed, bulk-insert turns, record in `handoff_drops`

Token estimation: `len(content) // 4` (character-based approximation, no external dependency).

---

## CLI Changes

### New: `reza session turns` subgroup

```bash
# Append a single turn
reza session turns add --id <session_id> --role user|assistant|system --content "..." [--tokens N]

# Bulk-save from a JSON array file
reza session turns add --id <session_id> --from-file turns.json

# List turns (debugging)
reza session turns list --id <session_id>
```

### New: `reza ingest <file>`

```bash
reza ingest .reza/handoffs/codex-session.md
reza ingest .reza/handoffs/claude-export.json
```

- Detects format from file extension
- Creates a new session in reza if no `--session-id` provided; `llm_name` is parsed from the filename prefix (e.g. `codex-20260410.md` → `codex`, `claude-abc.json` → `claude`), falling back to `"unknown"` if unparseable
- Records ingestion in `handoff_drops` to prevent re-import
- Prints the created/linked session ID on success

### Extended: `reza session handoff`

```bash
reza session handoff                         # latest interrupted session, markdown
reza session handoff --id <session_id>       # specific session
reza session handoff --format json           # machine-readable
reza session handoff --budget 8000           # truncate to ~8k tokens
reza session handoff --format json --budget 4000
```

### Extended: `reza watch`

Auto-ingests files dropped into `.reza/handoffs/` directory. Calls `ingest_file()` on any new `.md` or `.json` file detected by the file watcher.

---

## Handoff Output Format

### Markdown (default)

```markdown
# Session Handoff: claude-abc123
**Tool:** Claude Code  |  **Started:** 2026-04-10 14:22  |  **Status:** interrupted

## What Was Being Done
<session.working_on>

## Summary
<session.summary (AI-written)>

## Last Conversation (~8000 tokens, most recent first)
**assistant:** ...
**user:** ...

## Files Modified
- path/to/file.jsx

## Pick Up From Here
<last assistant turn or explicit resume_from field>
```

### JSON (`--format json`)

```json
{
  "session_id": "claude-abc123",
  "llm": "claude",
  "status": "interrupted",
  "started_at": "2026-04-10T14:22:00",
  "working_on": "...",
  "summary": "...",
  "turns": [
    {"role": "assistant", "content": "...", "token_est": 420, "turn_index": 7}
  ],
  "files_modified": ["path/to/file.jsx"],
  "budget_applied": 8000,
  "turns_truncated": 3
}
```

**Budget truncation rule:** Drop oldest turns first. Summary and `working_on` are always included regardless of budget.

---

## File Drop Directory

`.reza/handoffs/` is created by `reza init` automatically. Workflow:
1. AI tool exports its conversation to `.reza/handoffs/<llm>-<timestamp>.md` (or `.json`)
2. `reza watch` detects the file and calls `ingest_file()` automatically
3. OR: developer runs `reza ingest <file>` manually
4. Next AI tool runs `reza session handoff` and gets the full context

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `--id` references unknown session | Clear error: "Session X not found" |
| File already ingested | Skip silently, print "already ingested: <file>" |
| Unknown file format | Error: "Unsupported format. Use .md or .json" |
| `--budget` too small to fit even summary | Return summary only, warn "budget too small for turns" |
| Malformed JSON transcript | Error with line number |
| Malformed markdown transcript (no markers) | Treat entire file as single assistant turn, warn |

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `reza/schema.py` | Add `conversation_turns` + `handoff_drops` tables and indexes; add `handoffs/` dir creation to `init_schema` |
| `reza/turns.py` | New module — all turn CRUD + budget truncation |
| `reza/ingest.py` | New module — transcript parsing + file drop ingestion |
| `reza/session.py` | Extend `handoff()` to include turns with `--budget` + `--format` |
| `reza/watcher.py` | Watch `.reza/handoffs/` and auto-call `ingest_file()` |
| `reza/cli.py` | Add `session turns` subgroup, `ingest` command, extend `session handoff` flags |
| `tests/test_turns.py` | New — unit tests for turn add/list/budget truncation |
| `tests/test_ingest.py` | New — unit tests for markdown + JSON parsing, double-import guard |

---

## Out of Scope

- reza does NOT call any LLM API to summarize — the AI tool is responsible for summarization before saving
- No UI — all interaction is CLI
- No cloud sync — SQLite stays local
- No turn editing or deletion (append-only for integrity)
