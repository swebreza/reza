"""CLI tests for searchable session memory workflows."""

import json
from pathlib import Path

from click.testing import CliRunner

from reza.cli import main
from reza.init_db import initialize_project
from reza.session import start_session
from reza.turns import add_turns_bulk


def _init_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text('"""Main entry point."""\n')
    result = initialize_project(str(tmp_path), install_hooks=False)
    return Path(result["db_path"])


class TestSessionCli:
    def test_handoff_json_includes_summary_recent_turns_and_search_hits(self, tmp_path, monkeypatch):
        _init_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        session_id = start_session(Path(".reza/context.db"), "codex", "continue auth flow")
        add_turns_bulk(Path(".reza/context.db"), session_id, [
            {"role": "user", "content": "we decided to keep the legacy auth middleware"},
            {"role": "assistant", "content": "next step is wiring the login route"},
            {"role": "user", "content": "search for auth middleware notes later"},
        ])

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "session",
                "handoff",
                "--id",
                session_id,
                "--format",
                "json",
                "--budget",
                "1000",
                "--search",
                "middleware",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["id"] == session_id
        assert payload["working_on"] == "continue auth flow"
        assert payload["budget_applied"] == 1000
        assert len(payload["turns"]) == 3
        assert payload["search_query"] == "middleware"
        assert len(payload["search_results"]) >= 1
        assert any("middleware" in hit["content"] for hit in payload["search_results"])

    def test_session_search_json_preserves_raw_content(self, tmp_path, monkeypatch):
        _init_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        session_id = start_session(Path(".reza/context.db"), "claude", "check secrets handling")
        raw_secret = "api_key=sk-live-ABC123"
        add_turns_bulk(Path(".reza/context.db"), session_id, [
            {"role": "user", "content": f"Keep this raw snippet unchanged: {raw_secret}"},
        ])

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["session", "search", "raw snippet", "--id", session_id, "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload) == 1
        assert raw_secret in payload[0]["content"]

    def test_session_save_errors_for_unknown_session_id(self, tmp_path, monkeypatch):
        _init_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["session", "save", "--id", "missing-session", "--summary", "should fail"],
        )

        assert result.exit_code == 1
        assert "Session not found" in result.output

    def test_session_end_errors_for_unknown_session_id(self, tmp_path, monkeypatch):
        _init_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["session", "end", "--id", "missing-session", "--summary", "should fail"],
        )

        assert result.exit_code == 1
        assert "Session not found" in result.output
