# reza Integration — Codeium / Windsurf

Use reza with Codeium (IDE extension) and Windsurf (AI-powered IDE) for instant project context.

## Setup

```bash
pip install reza
cd your-project
reza init
reza export --format context   # generates .reza/CONTEXT.md
```

## Windsurf (Cascade)

### Attach context in Cascade chat

```
@.reza/CONTEXT.md

What is the architecture of this project?
```

### Add to Windsurf rules

Create `.windsurf/rules.md` (or check Windsurf docs for current config path):

```markdown
# Project Context Rules

This project uses reza context database.

Always read `.reza/CONTEXT.md` at the start of each session.
Always run `reza session handoff` to check for interrupted sessions.
Use `reza query --find "keyword"` instead of searching files manually.
```

## Codeium Chat (VS Code / JetBrains)

Paste the context directly into your first message:

```
Context: [paste output of: reza export --format context]

Now, help me with: ...
```

Or reference the exported file if Codeium supports file attachments in your version.

## General Approach

Since Codeium reads your open files, keep `.reza/CONTEXT.md` open in an editor tab:

```bash
reza export        # generate/refresh context
code .reza/CONTEXT.md   # open in VS Code (Codeium will see it)
```

## Cross-tool session tracking

```bash
# Check what other AI tools left off:
reza session handoff

# Track your Codeium session:
reza session start --llm codeium --task "..."
reza session save --id codeium-XXXXXXXX --summary "..." --context "..."
reza session end --id codeium-XXXXXXXX
```

## Real-time updates

Keep the watcher running so the DB stays current as Codeium suggests changes:

```bash
reza watch &
```
