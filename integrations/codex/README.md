# reza Integration — OpenAI Codex / ChatGPT

Use reza with OpenAI Codex CLI or ChatGPT to share project context.

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

## Codex CLI

### Inject context as system message

```bash
reza export --format context -o /tmp/ctx.md
codex --system-prompt "$(cat /tmp/ctx.md)" "help me with ..."
```

### Shell alias for context-aware Codex

```bash
alias codex-reza='reza export --format context -o /tmp/.reza_ctx.md && codex --system-prompt "$(cat /tmp/.reza_ctx.md)"'
```

Usage:
```bash
codex-reza "find the authentication middleware"
```

## ChatGPT / GPT-4

Paste the context output into your first message:

```bash
reza export --format context    # generates .reza/CONTEXT.md
cat .reza/CONTEXT.md            # copy this output
```

Then in ChatGPT:
```
[Paste the CONTEXT.md contents here]

Given this project context, help me: ...
```

## OpenAI Assistants API

Use reza's JSON export as a file for retrieval:

```bash
reza export --format json   # generates .reza/context.json
```

Upload `context.json` to your Assistant as a knowledge file.
The assistant can then answer questions like "what files handle auth?" accurately.

## Cross-LLM handoff with Codex

```bash
# Check what Claude / Cursor left off:
reza session handoff
reza session search "auth middleware"

# Save your Codex session:
reza session start --llm codex --task "..."
reza session save --id codex-XXXXXXXX --summary "..." --context "..."
reza session turns add --id codex-XXXXXXXX --role assistant --content "what you decided / what is next"
reza session end --id codex-XXXXXXXX

# Or ingest a full exported transcript when Codex wrote chat history elsewhere:
reza ingest .reza/handoffs/codex-20260410.json

# Resume from Codex in Claude:
reza session handoff    # shows summary + recent turns
reza session search "keyword" --id codex-XXXXXXXX
```

## Prompt template for Codex

```
Project Context:
$(reza export --format context 2>/dev/null | head -50)

Task: [your task here]

Important files:
$(reza query --find "[keyword]" --json 2>/dev/null)
```
