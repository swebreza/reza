# reza Integration — Aider

reza works with Aider via `--read` to inject project context into every session.

## Setup

```bash
pip install reza
cd your-project
reza init
```

## Usage with Aider

### Option 1 — Auto-inject context (recommended)

Generate the context file first:

```bash
reza export --format context
```

Then start Aider with it:

```bash
aider --read .reza/CONTEXT.md
```

This gives Aider instant project awareness — framework, files, purposes, active sessions.

### Option 2 — Regenerate context before each Aider session

Add this to your workflow:

```bash
reza export && aider --read .reza/CONTEXT.md
```

Or create a shell alias:

```bash
alias aider-reza='reza export && aider --read .reza/CONTEXT.md'
```

### Option 3 — Add to .aider.conf.yml

```yaml
# .aider.conf.yml
read:
  - .reza/CONTEXT.md
```

Then just run `aider` — the context file is always included.

## Cross-LLM Handoff with Aider

Before starting Aider, check what Claude or Cursor left off:

```bash
reza session handoff
```

After an Aider session, save progress so Claude or others can pick up:

```bash
reza session start --llm aider --task "refactoring auth module"
# ... do your work ...
reza session save --id aider-XXXXXXXX \
  --summary "Extracted JWT logic to auth/tokens.py" \
  --context "Next: update middleware to use new token module. models.py has circular import — avoid it." \
  --files "auth/tokens.py, auth/middleware.py"
reza session end --id aider-XXXXXXXX
```

## Watch mode (real-time sync)

Start reza's watcher alongside Aider so the DB stays current:

```bash
reza watch &
aider --read .reza/CONTEXT.md
```

Every file Aider modifies is automatically recorded in the context DB.

## Tips

- After a big refactor: `reza upgrade` to re-scan all file purposes
- Regenerate CONTEXT.md after each session: `reza export`
- Use `reza query --find "keyword"` from another terminal to locate files
