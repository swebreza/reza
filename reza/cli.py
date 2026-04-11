"""Main CLI entry point for reza."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from . import __version__
from .schema import find_db_path, get_connection

console = Console()
err_console = Console(stderr=True)


def _require_db(ctx: click.Context) -> Path:
    """Abort with a helpful message if no DB is found."""
    db = find_db_path()
    if db is None:
        err_console.print(
            "[bold red]No .reza/context.db found.[/bold red]\n"
            "Run [bold]reza init[/bold] in your project root first."
        )
        ctx.exit(1)
    return db


# ─────────────────────────────────────────────
# Root group
# ─────────────────────────────────────────────

@click.group()
@click.version_option(__version__, prog_name="reza")
def main():
    """reza — Universal LLM Context Database.

    Give any AI coding tool instant awareness of your project.
    Index once. Never re-explain again.

    \b
    Quick start:
        reza init        Index the current project
        reza watch       Start real-time file sync
        reza status      See what reza knows
        reza query       Search the context database
        reza session     Manage LLM sessions / handoffs
        reza export      Export context to markdown or JSON
    """


# ─────────────────────────────────────────────
# init
# ─────────────────────────────────────────────

@main.command()
@click.option("--dir", "project_dir", default=".", show_default=True,
              help="Project root directory to index.")
@click.option("--ignore", multiple=True, metavar="PATTERN",
              help="Extra directories to ignore (repeatable).")
@click.option("--no-hooks", is_flag=True, default=False,
              help="Skip git hook installation.")
@click.pass_context
def init(ctx, project_dir, ignore, no_hooks):
    """Initialize reza in a project directory.

    Creates .reza/context.db, indexes all source files, and installs
    a pre-commit git hook for automatic updates.
    """
    from .init_db import initialize_project

    project_dir = str(Path(project_dir).resolve())
    db_path = Path(project_dir) / ".reza" / "context.db"

    if db_path.exists():
        if not click.confirm(
            f".reza/context.db already exists. Re-initialize and re-scan?",
            default=False,
        ):
            console.print("[yellow]Aborted.[/yellow]")
            return

    with console.status("[bold green]Scanning project files…[/bold green]"):
        result = initialize_project(
            project_dir,
            extra_ignore=list(ignore) if ignore else None,
            install_hooks=not no_hooks,
        )

    console.print(Panel(
        f"[bold green]reza initialized![/bold green]\n\n"
        f"  Project : [cyan]{result['meta'].get('name', Path(project_dir).name)}[/cyan]\n"
        f"  Language: [cyan]{result['meta'].get('language', 'Unknown')}[/cyan]\n"
        f"  Framework: [cyan]{result['meta'].get('framework', 'Unknown')}[/cyan]\n"
        f"  Files indexed : [bold]{result['indexed']}[/bold]\n"
        f"  Files skipped : {result['skipped']}\n"
        f"  Database : [dim]{result['db_path']}[/dim]\n"
        f"  Git hook : {'[green]installed[/green]' if result['hook_installed'] else '[yellow]skipped (no .git)[/yellow]'}",
        title="[bold]reza init[/bold]",
        border_style="green",
    ))

    console.print("\nNext steps:")
    console.print("  [bold]reza watch[/bold]   — start real-time file sync (optional)")
    console.print("  [bold]reza status[/bold]  — view project overview")
    console.print("  [bold]reza query[/bold]   — search the context database")


# ─────────────────────────────────────────────
# status
# ─────────────────────────────────────────────

@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx, as_json):
    """Show a quick overview of the indexed project."""
    db = _require_db(ctx)

    with get_connection(db) as conn:
        meta = dict(conn.execute("SELECT key, value FROM project_meta").fetchall())
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        session_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT COUNT(*) FROM changes WHERE changed_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]

        ext_rows = conn.execute(
            "SELECT file_type, COUNT(*) as cnt FROM files GROUP BY file_type ORDER BY cnt DESC LIMIT 8"
        ).fetchall()

    if as_json:
        click.echo(json.dumps({
            "meta": meta,
            "file_count": file_count,
            "active_sessions": session_count,
            "changes_24h": recent,
        }, indent=2))
        return

    console.print(Panel(
        f"  [bold]Project[/bold]   : {meta.get('name', 'unknown')}\n"
        f"  [bold]Language[/bold]  : {meta.get('language', 'unknown')}\n"
        f"  [bold]Framework[/bold] : {meta.get('framework', 'unknown')}\n"
        f"  [bold]Files[/bold]     : {file_count:,}\n"
        f"  [bold]Sessions[/bold]  : {session_count} active\n"
        f"  [bold]Changes[/bold]   : {recent} in last 24h\n"
        f"  [bold]DB[/bold]        : [dim]{db}[/dim]",
        title="[bold]reza status[/bold]",
        border_style="blue",
    ))

    if ext_rows:
        table = Table(title="Top file types", box=box.SIMPLE)
        table.add_column("Extension", style="cyan")
        table.add_column("Count", justify="right")
        for row in ext_rows:
            table.add_row(row["file_type"] or "no-ext", str(row["cnt"]))
        console.print(table)


# ─────────────────────────────────────────────
# query
# ─────────────────────────────────────────────

@main.command()
@click.option("--find", "-f", "find_query", metavar="TEXT",
              help="Search files by path or purpose keyword.")
@click.option("--recent", "-r", is_flag=True,
              help="Show the 30 most recent file changes.")
@click.option("--sessions", "-s", is_flag=True,
              help="Show active and interrupted sessions.")
@click.option("--file", "file_path", metavar="PATH",
              help="Show full info about a specific file.")
@click.option("--json", "as_json", is_flag=True,
              help="Output as JSON.")
@click.pass_context
def query(ctx, find_query, recent, sessions, file_path, as_json):
    """Query the context database.

    \b
    Examples:
        reza query                      # full project overview
        reza query --find auth          # files related to authentication
        reza query --recent             # latest file changes
        reza query --sessions           # active / interrupted sessions
        reza query --file src/api.py    # info about one file
        reza query --json               # machine-readable JSON output
    """
    from .query import (
        get_overview, find_files, get_recent_changes,
        get_sessions_list, get_file_info,
    )

    db = _require_db(ctx)

    if file_path:
        result = get_file_info(db, file_path)
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            if not result:
                err_console.print(f"[red]File not found:[/red] {file_path}")
                ctx.exit(1)
            _print_file_info(result)
    elif find_query:
        results = find_files(db, find_query)
        if as_json:
            click.echo(json.dumps(results, indent=2))
        else:
            _print_find_results(find_query, results)
    elif recent:
        changes = get_recent_changes(db, limit=30)
        if as_json:
            click.echo(json.dumps(changes, indent=2))
        else:
            _print_recent_changes(changes)
    elif sessions:
        sess = get_sessions_list(db)
        if as_json:
            click.echo(json.dumps(sess, indent=2))
        else:
            _print_sessions(sess)
    else:
        overview = get_overview(db)
        if as_json:
            click.echo(json.dumps(overview, indent=2))
        else:
            _print_overview(overview)


def _print_overview(data: dict):
    meta = data.get("meta", {})
    console.print(Panel(
        f"  Name      : [cyan]{meta.get('name', 'unknown')}[/cyan]\n"
        f"  Language  : {meta.get('language', '?')}\n"
        f"  Framework : {meta.get('framework', '?')}\n"
        f"  Files     : {data.get('file_count', 0):,}",
        title="Project Overview", border_style="blue",
    ))
    sessions = data.get("active_sessions", [])
    if sessions:
        console.print(f"\n[bold yellow]Active sessions ({len(sessions)}):[/bold yellow]")
        for s in sessions:
            console.print(f"  [{s['llm_name']}] {s['id']} — {s['working_on'] or '(no task)'}")

    console.print(f"\n[bold]Files by type:[/bold]")
    for ext, count, purposes in data.get("file_tree", []):
        console.print(f"  [cyan].{ext}[/cyan] ({count} files)")
        for p in (purposes or "").split(" | ")[:3]:
            if p.strip():
                console.print(f"    [dim]• {p.strip()}[/dim]")


def _print_find_results(query: str, results: list):
    if not results:
        console.print(f"[yellow]No files found matching '{query}'[/yellow]")
        return
    table = Table(title=f"Search: '{query}'", box=box.SIMPLE)
    table.add_column("Path", style="cyan")
    table.add_column("Type")
    table.add_column("Purpose", max_width=60)
    for r in results:
        table.add_row(r["path"], r["file_type"] or "", r["purpose"] or "")
    console.print(table)


def _print_recent_changes(changes: list):
    if not changes:
        console.print("[yellow]No recent changes recorded.[/yellow]")
        return
    table = Table(title="Recent Changes", box=box.SIMPLE)
    table.add_column("When", style="dim")
    table.add_column("Type")
    table.add_column("File", style="cyan")
    table.add_column("Session", style="dim")
    for c in changes:
        table.add_row(
            (c["changed_at"] or "")[:16],
            c["change_type"] or "",
            c["file_path"],
            c["session_id"] or "",
        )
    console.print(table)


def _print_sessions(sessions: list):
    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return
    table = Table(title="Sessions", box=box.SIMPLE)
    table.add_column("ID", style="cyan")
    table.add_column("LLM")
    table.add_column("Status")
    table.add_column("Working on", max_width=40)
    table.add_column("Started", style="dim")
    for s in sessions:
        status_color = "green" if s["status"] == "active" else "yellow"
        table.add_row(
            s["id"], s["llm_name"],
            f"[{status_color}]{s['status']}[/{status_color}]",
            s["working_on"] or "",
            (s["started_at"] or "")[:16],
        )
    console.print(table)


def _print_file_info(info: dict):
    console.print(Panel(
        f"  Path    : [cyan]{info.get('path')}[/cyan]\n"
        f"  Type    : {info.get('file_type')}\n"
        f"  Lines   : {info.get('line_count'):,}\n"
        f"  Purpose : {info.get('purpose') or '[dim]not detected[/dim]'}\n"
        f"  Notes   : {info.get('llm_notes') or '[dim]none[/dim]'}",
        title="File Info", border_style="blue",
    ))


def _render_handoff_markdown(s: dict) -> str:
    """Render a session handoff dict as a markdown string for pasting into any AI tool."""
    lines = [
        f"# Session Handoff: {s['id']}",
        f"**Tool:** {s['llm_name']}  |  **Started:** {s.get('started_at', 'unknown')}  |  **Status:** {s.get('status', 'unknown')}",
        "",
        "## What Was Being Done",
        s.get("working_on") or "(not set)",
        "",
        "## Summary",
        s.get("summary") or s.get("conversation_context") or "(none saved — use reza session save --summary before ending session)",
        "",
    ]

    turns = s.get("turns", [])
    if turns:
        budget_note = f"~{s['budget_applied']} token budget" if s.get("budget_applied") else "all turns"
        truncated = s.get("turns_truncated", 0)
        truncated_note = f", {truncated} oldest dropped" if truncated else ""
        lines.append(f"## Recent Conversation ({budget_note}{truncated_note})")
        for turn in turns:
            lines.append(f"\n**{turn['role']}:** {turn['content']}")
        lines.append("")
    else:
        lines += ["## Recent Conversation", "(no turns saved)", ""]

    search_hits = s.get("search_results", [])
    if search_hits:
        lines.append(f"## Relevant Context (search: \"{s.get('search_query', '')}\")")
        for hit in search_hits:
            lines.append(f"\n**{hit['role']}** *(turn #{hit['turn_index']})*: {hit['content']}")
        lines.append("")

    files = s.get("files_modified") or ""
    lines.append("## Files Modified")
    file_list = [f.strip() for f in files.split(",") if f.strip()]
    if file_list:
        for f in file_list:
            lines.append(f"- {f}")
    else:
        lines.append("(none recorded)")
    lines.append("")

    lines.append("## Pick Up From Here")
    if turns:
        last_assistant = next(
            (t["content"] for t in reversed(turns) if t["role"] == "assistant"), None
        )
        lines.append(last_assistant or "(see last turn above)")
    else:
        lines.append(s.get("conversation_context") or "(see summary above)")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# session group
# ─────────────────────────────────────────────

@main.group()
def session():
    """Manage LLM sessions and cross-tool handoffs.

    \b
    Examples:
        reza session start --llm claude --task "implement auth"
        reza session save --id claude-abc123 --summary "done with models"
        reza session handoff
        reza session end --id claude-abc123
    """


@session.command("start")
@click.option("--llm", required=True, help="LLM name: claude, codex, cursor, aider, etc.")
@click.option("--task", default="", help="What you are working on.")
@click.option("--tags", default="", help="Comma-separated tags.")
@click.pass_context
def session_start(ctx, llm, task, tags):
    """Start a new LLM session and get a session ID."""
    db = _require_db(ctx)
    from .session import start_session
    session_id = start_session(db, llm, task, tags)
    console.print(f"[bold green]Session started:[/bold green] [cyan]{session_id}[/cyan]")
    console.print(f"  LLM  : {llm}")
    console.print(f"  Task : {task or '(not set)'}")
    console.print(f"\nSave progress with: [bold]reza session save --id {session_id} --summary \"...\"[/bold]")


@session.command("save")
@click.option("--id", "session_id", required=True, help="Session ID to update.")
@click.option("--summary", default="", help="What was accomplished.")
@click.option("--context", default="", help="Context/notes for the next LLM picking this up.")
@click.option("--files", default="", help="Comma-separated list of modified files.")
@click.pass_context
def session_save(ctx, session_id, summary, context, files):
    """Save progress to an active session."""
    db = _require_db(ctx)
    from .session import save_session
    save_session(db, session_id, summary, context, files)
    console.print(f"[green]Session[/green] [cyan]{session_id}[/cyan] [green]updated.[/green]")


@session.command("end")
@click.option("--id", "session_id", required=True, help="Session ID to close.")
@click.option("--summary", default="", help="Final summary before closing.")
@click.pass_context
def session_end(ctx, session_id, summary):
    """Mark a session as completed."""
    db = _require_db(ctx)
    from .session import end_session
    end_session(db, session_id, summary)
    console.print(f"[green]Session[/green] [cyan]{session_id}[/cyan] [green]closed.[/green]")


@session.command("list")
@click.option("--status", default="all", show_default=True,
              type=click.Choice(["all", "active", "interrupted", "completed"]),
              help="Filter by status.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def session_list(ctx, status, as_json):
    """List sessions."""
    db = _require_db(ctx)
    from .session import list_sessions
    sessions = list_sessions(db, status if status != "all" else None)
    if as_json:
        click.echo(json.dumps(sessions, indent=2))
    else:
        _print_sessions(sessions)


# ─── session turns ───────────────────────────────────────────────────────────

@session.group("turns")
def session_turns():
    """Manage conversation turns for a session."""


@session_turns.command("add")
@click.option("--id", "session_id", required=True, help="Session ID to add turns to.")
@click.option("--role", type=click.Choice(["user", "assistant", "system"]), default=None, help="Role for a single turn.")
@click.option("--content", default="", help="Content for a single turn.")
@click.option("--tokens", "token_est", default=0, help="Token estimate (auto-calculated if 0).")
@click.option("--from-file", "from_file", default=None, help="Path to a JSON array file of turns [{role, content}, ...].")
@click.pass_context
def session_turns_add(ctx, session_id, role, content, token_est, from_file):
    """Add one or more turns to a session.

    \b
    Single turn:
        reza session turns add --id claude-abc --role user --content "hello"
    Bulk from JSON file:
        reza session turns add --id claude-abc --from-file turns.json
    """
    db = _require_db(ctx)
    from .turns import add_turn, add_turns_bulk, list_turns

    if from_file:
        with open(from_file, encoding="utf-8") as f:
            turns_data = json.load(f)
        count = add_turns_bulk(db, session_id, turns_data)
        console.print(f"[green]Added {count} turns to[/green] [cyan]{session_id}[/cyan]")
    elif role and content:
        existing = list_turns(db, session_id)
        next_idx = (existing[-1]["turn_index"] + 1) if existing else 0
        add_turn(db, session_id, role, content, token_est=token_est, turn_index=next_idx)
        console.print(f"[green]Turn added to[/green] [cyan]{session_id}[/cyan]")
    else:
        err_console.print("[red]Provide either --role + --content or --from-file[/red]")
        ctx.exit(1)


@session_turns.command("list")
@click.option("--id", "session_id", required=True, help="Session ID.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def session_turns_list(ctx, session_id, as_json):
    """List all conversation turns for a session."""
    db = _require_db(ctx)
    from .turns import list_turns
    turns = list_turns(db, session_id)
    if as_json:
        click.echo(json.dumps(turns, indent=2, default=str))
        return
    if not turns:
        console.print(f"[dim]No turns for session {session_id}[/dim]")
        return
    for t in turns:
        console.print(
            f"[bold]{t['role']}[/bold] [dim](#{t['turn_index']}, ~{t['token_est']} tokens)[/dim]"
        )
        preview = t["content"][:120]
        if len(t["content"]) > 120:
            preview += "..."
        console.print(f"  {preview}")
        console.print()


@session.command("search")
@click.argument("query")
@click.option("--id", "session_id", default=None, help="Restrict search to one session (default: all sessions).")
@click.option("--limit", default=5, show_default=True, help="Max results to return.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def session_search(ctx, query, session_id, limit, as_json):
    """Search conversation history by keyword using full-text search.

    \b
    Examples:
        reza session search "password reset"
        reza session search "auth" --id claude-abc123
        reza session search "database schema" --limit 10
    """
    db = _require_db(ctx)
    from .turns import search_turns
    results = search_turns(db, query, session_id=session_id, limit=limit)
    if as_json:
        click.echo(json.dumps(results, indent=2, default=str))
        return
    if not results:
        console.print(f"[dim]No results for[/dim] [bold]{query!r}[/bold]")
        return
    console.print(f"[bold green]{len(results)} result(s)[/bold green] for [bold]{query!r}[/bold]\n")
    for r in results:
        console.print(
            f"[bold]{r['role']}[/bold] [dim]session={r['session_id']} "
            f"turn=#{r['turn_index']}[/dim]"
        )
        preview = r["content"][:200]
        if len(r["content"]) > 200:
            preview += "..."
        console.print(f"  {preview}")
        console.print()


@session.command("handoff")
@click.option("--id", "session_id", default=None, help="Specific session ID (default: latest interrupted).")
@click.option("--format", "fmt", default="markdown",
              type=click.Choice(["markdown", "json"]),
              show_default=True, help="Output format.")
@click.option("--budget", "budget_tokens", default=None, type=int,
              help="Token budget for turns. Oldest dropped first to fit.")
@click.option("--search", "search_query", default=None,
              help="Include relevant turns matching this query (FTS, in addition to recent turns).")
@click.option("--json", "as_json", is_flag=True, hidden=True,
              help="Deprecated: use --format json instead.")
@click.pass_context
def session_handoff(ctx, session_id, fmt, budget_tokens, search_query, as_json):
    """Show interrupted session context — ready to paste into any AI tool.

    \b
    Examples:
        reza session handoff
        reza session handoff --id claude-abc123
        reza session handoff --format json --budget 4000
        reza session handoff --search "auth pages" --budget 2000
    """
    db = _require_db(ctx)
    from .session import get_handoff_data
    from .turns import search_turns

    if as_json:
        fmt = "json"

    try:
        data = get_handoff_data(db, session_id=session_id, budget_tokens=budget_tokens)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        ctx.exit(1)
        return

    if data is None:
        console.print("[green]No interrupted sessions.[/green] All clear.")
        return

    # Attach search results if --search provided
    if search_query:
        search_hits = search_turns(db, search_query, session_id=data["id"], limit=5)
        data["search_results"] = search_hits
        data["search_query"] = search_query
    else:
        data["search_results"] = []
        data["search_query"] = None

    if fmt == "json":
        click.echo(json.dumps(data, indent=2, default=str))
        return

    click.echo(_render_handoff_markdown(data))


# ─────────────────────────────────────────────
# ingest
# ─────────────────────────────────────────────

@main.command()
@click.argument("file_path")
@click.option("--session-id", default=None, help="Link to an existing session instead of creating one.")
@click.pass_context
def ingest(ctx, file_path, session_id):
    """Ingest a transcript file (.md or .json) as conversation turns.

    Creates a new session automatically (llm_name derived from filename prefix)
    unless --session-id is provided.

    \b
    Examples:
        reza ingest .reza/handoffs/codex-20260410.md
        reza ingest .reza/handoffs/claude-export.json
        reza ingest export.json --session-id claude-abc123
    """
    db = _require_db(ctx)
    from .ingest import ingest_file

    try:
        used_sid = ingest_file(db, file_path, session_id=session_id)
        console.print(f"[green]Ingested[/green] [cyan]{file_path}[/cyan]")
        console.print(f"  Session : [cyan]{used_sid}[/cyan]")
        console.print(
            f"  Search  : [bold]reza session search \"keyword\" --id {used_sid}[/bold]"
        )
        console.print(
            f"  Handoff : [bold]reza session handoff --id {used_sid}[/bold]"
        )
    except FileNotFoundError as e:
        err_console.print(f"[red]File not found:[/red] {e}")
        ctx.exit(1)
    except RuntimeError as e:
        console.print(f"[yellow]Skipped:[/yellow] {e}")
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        ctx.exit(1)


# ─────────────────────────────────────────────
# watch
# ─────────────────────────────────────────────

@main.command()
@click.option("--dir", "project_dir", default=".", show_default=True,
              help="Project root to watch.")
@click.pass_context
def watch(ctx, project_dir):
    """Start real-time file watcher.

    Watches for file changes and updates the context database automatically.
    Run in a separate terminal or background process.

    \b
        reza watch &          # background on Unix
        Start-Process reza watch   # background on Windows
    """
    db = _require_db(ctx)
    try:
        from watchdog.observers import Observer
    except ImportError:
        err_console.print(
            "[red]watchdog is not installed.[/red]\n"
            "Install it with: [bold]pip install watchdog[/bold]"
        )
        ctx.exit(1)

    from .watcher import start_watcher
    project_dir = str(Path(project_dir).resolve())
    console.print(f"[bold green]Watching[/bold green] [cyan]{project_dir}[/cyan]")
    console.print("Press [bold]Ctrl+C[/bold] to stop.\n")
    try:
        start_watcher(project_dir, db)
    except KeyboardInterrupt:
        console.print("\n[yellow]Watcher stopped.[/yellow]")


# ─────────────────────────────────────────────
# export
# ─────────────────────────────────────────────

@main.command()
@click.option("--format", "fmt", default="markdown",
              type=click.Choice(["markdown", "json", "context"]),
              show_default=True,
              help="markdown=human-readable, json=machine-readable, context=compact for LLM prompts.")
@click.option("--output", "-o", default=None, help="Output file (default: .reza/CONTEXT.md or context.json).")
@click.pass_context
def export(ctx, fmt, output):
    """Export context to a file any LLM tool can read.

    \b
    Use 'context' format to generate .reza/CONTEXT.md — a compact
    file that tools like Aider, Cursor, and Copilot can include in context.

    Examples:
        reza export                       # markdown to .reza/CONTEXT.md
        reza export --format json         # JSON to .reza/context.json
        reza export --format context -o CONTEXT.md
    """
    from .export import export_markdown, export_json, export_context

    db = _require_db(ctx)
    db_dir = db.parent

    if fmt == "json":
        out = output or str(db_dir / "context.json")
        export_json(db, out)
    elif fmt == "context":
        out = output or str(db_dir / "CONTEXT.md")
        export_context(db, out)
    else:
        out = output or str(db_dir / "CONTEXT.md")
        export_markdown(db, out)

    console.print(f"[green]Exported[/green] ({fmt}) → [cyan]{out}[/cyan]")


# ─────────────────────────────────────────────
# hooks
# ─────────────────────────────────────────────

@main.command()
@click.option("--uninstall", is_flag=True, help="Remove reza from git hooks.")
@click.option("--dir", "project_dir", default=".", help="Project root.")
@click.pass_context
def hooks(ctx, uninstall, project_dir):
    """Install or remove the pre-commit git hook."""
    from .init_db import install_git_hooks

    project_dir = str(Path(project_dir).resolve())
    hook_path = Path(project_dir) / ".git" / "hooks" / "pre-commit"

    if uninstall:
        if hook_path.exists():
            content = hook_path.read_text()
            lines = [ln for ln in content.splitlines()
                     if "reza" not in ln.lower()]
            hook_path.write_text("\n".join(lines) + "\n")
            console.print("[yellow]reza removed from pre-commit hook.[/yellow]")
        return

    if install_git_hooks(project_dir):
        console.print("[green]Pre-commit hook installed.[/green]")
    else:
        err_console.print("[red]No .git directory found.[/red] Not a git repo?")
        ctx.exit(1)


# ─────────────────────────────────────────────
# update (called by git hook)
# ─────────────────────────────────────────────

@main.command(hidden=True)
@click.option("--staged", is_flag=True, help="Update only staged files (git hook mode).")
@click.option("--file", "file_path", help="Update a single file.")
@click.option("--silent", is_flag=True, help="Suppress all output.")
@click.pass_context
def update(ctx, staged, file_path, silent):
    """Update the context DB for changed files. Called by git hooks."""
    db = find_db_path()
    if db is None:
        return  # Silently exit — no DB found

    from .update import update_staged, update_single_file

    if staged:
        update_staged(db, silent=silent)
    elif file_path:
        update_single_file(db, file_path, silent=silent)


# ─────────────────────────────────────────────
# upgrade
# ─────────────────────────────────────────────

@main.command()
@click.option("--dir", "project_dir", default=".", help="Project root.")
@click.pass_context
def upgrade(ctx, project_dir):
    """Re-scan all files and refresh the context database."""
    db = _require_db(ctx)
    from .init_db import scan_files
    from .schema import init_schema
    import sqlite3 as _sqlite3

    project_dir = str(Path(project_dir).resolve())
    conn = _sqlite3.connect(str(db))
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Apply any new schema tables (idempotent)
    init_schema(conn)

    # Ensure handoffs dir exists
    db.parent.joinpath("handoffs").mkdir(exist_ok=True)

    with console.status("[bold green]Re-scanning files…[/bold green]"):
        indexed, skipped = scan_files(conn, project_dir)
        conn.commit()
    conn.close()
    console.print(f"[green]Upgrade complete.[/green] Indexed {indexed:,} files, skipped {skipped:,}.")


# ─────────────────────────────────────────────
# claim
# ─────────────────────────────────────────────

@main.command()
@click.argument("file_path")
@click.option("--session", "session_id", required=True, help="Session ID claiming this file.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def claim(ctx, file_path, session_id, as_json):
    """Claim a file for exclusive editing by a session.

    Prevents other agents from silently overwriting your work.
    A conflict alert fires immediately if another session writes the file.

    \b
    Examples:
        reza claim src/auth.py --session claude-abc123
        reza claim src/models.py --session cursor-xyz789
    """
    db = _require_db(ctx)
    from .claim import claim_file

    result = claim_file(db, file_path, session_id)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if result["conflict"]:
        console.print(
            f"[bold red]CONFLICT[/bold red] — [cyan]{file_path}[/cyan] is already locked\n"
            f"  Owner  : [yellow]{result['llm']}[/yellow] ({result['owner']})\n"
            f"  Run [bold]reza conflicts[/bold] to review all open conflicts."
        )
        ctx.exit(1)
    else:
        console.print(
            f"[bold green]Claimed[/bold green] [cyan]{file_path}[/cyan]\n"
            f"  Session: {session_id}\n"
            f"  Release with: [bold]reza release {file_path} --session {session_id}[/bold]"
        )


# ─────────────────────────────────────────────
# release
# ─────────────────────────────────────────────

@main.command()
@click.argument("file_path", required=False)
@click.option("--session", "session_id", default=None, help="Release only locks held by this session.")
@click.option("--all-session", "all_session", default=None, metavar="SESSION_ID",
              help="Release ALL locks held by a session.")
@click.pass_context
def release(ctx, file_path, session_id, all_session):
    """Release a file lock (or all locks for a session).

    \b
    Examples:
        reza release src/auth.py --session claude-abc123
        reza release --all-session claude-abc123   # release everything Claude claimed
    """
    db = _require_db(ctx)
    from .claim import release_file, release_session_locks

    if all_session:
        count = release_session_locks(db, all_session)
        console.print(f"[green]Released {count} lock(s)[/green] for session [cyan]{all_session}[/cyan].")
        return

    if not file_path:
        err_console.print("[red]Provide a file path or use --all-session SESSION_ID[/red]")
        ctx.exit(1)

    released = release_file(db, file_path, session_id)
    if released:
        console.print(f"[green]Released[/green] lock on [cyan]{file_path}[/cyan].")
    else:
        console.print(f"[yellow]No lock found[/yellow] for [cyan]{file_path}[/cyan].")


# ─────────────────────────────────────────────
# conflicts
# ─────────────────────────────────────────────

@main.command()
@click.option("--all", "show_all", is_flag=True, help="Show resolved conflicts too.")
@click.option("--resolve", "resolve_id", default=None, type=int,
              help="Resolve a conflict by its ID.")
@click.option("--resolve-file", "resolve_file", default=None, metavar="PATH",
              help="Resolve all open conflicts for a specific file.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def conflicts(ctx, show_all, resolve_id, resolve_file, as_json):
    """View and resolve parallel-agent file conflicts.

    \b
    Examples:
        reza conflicts                      # open conflicts
        reza conflicts --all                # including resolved
        reza conflicts --resolve 3          # mark conflict #3 resolved
        reza conflicts --resolve-file src/auth.py
        reza conflicts --json
    """
    db = _require_db(ctx)
    from .claim import list_conflicts, resolve_conflict, resolve_file_conflicts

    if resolve_id is not None:
        ok = resolve_conflict(db, resolve_id, resolved_by="manual")
        if ok:
            console.print(f"[green]Conflict #{resolve_id} resolved.[/green]")
        else:
            console.print(f"[yellow]Conflict #{resolve_id} not found or already resolved.[/yellow]")
        return

    if resolve_file:
        count = resolve_file_conflicts(db, resolve_file, resolved_by="manual")
        console.print(f"[green]Resolved {count} conflict(s)[/green] for [cyan]{resolve_file}[/cyan].")
        return

    rows = list_conflicts(db, unresolved_only=not show_all)

    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return

    if not rows:
        console.print("[green]No open conflicts.[/green] All agents are working in harmony.")
        return

    table = Table(
        title=f"[bold red]{'All' if show_all else 'Open'} Conflicts[/bold red]",
        box=box.SIMPLE,
    )
    table.add_column("ID", style="dim", width=4)
    table.add_column("File", style="cyan")
    table.add_column("Agent A (lock owner)")
    table.add_column("Agent B (writer)")
    table.add_column("When", style="dim")
    table.add_column("Status")

    for r in rows:
        status = "[green]resolved[/green]" if r["resolved"] else "[red]OPEN[/red]"
        table.add_row(
            str(r["id"]),
            r["file_path"],
            f"{r['llm_a'] or '?'}\n[dim]{r['session_a'] or ''}[/dim]",
            f"{r['llm_b'] or '?'}\n[dim]{r['session_b'] or ''}[/dim]",
            (r["detected_at"] or "")[:16],
            status,
        )
    console.print(table)
    console.print(
        f"\nResolve with: [bold]reza conflicts --resolve ID[/bold]  "
        f"or  [bold]reza conflicts --resolve-file PATH[/bold]"
    )


# ─────────────────────────────────────────────
# locks
# ─────────────────────────────────────────────

@main.command()
@click.option("--session", "session_id", default=None, help="Filter by session ID.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def locks(ctx, session_id, as_json):
    """Show all currently claimed file locks.

    \b
    Examples:
        reza locks                          # all active locks
        reza locks --session claude-abc123  # only Claude's locks
    """
    db = _require_db(ctx)
    from .claim import list_locks

    rows = list_locks(db, session_id=session_id)

    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return

    if not rows:
        console.print("[green]No active file locks.[/green]")
        return

    table = Table(title="Active File Locks", box=box.SIMPLE)
    table.add_column("File", style="cyan")
    table.add_column("LLM")
    table.add_column("Session", style="dim")
    table.add_column("Claimed at", style="dim")

    for r in rows:
        table.add_row(
            r["file_path"],
            r["llm_name"] or "?",
            r["session_id"],
            (r["claimed_at"] or "")[:16],
        )
    console.print(table)
