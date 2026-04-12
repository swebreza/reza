---
name: reza
description: >
  Universal LLM context database. Query project structure instantly using reza.
  ACTIVATE when: user says "pick up where I left off", "what is this project",
  "continue the previous session", "what files are in this project", "what LLM
  was working on this", "reza", "context database", ".reza/context.db" exists,
  or at the start of any session on a project that has .reza/context.db.
triggers:
  - .reza/context.db exists in project
  - "pick up where"
  - "what is this project"
  - "continue from"
  - "what was I working on"
  - "reza query"
  - "reza status"
---

# reza — Universal LLM Context Database

reza gives you instant project awareness without scanning files.
**Always query before touching code.**

## Step 1 — Check if reza is initialized

```bash
reza status
```

If it fails: run `reza init` first.

## Step 2 — Get project overview

```bash
reza query
```

This returns: project name, language, framework, active sessions,
and a breakdown of all indexed files with their purposes.

## Step 3 — Find specific files

```bash
reza query --find "authentication"
reza query --find "api"
reza query --find "database"
```

Use this instead of glob/grep when looking for files by purpose.

## Step 4 — Check for interrupted sessions (handoff)

```bash
reza session handoff
```

If any sessions appear, use the summary and recent turns first. If you need
older, specific context, search the raw transcript:

```bash
reza session search "keyword from the earlier discussion"
```

## Step 5 — Start your own session

```bash
reza session start --llm claude --task "describe what you are doing"
```

Copy the session ID printed. Use it to save progress:

```bash
reza session save --id claude-XXXXXXXX \
  --summary "what was accomplished" \
  --context "key decisions, what to do next, what failed" \
  --files "src/auth.py, src/models.py"
```

For turn-by-turn continuity, append turns directly or ingest an exported transcript:

```bash
reza session turns add --id claude-XXXXXXXX --role assistant --content "what changed, what is next"
reza ingest .reza/handoffs/claude-20260410.json
```

## Step 6 — End your session

```bash
reza session end --id claude-XXXXXXXX --summary "final summary"
```

## Query reference

```bash
reza query                    # full project overview
reza query --find TEXT        # search by path or purpose
reza query --recent           # last 30 file changes
reza query --sessions         # active / interrupted sessions
reza query --file src/foo.py  # info about one file
reza query --json             # machine-readable output
```

## Export (for non-SQL tools)

```bash
reza export                   # .reza/CONTEXT.md (markdown)
reza export --format json     # .reza/context.json
reza export --format context  # compact LLM prompt format
```

## Workflow rules

1. **Query first, code second.** Never start reading files before running `reza query`.
2. **Use `--find` instead of glob.** `reza query --find auth` is faster and more accurate than globbing.
3. **Save progress before ending.** Use `reza session save` when switching tasks or tools.
4. **Check handoff.** Always run `reza session handoff` at the start of a session.
5. **Search old chat when needed.** Use `reza session search` instead of relying only on recency.

## File info

```bash
reza query --file src/api.py   # shows purpose, line count, recent changes
```

## Token savings

- `reza query` costs ~200 tokens vs ~18,000 tokens for manual file scanning
- `reza session handoff` costs ~300 tokens vs 10,000+ tokens to re-explain context
- Use reza to stay within context limits on large projects
