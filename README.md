# reza

**Universal LLM Context Database** — give any AI coding tool instant awareness of your project.

Index your project once. Never re-explain it again.

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
git clone https://github.com/swebreza/reza
cd reza
pip install -e .

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

## Install as an AI CLI Skill

Install reza once into your AI tool so it auto-activates on every project — no manual setup per session.

### Claude Code

Installs `/reza` as a slash command. Type `/reza` in any Claude Code session to instantly load your project context.

**One-line install:**

```bash
mkdir -p ~/.claude/skills/reza && curl -fsSL \
  https://raw.githubusercontent.com/swebreza/reza/main/integrations/claude-code/SKILL.md \
  -o ~/.claude/skills/reza/SKILL.md
```

**Or manually:**

```bash
mkdir -p ~/.claude/skills/reza
cp integrations/claude-code/SKILL.md ~/.claude/skills/reza/SKILL.md
```

Restart Claude Code, then type `/` — you'll see **reza** in the skill list.

It also **auto-triggers** whenever you say:
- "pick up where I left off"
- "what is this project"
- "continue from last session"
- "what was I working on"

---

### Cursor

Copy the `.cursorrules` file into your project root:

```bash
cp integrations/cursor/.cursorrules your-project/.cursorrules
```

Or add globally to `~/.cursor/rules/reza.mdc`:

```bash
mkdir -p ~/.cursor/rules
cp integrations/cursor/.cursorrules ~/.cursor/rules/reza.mdc
```

Cursor will now prompt reza queries automatically at session start.

---

### Kilocode

```bash
# Copy into your project:
cp integrations/kilocode/rules.md your-project/.kilocode/reza.md

# Or add globally to Kilocode's rules directory:
cp integrations/kilocode/rules.md ~/.kilocode/rules/reza.md
```

---

### Aider

```bash
# Add to your project's .aider.conf.yml:
echo "read:" >> .aider.conf.yml
echo "  - .reza/CONTEXT.md" >> .aider.conf.yml

# Generate the context file before each session:
reza export

# Then just run aider normally — context is always included:
aider
```

Or pass it inline per session:

```bash
reza export && aider --read .reza/CONTEXT.md
```

---

### GitHub Copilot

```bash
# Creates .github/copilot-instructions.md (Copilot reads this automatically):
mkdir -p .github
cp integrations/github-copilot/README.md .github/copilot-instructions.md
```

Then in Copilot Chat, reference the exported context:

```
#file:.reza/CONTEXT.md  what files handle authentication?
```

---

### Continue.dev

```bash
# Generate context file:
reza export

# Reference in chat:
@.reza/CONTEXT.md
```

Or add to `~/.continue/config.json` to auto-include on every session — see [integrations/continue/README.md](integrations/continue/README.md).

---

### Codeium / Windsurf

```bash
reza export --format context   # generates .reza/CONTEXT.md
```

In Windsurf Cascade:
```
@.reza/CONTEXT.md
```

In Codeium: keep `.reza/CONTEXT.md` open in an editor tab — Codeium reads open files.

---

### OpenAI Codex CLI

```bash
# Create a shell alias that auto-injects reza context:
alias codex-reza='reza export --format context -o /tmp/.reza_ctx.md && codex --system-prompt "$(cat /tmp/.reza_ctx.md)"'

# Use it:
codex-reza "find the authentication middleware"
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

### Parallel agents — file locks & conflict detection

When two AI tools work on the same repo at the same time, reza prevents silent overwrites.

```bash
# Claim a file before editing (prevents other agents from touching it)
reza claim src/auth.py --session claude-abc12345

# See all active locks across all agents
reza locks
reza locks --session cursor-xyz789   # filter by session

# Release a lock when done
reza release src/auth.py --session claude-abc12345
reza release --all-session claude-abc12345   # release all at once

# View all open conflicts
reza conflicts
reza conflicts --all                          # include resolved

