# reza

**Universal LLM Context Database** — give any AI coding tool instant awareness of your project.

Index your project once. Never re-explain it again.

[![PyPI version](https://img.shields.io/pypi/v/reza.svg)](https://pypi.org/project/reza/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Works with](https://img.shields.io/badge/works%20with-Claude%20%7C%20Cursor%20%7C%20Codex%20%7C%20Aider%20%7C%20Kilocode-green.svg)](#integrations)

---

## The Problem

Every time you start a new AI session, you waste 5–15 minutes re-explaining your project:

- What the stack is
- Where the key files are
- What was already tried
- Why certain decisions were made

Switch from Claude to Cursor mid-task? Start over. Hit a context limit? Your architectural decisions vanish. Use two AI tools at once? They have no idea what each other did.

**This is a solved problem. reza solves it.**

---

## The Solution

reza creates a local SQLite database (`.reza/context.db`) in your project that stores:

- Every file path, type, line count, and **purpose** (extracted from docstrings and comments)
- All active LLM sessions and their progress
- A real-time change log synced via file watcher and git hooks
- Handoff notes so any LLM can continue where another left off

Any AI tool can query this database instead of scanning your files.

---

## Quick Start

```bash
pip install reza
cd your-project
reza init
```

That's it. Your project is now indexed.

```bash
reza status          # what reza knows about your project
reza query           # full context overview
reza watch &         # optional: real-time file sync
```

---

## Measured Token Savings

Tested on a real 1,710-file monorepo (Django + 2× FastAPI + 4× React):

| Scenario | Without reza | With reza | Reduction |
|----------|-------------|-----------|-----------|
| Task orientation (find relevant files) | ~18,000 tokens | ~4,900 tokens | **73%** |
| Cross-LLM handoff | ~10,000 tokens | ~1,250 tokens | **88%** |
| Find a specific file | ~7,200 tokens | ~450 tokens | **94%** |

**At 500 sessions/month on Claude Sonnet: ~$14/month saved in API costs.**  
More importantly: **58+ hours of developer wait time returned.**

---

## CLI Reference

### Core commands

```bash
reza init                     # Initialize reza in the current project
reza status                   # Quick project overview
reza watch                    # Start real-time file watcher
reza upgrade                  # Re-scan all files (after big refactors)
```

### Querying

```bash
reza query                    # Full project overview
reza query --find "auth"      # Search files by path or purpose
reza query --recent           # Last 30 file changes
reza query --sessions         # Active / interrupted sessions
reza query --file src/api.py  # Full info about one file
reza query --json             # Machine-readable JSON output
```

### Session management

```bash
# Start a session (get back a session ID)
reza session start --llm claude --task "implementing JWT auth"

# Save progress
reza session save --id claude-abc12345 \
  --summary "Models and serializers done, starting views" \
  --context "Decided on JWT over sessions — see auth/tokens.py. Avoid circular import in models.py" \
  --files "auth/models.py, auth/serializers.py"

# Check for interrupted sessions (cross-LLM handoff)
reza session handoff

# List all sessions
reza session list

# Close a session
reza session end --id claude-abc12345
```

### Exporting (for tools without direct DB access)

```bash
reza export                          # .reza/CONTEXT.md (human-readable markdown)
reza export --format json            # .reza/context.json (machine-readable)
reza export --format context         # compact format optimized for LLM prompts
reza export -o /path/to/output.md    # custom output path
```

### Git hooks

```bash
reza hooks                    # Install pre-commit hook (auto-update on commit)
reza hooks --uninstall        # Remove the hook
```

---

## Integrations

reza works with every major AI coding tool.

| Tool | Method | Guide |
|------|--------|-------|
| **Claude Code** | Native skill — auto-triggered | [integrations/claude-code/](integrations/claude-code/SKILL.md) |
| **Cursor** | `.cursorrules` | [integrations/cursor/](integrations/cursor/.cursorrules) |
| **Kilocode** | Rules file | [integrations/kilocode/](integrations/kilocode/rules.md) |
| **Aider** | `--read .reza/CONTEXT.md` | [integrations/aider/](integrations/aider/README.md) |
| **Continue.dev** | `@file` / config.json | [integrations/continue/](integrations/continue/README.md) |
| **GitHub Copilot** | `#file` / copilot-instructions.md | [integrations/github-copilot/](integrations/github-copilot/README.md) |
| **Codeium / Windsurf** | Context file | [integrations/codeium/](integrations/codeium/README.md) |
| **OpenAI Codex** | System prompt | [integrations/codex/](integrations/codex/README.md) |
| **Any other tool** | `reza export` → paste output | See below |

### Universal approach (works with any tool)

```bash
reza export --format context
# Copy .reza/CONTEXT.md into your tool's context window
```

---

## Cross-LLM Handoff

This is reza's killer feature. Hand off work between AI tools without re-explaining anything.

**Scenario**: Claude was implementing auth, hit its context limit. You switch to Cursor.

**Without reza**: Cursor starts from scratch. Re-explains stack, re-reads files, may contradict Claude's decisions.

**With reza**:

```bash
# In Cursor:
reza session handoff

# Output:
# Interrupted session: [claude] claude-abc12345
# Working on: JWT authentication implementation
# Summary: Models and serializers complete. Starting on views.
# Context: Decided on JWT over sessions because of multi-service architecture.
#          Avoid circular import in models.py — use string references.
#          Next: implement auth/views.py and wire up to urls.py
# Files modified: auth/models.py, auth/serializers.py
```

Cursor now knows exactly where to continue, what decisions were made, and what to avoid. Zero re-explanation.

---

## How It Works

```
Your project
├── .reza/
│   ├── context.db          ← SQLite database (the brain)
│   └── CONTEXT.md          ← Exported markdown (for tools without SQL)
├── src/
│   └── ...your code...
└── .git/
    └── hooks/
        └── pre-commit       ← Auto-updates DB on every commit
```

**Database schema (6 tables):**

| Table | What it stores |
|-------|---------------|
| `project_meta` | Language, framework, project name |
| `files` | All files with path, type, line count, purpose |
| `sessions` | LLM sessions with progress and context |
| `changes` | Real-time change log linked to sessions |
| `dependencies` | File import relationships |
| `conflicts` | Simultaneous edit detection |

**Three sync mechanisms:**

1. **`reza init`** — full scan on first use
2. **`reza watch`** — file watcher (Python `watchdog`) for real-time updates
3. **git pre-commit hook** — updates staged files on every commit

---

## Installation

### From PyPI (recommended)

```bash
pip install reza
```

### From source

```bash
git clone https://github.com/suwebreza/reza
cd reza
pip install -e .
```

### Requirements

- Python 3.8+
- `click` — CLI framework
- `rich` — terminal output
- `watchdog` — file watching (only needed for `reza watch`)

All dependencies install automatically with `pip install reza`.

---

## Per-Project Setup

```bash
cd your-project
reza init
```

This:
1. Creates `.reza/context.db`
2. Scans all source files and extracts purposes from docstrings/comments
3. Detects your project's language and framework
4. Installs a pre-commit git hook
5. Adds a comment to `.gitignore` (you decide whether to commit `.reza/`)

### Should I commit `.reza/`?

**Team projects**: Yes — commit it. Everyone gets shared context and session history.

**Solo projects**: Optional. The DB regenerates quickly with `reza init`.

---

## Supported Languages & Frameworks

Purpose extraction works for:

| Language | Purpose extracted from |
|----------|----------------------|
| Python | Module docstrings (`"""..."""`) |
| JavaScript / TypeScript | JSDoc comments (`/** ... */`) |
| Markdown | First `#` heading |
| Go / Java / Kotlin / Swift | `//` first-line comments |
| Rust | `///` doc comments |
| HTML / XML | `<!-- ... -->` comments |
| SQL / Lua | `--` comments |
| Ruby / Shell / YAML | `#` comments |

Framework detection: Django, FastAPI, Flask, React, Vue, Next.js, Nuxt, Svelte, Astro, Express, Fastify, Go, Rust/Cargo, Maven, Gradle, Rails, and more.

---

## Configuration

reza works with zero configuration. For advanced use:

### Extra ignore patterns

```bash
reza init --ignore generated --ignore vendor --ignore legacy
```

### Skip git hooks

```bash
reza init --no-hooks
```

### Custom project directory

```bash
reza init --dir /path/to/project
```

---

## Real-World Example

```bash
# Day 1: Start with Claude
cd my-saas-project
reza init
# → Indexed 847 files in 8.2 seconds

reza session start --llm claude --task "build subscription billing"
# → Session started: claude-f3a91b2c

# ... Claude implements Stripe integration ...

reza session save --id claude-f3a91b2c \
  --summary "Stripe webhook handler done. Subscription model created." \
  --context "Use Stripe's idempotency keys on all POST calls. Don't use our old PaymentMethod model — deprecated. Next: wire up frontend checkout flow." \
  --files "billing/models.py, billing/webhooks.py, billing/stripe.py"

# Day 2: Switch to Cursor for frontend work
reza session handoff
# → Shows claude-f3a91b2c with full context

reza session start --llm cursor --task "frontend checkout flow"
# → Cursor now knows the Stripe setup, deprecations, and next steps
```

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

**High-value contributions:**

- New tool integrations (in `integrations/`)
- Better purpose extraction heuristics
- Language-specific parsers (AST-based)
- VS Code extension that reads `.reza/context.db` directly
- Web UI for browsing the context database

---

## License

MIT — see [LICENSE](LICENSE).

---

## Author

Built by [Suweb Reza](https://github.com/suwebreza).

If reza saves you time, star the repo and tell your team.
