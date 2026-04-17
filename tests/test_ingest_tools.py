"""Tests for cross-tool ingestion (Cursor transcripts, Codex rollouts)
and the session inspection API that powers ``reza session show/load/graph``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from reza.ingest import codex as codex_ingest
from reza.ingest import cursor as cursor_ingest
from reza.ingest._common import ParsedSession, ParsedTurn, upsert_imported_session
from reza.schema import init_schema
from reza.sessions_view import (
    get_session_detail,
    get_session_graph_scope,
    get_session_turns,
    list_sessions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    """Fresh .reza/context.db with schema initialized."""
    db = tmp_path / "context.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    conn.close()
    return db


def _open(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Cursor transcript parser
# ---------------------------------------------------------------------------


def _write_cursor_transcript(path: Path, turns: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t) + "\n")


def test_cursor_parser_extracts_text_and_paths(tmp_path: Path) -> None:
    """Cursor parser should pull text, normalise tool_use, harvest paths."""
    transcript = tmp_path / "7c49f9bf.jsonl"
    _write_cursor_transcript(transcript, [
        {"role": "user", "message": {"content": [
            {"type": "text", "text": "please read src/main.py"},
        ]}},
        {"role": "assistant", "message": {"content": [
            {"type": "text", "text": "On it."},
            {"type": "tool_use", "name": "Read",
             "input": {"path": "src/main.py"}},
            {"type": "tool_use", "name": "StrReplace",
             "input": {"file_path": "src/utils.py"}},
        ]}},
    ])

    parsed = cursor_ingest._parse_transcript(transcript)

    assert parsed is not None
    assert parsed.source_tool == "cursor"
    assert parsed.source_id == "7c49f9bf"
    assert len(parsed.turns) == 2
    assert parsed.turns[0].role == "user"
    assert "please read" in parsed.turns[0].content
    assert "[tool_use: Read]" in parsed.turns[1].content
    assert set(parsed.files_touched) == {"src/main.py", "src/utils.py"}
    assert parsed.working_on.startswith("please read")


def test_cursor_parser_skips_empty_content(tmp_path: Path) -> None:
    """Blocks with no text should not generate empty turns."""
    t = tmp_path / "x.jsonl"
    _write_cursor_transcript(t, [
        {"role": "user", "message": {"content": []}},
        {"role": "assistant", "message": {"content": [{"type": "image"}]}},
    ])
    assert cursor_ingest._parse_transcript(t) is None


def test_cursor_discover_matches_slugged_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """discover_cursor_transcripts should find the Cursor project folder
    whose slug equals the workspace path's slug."""
    fake_cursor_home = tmp_path / ".cursor" / "projects"
    workspace = tmp_path / "myproj"
    workspace.mkdir()

    slug = cursor_ingest._slug_for(workspace)
    proj_dir = fake_cursor_home / slug
    at_dir = proj_dir / "agent-transcripts"
    at_dir.mkdir(parents=True)
    jsonl = at_dir / "abc.jsonl"
    _write_cursor_transcript(jsonl, [
        {"role": "user", "message": {"content": "hi"}},
    ])

    monkeypatch.setattr(cursor_ingest, "_CURSOR_PROJECTS", fake_cursor_home)

    found = cursor_ingest.discover_cursor_transcripts(workspace)
    assert found == [jsonl]


