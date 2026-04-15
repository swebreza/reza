# reza

**Universal LLM Context Database** — instant project awareness for Claude, Cursor, Codex, Aider, Kilocode, and any AI coding tool.

## Install

```bash
npm install -g @swebreza/reza
```

This automatically installs the Python backend via `pip install reza`. Requires **Python 3.8+**.

## Usage

```bash
reza init          # index your project
reza query         # get full context overview
reza status        # quick status
reza watch         # real-time file sync
```

## What is reza?

reza indexes your project into a local SQLite database (`.reza/context.db`). Any AI tool queries this instead of scanning files — saving 73–94% of tokens per session.

**Key features:**
- **Auto-sync via Stop hook**: `reza install-claude-hook` — every Claude response synced automatically, even at context limit (zero tokens)
- **Cross-LLM handoff**: `reza session handoff --budget 8000` — full conversation brief ready to paste into Codex, Cursor, or any tool
- Searchable raw chat history: `reza session search "keyword"` pulls older relevant context back in
- Transcript ingest: `reza ingest .reza/handoffs/tool-20260410.json` for tools that export chats
- File locking: `reza claim src/auth.py --session ID` — prevent parallel agent conflicts
- Real-time sync: file watcher + git hooks keep the DB current automatically
- Works with Claude Code, Cursor, Kilocode, Aider, Copilot, Continue, Codeium, Codex

## Full documentation

→ **[github.com/swebreza/reza](https://github.com/swebreza/reza)**

## Troubleshooting

**"Python backend not found"**

The npm package is a shim — it requires Python 3.8+ and `pip install reza` to work.

```bash
# If postinstall failed, install manually:
pip install reza

# Verify:
reza --version
```

**Python not in PATH on Windows**

```bash
py -3 -m pip install reza
```

**Skip pip install during CI**

```bash
REZA_SKIP_POSTINSTALL=1 npm install -g @swebreza/reza
```

## License

MIT
