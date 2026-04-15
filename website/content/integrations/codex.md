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

### Picking up from Claude (recommended workflow)

If you installed the Claude Code Stop hook (`reza install-claude-hook`), every Claude turn was already synced automatically — including turns saved right at Claude's context limit.

```bash
# Get the handoff brief to paste into Codex:
reza session handoff --budget 8000
# → Full markdown: what was being done, recent conversation, files modified, pick-up point

# Search specific older context:
reza session search "auth middleware"
reza session search "JWT" --id claude-XXXXXXXX
```

Paste the `reza session handoff` output as your first Codex message. Codex has full context.

### Saving your Codex session

```bash
reza session start --llm codex --task "..."
reza session save --id codex-XXXXXXXX --summary "..." --context "..."
reza session end --id codex-XXXXXXXX

# Or ingest a full exported Codex transcript:
reza ingest .reza/handoffs/codex-20260410.json
```

### Resuming from Codex back in Claude

```bash
reza session handoff    # shows all interrupted sessions — Claude sees Codex's too
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
