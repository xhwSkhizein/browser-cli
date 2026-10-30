"""Agent-facing contracts exercised through the CLI entrypoint."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from unittest.mock import patch

import pytest

from browser_cli import exit_codes
from browser_cli.cli.main import main
from browser_cli.daemon.client import _error_from_payload
from browser_cli.errors import (
    BatchFailedError,
    BusyTabError,
    DaemonNotAvailableError,
    NoActiveTabError,
)
from browser_cli.outputs.files import write_json_artifact
from browser_cli.tabs.registry import TabRegistry
from browser_cli.task_runtime import BrowserCliTaskClient


def response(value):
    return {
        "ok": True,
        "data": {"result": value},
        "meta": {"action": "eval", "agent_id": "export-test", "request_id": "request-1"},
    }


@pytest.mark.parametrize("error", [NoActiveTabError(), BusyTabError(), DaemonNotAvailableError()])
def test_action_errors_are_json_without_an_output_flag(error, monkeypatch, capsys):
    monkeypatch.setenv("X_AGENT_ID", "error-test")
    error.payload["meta"] = {"request_id": "failed-request", "state_reset": True}
    with patch("browser_cli.commands.action.send_command", side_effect=error):
        code = main(["eval", "() => 1"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == error.exit_code != 0
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["error_code"] == error.error_code
    assert payload["error_message"] == error.message
    assert payload["data"] == {}
    assert payload["meta"] == {
        "action": "eval",
        "agent_id": "error-test",
        "request_id": "failed-request",
        "state_reset": True,
    }


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["not-a-command"],
        ["eval"],
        ["eval", "() => 1", "--invalid"],
        ["resize", "invalid", "10"],
    ],
)
def test_parse_errors_are_json_and_never_reach_the_daemon(argv, capsys):
    with patch("browser_cli.commands.action.send_command") as send:
        code = main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == exit_codes.USAGE_ERROR
    assert captured.err == ""
    assert payload["error_code"] == "INVALID_INPUT"
    assert payload["execution_state"] == "not_started"
    send.assert_not_called()


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), RuntimeError("unexpected")])
def test_interrupts_and_unexpected_errors_remain_json(failure, capsys):
    with patch("browser_cli.commands.action.send_command", side_effect=failure):
        code = main(["eval", "() => 1"])
    captured = capsys.readouterr()
    assert code != 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["execution_state"] == "unknown"


def test_python_error_conversion_preserves_the_daemon_envelope():
    original = {
        "ok": False,
        "data": {},
        "error_code": "AGENT_ACTIVE_TAB_BUSY",
        "error_message": "Busy",
        "meta": {"action": "eval", "agent_id": "a", "state_reset": True},
        "execution_state": "not_started",
        "blocked_by": {"command": "cookies", "request_id": "other", "started_at": 123.0},
    }
    error = _error_from_payload(original)
    assert isinstance(error, BusyTabError)
    assert error.payload == original


def test_busy_details_are_from_the_same_agents_tab_and_lock_is_released():
    async def scenario():
        tabs = TabRegistry()
        await tabs.add_tab(page_id="page-a", owner_agent_id="a")
        await tabs.add_tab(page_id="page-b", owner_agent_id="b")
        async with tabs.claim_active_tab(agent_id="a", request_id="first", command="cookies"):
            with pytest.raises(BusyTabError) as caught:
                async with tabs.claim_active_tab(agent_id="a", request_id="second", command="eval"):
                    pytest.fail("Busy action must not start")
            details = caught.value.payload
            assert details["execution_state"] == "not_started"
            assert details["blocked_by"]["command"] == "cookies"
            assert details["blocked_by"]["request_id"] == "first"
            assert details["blocked_by"]["agent_id"] == "a"
            assert details["blocked_by"]["started_at"] > 0
            async with tabs.claim_active_tab(agent_id="b", request_id="third", command="eval"):
                pass
        async with tabs.claim_active_tab(agent_id="a", request_id="fourth", command="eval"):
            pass

    asyncio.run(scenario())


def batch_response(success):
    return {
        "ok": True,
        "data": {
            "success": success,
            "completed": True,
            "completed_count": 2,
            "total_count": 2,
            "failed_indices": [] if success else [1],
            "results": [{"ok": True, "data": {"value": 1}}, {"ok": success}],
            "errors": [] if success else [{"ok": False, "error_code": "INVALID_INPUT"}],
        },
        "meta": {"action": "batch", "agent_id": "a"},
    }


@pytest.mark.parametrize("mode", ["all", "last", "summary"])
@pytest.mark.parametrize("success", [True, False])
def test_batch_exit_code_checks_step_success_without_rewriting_the_response(mode, success, capsys):
    original = batch_response(success)
    with patch("browser_cli.commands.action.send_command", return_value=original):
        code = main(
            [
                "batch",
                "--commands",
                '[{"action":"eval","args":{"code":"() => 1"}}]',
                "--result-mode",
                mode,
                "--continue-on-error",
            ]
        )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert code == (0 if success else exit_codes.TEMPORARY_FAILURE)
    assert json.loads(captured.out) == original


def test_eval_file_export_saves_complete_unicode_value_and_only_prints_metadata(tmp_path, capsys):
    script = tmp_path / "extract data.js"
    script.write_text('() => ({title: "中文", special: "\\n"})', encoding="utf-8")
    value = [
        {"title": '中文 "quotes" \\ \n' * 20_000, "url": "https://example.com/?signed=private"}
    ]
    target = tmp_path / "nested" / "完整结果.json"
    with patch("browser_cli.commands.action.send_command", return_value=response(value)) as send:
        code = main(["eval", "--file", str(script), "--output", str(target), "--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    send.assert_called_once_with(
        "eval", {"code": script.read_text(encoding="utf-8")}, start_if_needed=True
    )
    saved = target.read_bytes()
    assert len(saved) > 200_000
    assert json.loads(saved) == value
    info = json.loads(captured.out)["data"]["artifact"]
    assert info == {
        "path": str(target.resolve()),
        "bytes": len(saved),
        "sha256": hashlib.sha256(saved).hexdigest(),
        "result_type": "array",
        "source": "data.result",
    }
    assert len(captured.out) < 1000
    assert "signed=private" not in captured.out
    assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("action, extra", [("eval", []), ("eval-on", ["ref-1"])])
def test_eval_accepts_stdin_without_forwarding_local_output_options(action, extra, capsys):
    with (
        patch("browser_cli.actions.cli_specs.sys.stdin", io.StringIO("() => '中文'")),
        patch("browser_cli.commands.action.send_command", return_value=response("中文")) as send,
    ):
        assert main([action, *extra, "--file", "-", "--json"]) == 0
    capsys.readouterr()
    expected = {"code": "() => '中文'"}
    if extra:
        expected["ref"] = "ref-1"
    send.assert_called_once_with(action, expected, start_if_needed=True)


@pytest.mark.parametrize("kind", ["missing", "empty", "invalid-utf8", "both-sources"])
def test_invalid_script_source_does_not_start_an_action_or_create_a_file(kind, tmp_path, capsys):
    source = tmp_path / "script.js"
    if kind == "empty":
        source.write_text("  ")
    elif kind == "invalid-utf8":
        source.write_bytes(b"\xff")
    target = tmp_path / "result.json"
    argv = ["eval", "--file", str(source), "--output", str(target)]
    if kind == "both-sources":
        argv.insert(1, "() => 1")
    with patch("browser_cli.commands.action.send_command") as send:
        assert main(argv) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["execution_state"] == "not_started"
    assert not target.exists()
    send.assert_not_called()


def test_output_options_stay_local_for_ordinary_actions(tmp_path, capsys):
    target = tmp_path / "info.json"
    original = {"ok": True, "data": {"title": "test"}, "meta": {"action": "info"}}
    with patch("browser_cli.commands.action.send_command", return_value=original) as send:
        assert main(["info", "--output", str(target), "--json"]) == 0
    send.assert_called_once_with("info", {}, start_if_needed=True)
    assert json.loads(target.read_text()) == original["data"]
    assert json.loads(capsys.readouterr().out)["data"]["artifact"]["source"] == "data"


def test_failed_batch_can_export_partial_results_without_reporting_success(tmp_path, capsys):
    target = tmp_path / "batch.json"
    original = batch_response(False)
    with patch("browser_cli.commands.action.send_command", return_value=original):
        assert main(["batch", "--commands", '[{"action":"info"}]', "--output", str(target)]) == 75
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["success"] is False
    assert payload["data"]["failed_indices"] == [1]
    assert json.loads(target.read_text()) == original["data"]


@pytest.mark.parametrize("failure", [OSError("disk unavailable"), KeyboardInterrupt()])
def test_failed_or_interrupted_atomic_write_preserves_previous_file(failure, tmp_path, capsys):
    target = tmp_path / "result.json"
    target.write_text("previous")
    with (
        patch("browser_cli.commands.action.send_command", return_value=response({"value": 1})),
        patch("browser_cli.outputs.files.os.replace", side_effect=failure),
    ):
        assert main(["eval", "() => 1", "--output", str(target)]) != 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert "artifact" not in payload["data"]
    if isinstance(failure, OSError):
        assert payload["error_code"] == "OUTPUT_WRITE_FAILED"
        assert payload["execution_state"] == "completed"
        assert payload["meta"]["request_id"] == "request-1"
    assert target.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_failed_browser_action_does_not_replace_existing_output(tmp_path, capsys):
    target = tmp_path / "result.json"
    target.write_text("previous")
    with patch("browser_cli.commands.action.send_command", side_effect=BusyTabError()):
        assert main(["eval", "() => 1", "--output", str(target)]) == 75
    assert json.loads(capsys.readouterr().out)["execution_state"] == "not_started"
    assert target.read_text() == "previous"


def test_non_json_artifact_never_replaces_previous_file(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("previous")
    with pytest.raises(Exception, match="Cannot save JSON artifact"):
        write_json_artifact(target, {"value": float("nan")})
    assert target.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_python_batch_raises_with_partial_results_but_invoke_remains_raw():
    original = batch_response(False)
    client = BrowserCliTaskClient()
    with patch("browser_cli.task_runtime.client.send_command", return_value=original):
        with pytest.raises(BatchFailedError) as caught:
            client.batch([{"action": "info"}])
        assert caught.value.payload == original
        assert client.invoke("batch", commands=[{"action": "info"}]) == original["data"]
    with patch("browser_cli.task_runtime.client.send_command", return_value=batch_response(True)):
        assert client.batch([{"action": "info"}])["success"] is True
