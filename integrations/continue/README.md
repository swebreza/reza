# reza Integration — Continue.dev

Use reza with Continue (VS Code / JetBrains extension) to give it permanent project context.

## Setup

```bash
pip install reza
cd your-project
reza init
reza export --format context   # generates .reza/CONTEXT.md
```

## Method 1 — @File context provider

In any Continue chat, reference the context file directly:

```
@.reza/CONTEXT.md what files handle authentication?
```

Regenerate before using:

```bash
reza export
```

## Method 2 — Always-on context via config.json

Add reza's context file as a persistent context provider in `~/.continue/config.json`:

```json
{
  "contextProviders": [
    {
      "name": "file",
      "params": {
        "nRetrieve": 10,
        "nFinal": 5,
        "useReranking": false
      }
    }
  ],
  "systemMessage": "This project uses reza for context. The file .reza/CONTEXT.md contains the full project structure, active sessions, and key file purposes. Always check it before suggesting changes."
}
```

## Method 3 — Custom slash command

Add to your Continue config for a quick context refresh:

```json
{
  "slashCommands": [
    {
      "name": "reza",
      "description": "Load reza project context",
      "params": {
        "prompt": "Run: reza query --json and summarize the project structure for me."
      }
    }
  ]
}
```

## Cross-LLM handoff

```bash
# Before starting Continue session:
reza session handoff

# After Continue session:
reza session start --llm continue --task "..."
# ... work ...
reza session save --id continue-XXXXXXXX --summary "..." --context "..."
reza session end --id continue-XXXXXXXX
```

## Keep context fresh

Run this before each Continue session:

```bash
reza export && code .   # regenerate then open VS Code
```

Or keep the watcher running:

```bash
reza watch &   # auto-updates DB on every file save
```