# Resolve conflicts
reza conflicts --resolve 3                    # by ID
reza conflicts --resolve-file src/auth.py     # all conflicts on one file
```

Conflicts are also detected **automatically**:
- `reza watch` prints a stderr alert the moment a locked file is written by a different session
- The git pre-commit hook checks staged files against active locks on every commit
- `reza session end` auto-releases all locks for that session — no dangling locks

### Git hooks

```bash
reza hooks                    # Install pre-commit hook (auto-update on commit)
reza hooks --uninstall        # Remove the hook
```

---

## Integrations

reza works with every major AI coding tool.

| Tool | Skill Install | Per-Project Setup | Guide |
|------|--------------|-------------------|-------|
| **Claude Code** | `curl` into `~/.claude/skills/reza/` | `reza init` | [→](integrations/claude-code/SKILL.md) |
| **Cursor** | Copy `.cursorrules` globally | `reza init` | [→](integrations/cursor/.cursorrules) |
| **Kilocode** | Copy `rules.md` to `~/.kilocode/rules/` | `reza init` | [→](integrations/kilocode/rules.md) |
| **Aider** | Add to `.aider.conf.yml` | `reza export` | [→](integrations/aider/README.md) |
| **Continue.dev** | Edit `~/.continue/config.json` | `reza export` | [→](integrations/continue/README.md) |
| **GitHub Copilot** | Copy to `.github/copilot-instructions.md` | `reza export` | [→](integrations/github-copilot/README.md) |
| **Codeium / Windsurf** | Open context file in editor | `reza export` | [→](integrations/codeium/README.md) |
| **OpenAI Codex** | Shell alias with `--system-prompt` | `reza export` | [→](integrations/codex/README.md) |
| **Any other tool** | `reza export` → paste output | `reza export` | — |

### Universal approach (works with any tool)

```bash
reza export --format context
# Paste .reza/CONTEXT.md content into your tool's context window
```

---

## Parallel Agents — Running Claude + Cursor Simultaneously

reza makes it safe to run multiple AI tools on the same repo at the same time.

```
Claude (terminal 1)              Cursor (editor)
        │                               │
reza session start                reza session start
--llm claude                      --llm cursor
        │                               │
reza claim src/auth.py            reza claim src/auth.py
--session claude-abc123           --session cursor-xyz789
        │                               │
  ✅ GRANTED                       ❌ CONFLICT — file locked by claude
                                   Alert printed to stderr immediately
                                   Logged to conflicts table
```

**Typical parallel workflow:**

```bash
# Terminal 1 — Claude works on backend
reza session start --llm claude --task "auth backend"
reza claim src/auth.py --session claude-abc123
reza claim src/models.py --session claude-abc123
# ... Claude edits auth.py and models.py ...

# Terminal 2 — Cursor works on frontend simultaneously
reza session start --llm cursor --task "login UI"
reza claim src/components/Login.jsx --session cursor-xyz789
# ... Cursor edits Login.jsx (no conflict) ...

# Cursor tries to touch a locked file:
reza claim src/auth.py --session cursor-xyz789
# → CONFLICT: auth.py is locked by claude (claude-abc123)

# Claude finishes and releases
reza session end --id claude-abc123   # auto-releases all locks

# Now Cursor can claim it safely
reza claim src/auth.py --session cursor-xyz789   # ✅ granted
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

**Database schema (7 tables):**

| Table | What it stores |
|-------|---------------|
| `project_meta` | Language, framework, project name |
| `files` | All files with path, type, line count, purpose |
| `sessions` | LLM sessions with progress and context |
| `changes` | Real-time change log linked to sessions |
| `file_locks` | Active file locks — which session owns which file |
| `conflicts` | Conflict history — when two agents touched the same locked file |
| `dependencies` | File import relationships |

**Three sync mechanisms:**

1. **`reza init`** — full scan on first use
2. **`reza watch`** — file watcher (Python `watchdog`) for real-time updates
3. **git pre-commit hook** — updates staged files on every commit

---

## Installation

### From source

```bash
git clone https://github.com/swebreza/reza
cd reza
pip install -e .
```

### Requirements

- Python 3.8+
- `click` — CLI framework
- `rich` — terminal output
- `watchdog` — file watching (only needed for `reza watch`)

All dependencies install automatically with `pip install -e .`.

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

### Sequential handoff (Claude → Cursor)

```bash
# Day 1: Start with Claude Code
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
# → Shows claude-f3a91b2c with full context — zero re-explanation needed

reza session start --llm cursor --task "frontend checkout flow"
# → Cursor knows the Stripe setup, deprecations, and exactly what to do next
```

### Parallel agents (Claude + Aider at the same time)

```bash
# Both agents initialized on the same repo
reza watch &   # real-time conflict detection running in background

# Claude takes the API layer
reza session start --llm claude --task "REST endpoints"
reza claim src/api/ --session claude-f3a91b2c

# Aider takes the tests simultaneously
reza session start --llm aider --task "write test suite"
reza claim tests/ --session aider-8c2d4e1f

# If Aider tries to touch src/api/:
reza claim src/api/auth.py --session aider-8c2d4e1f
# → CONFLICT: src/api/auth.py is locked by claude (claude-f3a91b2c)
# → Conflict logged, alert fired to terminal

# Check all open conflicts:
reza conflicts

# Claude finishes and releases everything:
reza session end --id claude-f3a91b2c
# → All claude locks auto-released — Aider can now claim any file safely
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

Built by [Suweb Reza](https://github.com/swebreza).

If reza saves you time, star the repo and tell your team.
