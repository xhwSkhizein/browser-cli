from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from browser_cli.daemon import client
from browser_cli.errors import DaemonNotAvailableError


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


def test_build_daemon_command_includes_home(tmp_path: Path) -> None:
    command = client._build_daemon_command(tmp_path)  # noqa: SLF001
    assert command[:3] == [client.sys.executable, "-m", "browser_cli.daemon"]
    assert command[3:] == ["--home", str(tmp_path)]


def test_spawn_daemon_timeout_terminates_spawned_process(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    terminated: list[int] = []

    with (
        patch(
            "browser_cli.daemon.client.subprocess.Popen", return_value=_FakeProcess(321)
        ) as popen_mock,
        patch("browser_cli.daemon.client._wait_for_socket", return_value=False),
        patch("browser_cli.daemon.client._terminate_process_tree", side_effect=terminated.append),
        patch("browser_cli.daemon.client.read_run_info", return_value={"pid": 321}),
        pytest.raises(DaemonNotAvailableError),
    ):
        client._spawn_daemon()  # noqa: SLF001

    assert terminated == [321]
    command = popen_mock.call_args.args[0]
    assert command[-2:] == ["--home", str(tmp_path / ".browser-cli-runtime")]


def test_ensure_daemon_running_reaps_stale_runtime_before_spawn(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    call_state = {"probe_count": 0, "spawned": False}
    terminated: list[int] = []

    def fake_probe_socket(*_args, **_kwargs):
        call_state["probe_count"] += 1
        return False

    with (
        patch("browser_cli.daemon.client.probe_socket", side_effect=fake_probe_socket),
        patch("browser_cli.daemon.client.read_run_info", return_value={"pid": 654}),
        patch("browser_cli.daemon.client._pid_exists", return_value=True),
        patch("browser_cli.daemon.client._terminate_process_tree", side_effect=terminated.append),
        patch("browser_cli.daemon.client.remove_run_info") as remove_run_info_mock,
        patch("browser_cli.daemon.client.safe_remove_socket") as safe_remove_socket_mock,
        patch(
            "browser_cli.daemon.client._spawn_daemon",
            side_effect=lambda: call_state.__setitem__("spawned", True),
        ),
    ):
        client.ensure_daemon_running()

    assert terminated == [654]
    assert remove_run_info_mock.called
    assert safe_remove_socket_mock.called
    assert call_state["spawned"] is True


def test_ensure_daemon_running_reaps_incompatible_live_daemon(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    terminated: list[int] = []
    run_info = {"pid": 777, "package_version": "0.0.0", "runtime_version": "old"}
    probe_results = iter([True, False, False, False])

    with (
        patch("browser_cli.daemon.client.probe_socket", side_effect=lambda: next(probe_results)),
        patch("browser_cli.daemon.client.read_run_info", return_value=run_info),
        patch("browser_cli.daemon.client._pid_exists", return_value=True),
        patch("browser_cli.daemon.client._terminate_process_tree", side_effect=terminated.append),
        patch("browser_cli.daemon.client.remove_run_info") as remove_run_info_mock,
        patch("browser_cli.daemon.client.safe_remove_socket") as safe_remove_socket_mock,
        patch("browser_cli.daemon.client._spawn_daemon") as spawn_mock,
    ):
        client.ensure_daemon_running()

    assert terminated == [777]
    assert remove_run_info_mock.called
    assert safe_remove_socket_mock.called
    assert spawn_mock.called


def test_cleanup_runtime_fast_kills_stopped_daemon_without_waiting_for_grace(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))

    with (
        patch("browser_cli.daemon.client.read_run_info", return_value={"pid": 888}),
        patch("browser_cli.daemon.client._pid_exists", return_value=True),
        patch("browser_cli.daemon.client.probe_socket", return_value=False),
        patch("browser_cli.daemon.client._signal_process_tree") as signal_mock,
        patch("browser_cli.daemon.client._wait_for_pid_exit", return_value=True) as wait_mock,
        patch("browser_cli.daemon.client._terminate_process_tree") as terminate_mock,
        patch("browser_cli.daemon.client.remove_run_info"),
        patch("browser_cli.daemon.client.safe_remove_socket"),
    ):
        had_runtime = client.cleanup_runtime(fast_kill=True)

    assert had_runtime is True
    signal_mock.assert_called_once_with(888, client.signal.SIGKILL)
    wait_mock.assert_called_once_with(888, timeout_seconds=1.0)
    terminate_mock.assert_not_called()
