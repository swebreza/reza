# Reza Product Context

Reza is a local-first LLM memory layer for developers who work across multiple coding agents. It records project context, chat turns, handoffs, file activity, and threads into local SQLite databases so agents can retrieve useful context instead of asking the user to repeat it.

Primary users are AI-heavy software builders who move between Codex, Claude Code, Cursor, VS Code, Aider, Continue, Copilot, and related tools during the same project.

Product register: product documentation and developer tooling. Favor speed, trust, traceability, dense scanning, and precise command examples over marketing flourishes.

Core promise:

- Capture local transcript/history files where stable.
- Use drop-zone ingestion where direct capture is unreliable.
- Store memory locally in `.reza/context.db`.
- Route cross-project lookup through `~/.reza/registry.db`.
- Return compact, source-backed context packets to any editor or agent.

Current reality:

- Project memory, transcript turns, FTS search, checkpoints, threads, global registry, and sync adapters exist.
- Cursor, Codex, and Aider have direct sync paths.
- Claude, Continue, Copilot, VS Code chat, Kilocode, and unstable GUI tools use hook or drop-zone flows unless a durable transcript source is available.
- Integrations should call the CLI/API and should not mutate SQLite directly.
