# reza Integrations

reza works with every AI coding tool. Choose your tool below.

## Supported Tools

| Tool | Integration Type | Guide |
|------|-----------------|-------|
| **Claude Code** | Native skill (auto-triggered) | [claude-code/SKILL.md](claude-code/SKILL.md) |
| **Cursor** | `.cursorrules` file | [cursor/.cursorrules](cursor/.cursorrules) |
| **Kilocode** | Rules file | [kilocode/rules.md](kilocode/rules.md) |
| **Aider** | `--read` flag / `.aider.conf.yml` | [aider/README.md](aider/README.md) |
| **Continue.dev** | `@file` / config.json | [continue/README.md](continue/README.md) |
| **GitHub Copilot** | `#file` / copilot-instructions.md | [github-copilot/README.md](github-copilot/README.md) |
| **Codeium / Windsurf** | Context file | [codeium/README.md](codeium/README.md) |
| **OpenAI Codex** | System prompt / `--read` | [codex/README.md](codex/README.md) |

## Universal approach (works with any tool)

All tools can use reza via the **exported context file**:

```bash
# Generate the context file (run before each session):
reza export

# This creates .reza/CONTEXT.md — a compact markdown file
# that any LLM tool can read as context.
```

Then give it to your tool:
- Aider: `aider --read .reza/CONTEXT.md`
- Cursor: `@.reza/CONTEXT.md` in chat
- ChatGPT: paste the file content
- Any CLI tool: `cat .reza/CONTEXT.md | your-llm-tool`

## The universal workflow

Regardless of which tool you use, the workflow is the same:

```bash
# 1. Check for work from other AI tools:
reza session handoff

# 2. Start your session:
reza session start --llm YOUR_TOOL --task "what you are doing"

# 3. Find files without scanning:
reza query --find "keyword"

# 4. Save progress:
reza session save --id TOOL-XXXXXXXX \
  --summary "what was done" \
  --context "key decisions, next steps, what failed"

# 5. End your session:
reza session end --id TOOL-XXXXXXXX
```

## Adding a new integration

PRs welcome! To add a new tool integration:

1. Create `integrations/TOOLNAME/README.md`
2. Cover: setup, how to inject context, cross-LLM handoff workflow
3. Add the tool to the table in this README

See any existing integration as a template.
