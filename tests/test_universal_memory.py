"""Universal memory platform tests.

These tests cover the foundation for cross-tool, thread-aware, PC-wide Reza
memory. They intentionally exercise public modules and CLI commands rather than
private SQL details where possible.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from reza.cli import main
from reza.init_db import initialize_project
from reza.ingest._common import ParsedSession, ParsedTurn, upsert_imported_session
from reza.registry import get_registry_path, list_projects, register_project, search_global
from reza.schema import get_connection, init_schema
from reza.session import get_handoff_data, start_session
from reza.threads import create_thread, get_thread_handoff_data, link_session, unlink_session
from reza.turns import add_turns_bulk, search_turns


def _init_project(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text('"""Main entry point."""\n', encoding="utf-8")
    result = initialize_project(str(root), install_hooks=False)
    return Path(result["db_path"])


def _tables(db: Path) -> set[str]:
    with sqlite3.connect(str(db)) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')"
            )
        }


def test_universal_memory_schema_tables_are_initialized(tmp_path: Path) -> None:
    db = tmp_path / "context.db"
    conn = sqlite3.connect(str(db))
    init_schema(conn)
    conn.close()

    assert {
        "threads",
        "conversation_sources",
        "sync_checkpoints",
        "privacy_rules",
    }.issubset(_tables(db))

    with get_connection(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "thread_id" in cols


def test_imported_turns_are_redacted_and_sources_are_recorded(tmp_path: Path) -> None:
    db = tmp_path / "context.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    sid, inserted, _ = upsert_imported_session(
        conn,
        ParsedSession(
            source_tool="cursor",
            source_id="secret-session",
            source_path=str(tmp_path / "cursor.jsonl"),
            llm_name="cursor",
            turns=[ParsedTurn("user", "token=ghp_abcdefghijklmnopqrstuvwxyz123456")],
        ),
    )
    conn.commit()

    assert inserted == 1
    turn = conn.execute(
        "SELECT content FROM conversation_turns WHERE session_id = ?", (sid,)
    ).fetchone()
    source = conn.execute(
        "SELECT adapter_name, source_path FROM conversation_sources WHERE session_id = ?",
        (sid,),
    ).fetchone()
    conn.close()

    assert "ghp_" not in turn["content"]
    assert "token=[REDACTED]" in turn["content"]
    assert source["adapter_name"] == "cursor"
    assert source["source_path"].endswith("cursor.jsonl")


def test_imported_session_gets_thread_for_current_context(tmp_path: Path) -> None:
    db = tmp_path / "context.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    sid, inserted, _ = upsert_imported_session(
        conn,
        ParsedSession(
            source_tool="codex",
            source_id="session-with-thread",
            source_path=str(tmp_path / "rollout.jsonl"),
            llm_name="codex",
            working_on="verify local memory access",
            turns=[ParsedTurn("user", "continue this chat in another coding agent")],
        ),
    )
    conn.commit()
    conn.close()

    assert inserted == 1
    with get_connection(db) as conn:
        row = conn.execute("SELECT thread_id FROM sessions WHERE id = ?", (sid,)).fetchone()
    assert row["thread_id"]

    from reza.context.memory import build_current_context

    packet = build_current_context(db, budget_tokens=1000)
    assert packet["thread"]["id"] == row["thread_id"]
    assert packet["turns"][0]["content"] == "continue this chat in another coding agent"


def test_thread_handoff_and_search_span_multiple_sessions(tmp_path: Path) -> None:
    db = _init_project(tmp_path)
    thread_id = create_thread(db, "JWT auth")
    s1 = start_session(db, "cursor", "JWT auth frontend", thread_id=thread_id)
    s2 = start_session(db, "codex", "JWT auth backend", thread_id=thread_id)
    add_turns_bulk(db, s1, [{"role": "user", "content": "frontend uses refresh middleware"}])
    add_turns_bulk(db, s2, [{"role": "assistant", "content": "backend adds token rotation"}])

    handoff = get_thread_handoff_data(db, thread_id=thread_id, budget_tokens=1000)
    hits = search_turns(db, "token", thread_id=thread_id)

    assert handoff["id"] == thread_id
    assert [s["id"] for s in handoff["sessions"]] == [s1, s2]
    assert [t["session_id"] for t in handoff["turns"]] == [s1, s2]
    assert len(hits) == 1
    assert hits[0]["session_id"] == s2

    unlink_session(db, s2)
    assert get_handoff_data(db, thread_id=thread_id)["id"] == thread_id
    assert link_session(db, s2, thread_id)


def test_thread_cli_link_show_and_handoff(tmp_path: Path, monkeypatch) -> None:
    db = _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    s1 = start_session(db, "cursor", "checkout flow")
    s2 = start_session(db, "codex", "checkout flow followup")
    add_turns_bulk(db, s1, [{"role": "user", "content": "stripe webhook decision"}])
    add_turns_bulk(db, s2, [{"role": "assistant", "content": "checkout page next"}])

    runner = CliRunner()
    created = runner.invoke(main, ["thread", "create", "--title", "Checkout flow", "--json"])
    assert created.exit_code == 0
    thread_id = json.loads(created.output)["id"]

    linked = runner.invoke(main, ["thread", "link", "--session", s1, "--thread", thread_id])
    assert linked.exit_code == 0
    linked = runner.invoke(main, ["thread", "link", "--session", s2, "--thread", thread_id])
    assert linked.exit_code == 0

    shown = runner.invoke(main, ["thread", "show", "--id", thread_id, "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["id"] == thread_id
    assert len(payload["sessions"]) == 2

    handoff = runner.invoke(
        main,
        ["session", "handoff", "--thread", thread_id, "--format", "json", "--search", "webhook"],
    )
    assert handoff.exit_code == 0
    payload = json.loads(handoff.output)
    assert payload["id"] == thread_id
    assert payload["type"] == "thread"
    assert payload["search_results"][0]["session_id"] == s1


def test_install_hooks_writes_adapter_config_and_sync_all_filters_tool(
    tmp_path: Path, monkeypatch
) -> None:
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REZA_HOME", str(tmp_path / "home"))

    runner = CliRunner()
    installed = runner.invoke(main, ["install-hooks", "--tool", "cursor", "--json"])
    assert installed.exit_code == 0
    config_path = tmp_path / ".reza" / "adapters.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["adapters"]["cursor"]["enabled"] is True
    assert "codex" not in config["adapters"]

    listed = runner.invoke(main, ["install-hooks", "--list", "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.output)["adapters"]["cursor"]["enabled"] is True

    synced = runner.invoke(main, ["sync-all", "--tool", "cursor", "--json"])
    assert synced.exit_code == 0
    payload = json.loads(synced.output)
    assert list(payload["tools"]) == ["cursor"]


def test_sync_all_aider_imports_chat_history(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".aider.chat.history.md").write_text(
        "<!-- role: user -->\nremember the billing webhook\n"
        "<!-- role: assistant -->\nuse retry backoff\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["sync-all", "--tool", "aider", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tools"]["aider"]["sources_found"] == 1
    assert payload["tools"]["aider"]["turns_inserted"] == 2

    search = runner.invoke(main, ["session", "search", "billing", "--source", "aider", "--json"])
    assert search.exit_code == 0
    hits = json.loads(search.output)
    assert len(hits) == 1
    assert hits[0]["source_tool"] == "aider"


def test_privacy_audit_reports_redaction_patterns(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["privacy", "audit", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["redaction_enabled"] is True
    assert "assignment_secrets" in payload["built_in_rules"]


def test_context_cli_outputs_budgeted_packet(tmp_path: Path, monkeypatch) -> None:
    db = _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    thread_id = create_thread(db, "Context packet")
    sid = start_session(db, "codex", "Context packet", thread_id=thread_id)
    add_turns_bulk(db, sid, [{"role": "assistant", "content": "decision: keep local sqlite"}])

    runner = CliRunner()
    result = runner.invoke(main, ["context", "current", "--budget", "1000", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["project"]["name"]
    assert payload["thread"]["id"] == thread_id
    assert payload["turns"][0]["content"] == "decision: keep local sqlite"


def test_global_registry_registers_and_searches_projects(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("REZA_HOME", str(home))

    project = tmp_path / "proj"
    db = _init_project(project)
    sid = start_session(db, "codex", "stripe webhook")
    add_turns_bulk(db, sid, [{"role": "user", "content": "stripe webhook retry policy"}])

    register_project(project, db)
    assert get_registry_path() == home / "registry.db"
    assert list_projects()[0]["project_path"] == str(project.resolve())

    results = search_global("stripe")
    assert len(results) == 1
    assert results[0]["project_path"] == str(project.resolve())
    assert "stripe webhook" in results[0]["content"]

    runner = CliRunner()
    status = runner.invoke(main, ["global", "status", "--json"])
    assert status.exit_code == 0
    assert json.loads(status.output)["project_count"] == 1