def test_cursor_sync_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, empty_db: Path
) -> None:
    """Re-running sync_cursor_project should not duplicate turns."""
    fake_cursor_home = tmp_path / ".cursor" / "projects"
    workspace = tmp_path / "proj"
    workspace.mkdir()
    slug = cursor_ingest._slug_for(workspace)
    jsonl = fake_cursor_home / slug / "agent-transcripts" / "abc.jsonl"
    _write_cursor_transcript(jsonl, [
        {"role": "user", "message": {"content": [{"type": "text", "text": "one"}]}},
        {"role": "assistant", "message": {"content": [{"type": "text", "text": "two"}]}},
    ])
    monkeypatch.setattr(cursor_ingest, "_CURSOR_PROJECTS", fake_cursor_home)

    conn = _open(empty_db)
    try:
        r1 = cursor_ingest.sync_cursor_project(conn, workspace)
        r2 = cursor_ingest.sync_cursor_project(conn, workspace)
    finally:
        conn.close()

    assert r1["transcripts_found"] == 1
    assert r1["sessions_imported"] == 1
    assert r1["turns_inserted"] == 2
    # Second run: nothing new.
    assert r2["sessions_imported"] == 0
    assert r2["sessions_updated"] == 1
    assert r2["turns_inserted"] == 0

    conn = _open(empty_db)
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM conversation_turns"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert total == 2


# ---------------------------------------------------------------------------
# Codex rollout parser
# ---------------------------------------------------------------------------


def _write_codex_rollout(path: Path, meta: dict, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "session_meta", "payload": meta}) + "\n")
        for it in items:
            f.write(json.dumps(it) + "\n")


def test_codex_parser_extracts_turns_and_cwd(tmp_path: Path) -> None:
    """Codex parser should capture meta, role messages, and tool-call paths."""
    roll = tmp_path / "roll.jsonl"
    cwd = tmp_path / "myproj"
    cwd.mkdir()
    target = cwd / "app" / "main.py"
    target.parent.mkdir()
    target.write_text("# ok")

    _write_codex_rollout(
        roll,
        {"id": "019b-abc", "timestamp": "2026-04-10T03:33:37Z",
         "cwd": str(cwd), "cli_version": "0.119.0"},
        [
            {"type": "response_item", "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "fix main.py please"}],
            }},
            {"type": "response_item", "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "doing it"}],
            }},
            {"type": "response_item", "payload": {
                "type": "function_call",
                "name": "shell_command",
                "arguments": json.dumps({
                    "command": f'Get-Content "{target}"',
                    "workdir": str(cwd),
                }),
            }},
        ],
    )

    parsed = codex_ingest._parse_rollout(roll)
    assert parsed is not None
    assert parsed.source_tool == "codex"
    assert parsed.source_id == "019b-abc"
    assert parsed.llm_name == "codex-0.119.0"
    assert parsed.working_on.startswith("fix main.py")
    assert len(parsed.turns) == 2
    # Path harvested from function_call arguments and resolved inside project cwd.
    assert any("main.py" in f for f in parsed.files_touched)


def test_codex_parser_skips_system_preamble(tmp_path: Path) -> None:
    """The IDE's system preamble shouldn't end up as ``working_on``."""
    roll = tmp_path / "roll.jsonl"
    _write_codex_rollout(
        roll,
        {"id": "sys-1", "cwd": str(tmp_path)},
        [
            {"type": "response_item", "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text",
                             "text": "<environment_context><cwd>x</cwd></environment_context>"}],
            }},
            {"type": "response_item", "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "actually fix the bug"}],
            }},
        ],
    )
    parsed = codex_ingest._parse_rollout(roll)
    assert parsed is not None
    assert parsed.working_on.startswith("actually fix the bug")


def test_codex_discover_filters_by_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """discover_codex_rollouts should match only rollouts whose cwd == target."""
    fake_codex = tmp_path / ".codex" / "sessions"
    target = tmp_path / "target"
    other = tmp_path / "other"
    target.mkdir()
    other.mkdir()

    r1 = fake_codex / "2026" / "04" / "17" / "rollout-a.jsonl"
    r2 = fake_codex / "2026" / "04" / "17" / "rollout-b.jsonl"
    _write_codex_rollout(r1, {"id": "A", "cwd": str(target)}, [])
    _write_codex_rollout(r2, {"id": "B", "cwd": str(other)},  [])

    monkeypatch.setattr(codex_ingest, "_CODEX_SESSIONS", fake_codex)

    assert codex_ingest.discover_codex_rollouts(target) == [r1]
    assert codex_ingest.discover_codex_rollouts(other) == [r2]
    # None filter -> return all
    assert set(codex_ingest.discover_codex_rollouts(None)) == {r1, r2}


