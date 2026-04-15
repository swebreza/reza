# reza Integration — GitHub Copilot

Use reza with GitHub Copilot Chat to give it instant project awareness.

## Setup

```bash
# Install reza from GitHub source once:
git clone https://github.com/swebreza/reza
cd reza
pip install -e .

cd your-project
reza init
reza export --format context   # generates .reza/CONTEXT.md
```

## Usage with Copilot Chat

### Attach context file

In Copilot Chat (VS Code), use `#file` to attach the context:

```
#file:.reza/CONTEXT.md
What files handle user authentication in this project?
```

### Use as workspace context

With the Copilot workspace feature, add to `.github/copilot-instructions.md`:

```markdown
# Copilot Instructions

This project uses reza (Universal LLM Context Database).

Before suggesting file changes, read `.reza/CONTEXT.md` for the current project structure.

Key context:
- Run `reza query` to get live project overview
- Run `reza session handoff` to see interrupted sessions from other AI tools
- Run `reza query --find "keyword"` to find files by purpose
```

## .github/copilot-instructions.md template

Create this file in your repo (Copilot reads it automatically in VS Code):

```markdown
## Project Context

This project is indexed by reza. Always check `.reza/CONTEXT.md` for:
- Project language and framework
- File list with purposes
- Any sessions left by other AI tools (Claude, Cursor, Aider, etc.)

To get fresh context: run `reza export` in terminal.
To find files: run `reza query --find "what you need"`.
```

## Cross-tool handoff

```bash
# See what Claude or Cursor left off:
reza session handoff

# Save your Copilot session for later:
reza session start --llm copilot --task "..."
reza session save --id copilot-XXXXXXXX --summary "..." --context "..."
reza session end --id copilot-XXXXXXXX
```

## Regenerate context

```bash
reza export   # refreshes .reza/CONTEXT.md
```

Then re-attach in Copilot Chat: `#file:.reza/CONTEXT.md`
