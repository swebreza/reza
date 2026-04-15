# reza Integration — Kilocode

Add these rules to your Kilocode configuration to enable reza context awareness.

## System Instructions

```
This project uses reza (Universal LLM Context Database).
The database is at .reza/context.db.

ALWAYS run these commands at the start of each session:

1. reza session handoff        — check for interrupted sessions from other AI tools
2. reza query                  — get full project overview

ALWAYS use reza for file discovery instead of ls/find/glob:
    reza query --find "keyword"    — find files by purpose or path

When starting work:
    reza session start --llm kilocode --task "describe task"

When saving progress:
    reza session save --id kilocode-XXXXXXXX --summary "..." --context "..."

When done:
    reza session end --id kilocode-XXXXXXXX
```

## Quick Reference

| Task | Command |
|------|---------|
| Project overview | `reza query` |
| Find files | `reza query --find "keyword"` |
| Check handoff | `reza session handoff` |
| Recent changes | `reza query --recent` |
| Start session | `reza session start --llm kilocode --task "..."` |
| Save progress | `reza session save --id ID --summary "..." --context "..."` |
| End session | `reza session end --id ID` |
| Export context | `reza export` |
| Quick status | `reza status` |

## Setup

```bash
# Install reza from GitHub source once:
git clone https://github.com/swebreza/reza
cd reza
pip install -e .

cd your-project
reza init
reza watch &   # optional: real-time sync
```

## Why use reza with Kilocode?

- Skip project orientation (saves 5–15 min per session)
- Pick up interrupted work from Claude, Cursor, or Aider instantly
- Find the right file in 1 query instead of 5 globs
- Share architectural decisions across all your AI tools