# ---------------------------------------------------------------------------
# sessions_view
# ---------------------------------------------------------------------------


def test_upsert_imported_session_is_idempotent(empty_db: Path) -> None:
    """Calling upsert twice should append no new turns."""
    conn = _open(empty_db)
    try:
        ps = ParsedSession(
            source_tool="cursor",
            source_id="abc",
            source_path="/tmp/abc.jsonl",
            llm_name="cursor",
            turns=[
                ParsedTurn("user", "hi"),
                ParsedTurn("assistant", "hello back"),
            ],
            files_touched=["src/x.py"],
        )
        sid1, inserted1, _ = upsert_imported_session(conn, ps)
        sid2, inserted2, _ = upsert_imported_session(conn, ps)
        conn.commit()

        assert sid1 == sid2
        assert inserted1 == 2
        assert inserted2 == 0

        detail = get_session_detail(conn, sid1)
        assert detail is not None
        assert detail.source_tool == "cursor"
        assert detail.turn_count == 2
        assert detail.files_touched == ["src/x.py"]
    finally:
        conn.close()


def test_list_sessions_filters_by_source(empty_db: Path) -> None:
    conn = _open(empty_db)
    try:
        for i, tool in enumerate(["cursor", "codex", "cursor"]):
            upsert_imported_session(conn, ParsedSession(
                source_tool=tool,
                source_id=f"{tool}-{i}",
                source_path=f"/tmp/{tool}-{i}.jsonl",
                llm_name=tool,
                turns=[ParsedTurn("user", f"q{i}")],
            ))
        conn.commit()

        all_rows = list_sessions(conn)
        assert len(all_rows) == 3

        cursors = list_sessions(conn, source="cursor")
        assert len(cursors) == 2
        assert all(r.source_tool == "cursor" for r in cursors)

        codexes = list_sessions(conn, source="codex")
        assert len(codexes) == 1
        assert codexes[0].source_tool == "codex"
    finally:
        conn.close()


def test_get_session_turns_returns_in_order(empty_db: Path) -> None:
    conn = _open(empty_db)
    try:
        ps = ParsedSession(
            source_tool="cursor", source_id="seq", source_path="/t/s.jsonl",
            llm_name="cursor",
            turns=[
                ParsedTurn("user", "first"),
                ParsedTurn("assistant", "second"),
                ParsedTurn("user", "third"),
            ],
        )
        sid, _, _ = upsert_imported_session(conn, ps)
        conn.commit()

        rows = get_session_turns(conn, sid)
        assert [r["content"] for r in rows] == ["first", "second", "third"]
        assert [r["turn_index"] for r in rows] == [0, 1, 2]
    finally:
        conn.close()


def test_session_graph_scope_requires_code_nodes(empty_db: Path) -> None:
    """Without a built graph the scope should be empty but not crash."""
    conn = _open(empty_db)
    try:
        ps = ParsedSession(
            source_tool="cursor", source_id="empty", source_path="/t/e.jsonl",
            llm_name="cursor",
            turns=[ParsedTurn("user", "x")],
            files_touched=["no/such/file.py"],
        )
        sid, _, _ = upsert_imported_session(conn, ps)
        conn.commit()

        scope = get_session_graph_scope(conn, sid)
        assert scope["files"] == ["no/such/file.py"]
        assert scope["node_ids"] == []
        assert scope["edges"] == []
    finally:
        conn.close()


def test_missing_session_returns_none(empty_db: Path) -> None:
    conn = _open(empty_db)
    try:
        assert get_session_detail(conn, "does-not-exist") is None
        scope = get_session_graph_scope(conn, "does-not-exist")
        assert scope == {"files": [], "node_ids": [], "edges": []}
    finally:
        conn.close()
