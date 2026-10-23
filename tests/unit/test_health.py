from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import patch

from browser_cli import __version__
from browser_cli.commands.doctor import DoctorCheck, collect_doctor_report
from browser_cli.commands.status import run_status_command
from browser_cli.constants import get_app_paths
from browser_cli.daemon.health import inspect_directory
from browser_cli.daemon.transport import DAEMON_RUNTIME_VERSION


def test_directory_probe_detects_actual_write_denial_even_if_access_bits_allow(tmp_path):
    with patch(
        "browser_cli.daemon.health.tempfile.TemporaryFile", side_effect=PermissionError("sandbox")
    ):
        health = inspect_directory(tmp_path)
    assert health["state"] == "unwritable"
    assert health["writable"] is False
    assert health["checked_by"] == "caller"


def test_missing_output_is_reported_createable_without_creating_it(tmp_path):
    output = tmp_path / "nested" / "artifacts"
    health = inspect_directory(output)
    assert health["can_create"] is True
    assert health["state"] == "ready_to_create"
    assert not output.exists()


def test_writable_output_does_not_require_a_writable_parent(tmp_path):
    output = tmp_path / "artifacts"
    output.mkdir()
    with patch(
        "browser_cli.daemon.health.directory_writable", side_effect=lambda path: path == output
    ):
        health = inspect_directory(output)
    assert health["status"] == "pass"


def test_status_and_doctor_distinguish_healthy_runtime_from_unwritable_profile(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path))
    (tmp_path / "default-profile").mkdir()
    (tmp_path / "artifacts").mkdir()
    paths = get_app_paths()
    runtime = {
        "browser_started": True,
        "active_driver": "extension",
        "extension": {"connected": True, "capability_complete": True},
        "presentation": {"overall_state": "healthy"},
    }
    info = {"pid": 123, "runtime_version": DAEMON_RUNTIME_VERSION, "package_version": __version__}
    with (
        patch(
            "browser_cli.daemon.health.directory_writable",
            side_effect=lambda path: path != tmp_path / "default-profile",
        ),
        patch("browser_cli.commands.status.read_run_info", return_value=info),
        patch("browser_cli.commands.status.probe_socket", return_value=True),
        patch("browser_cli.commands.status.send_command", return_value={"data": runtime}),
        patch("browser_cli.commands.doctor._daemon_runtime_payload", return_value=runtime),
        patch(
            "browser_cli.commands.doctor._daemon_check",
            return_value=DoctorCheck("daemon", "pass", "Reachable"),
        ),
        patch(
            "browser_cli.commands.doctor._is_writable_directory",
            side_effect=lambda path: path != tmp_path / "default-profile",
        ),
    ):
        status = json.loads(run_status_command(Namespace(json=True)))["data"]
        doctor = collect_doctor_report()
    assert status["status"] == "healthy"
    assert status["status_scope"] == "runtime"
    for report in (status, doctor):
        assert report["health"]["service"]["status"] == "pass"
        assert report["health"]["extension"]["status"] == "pass"
        assert report["health"]["managed_profile"]["state"] == "unwritable"
        assert report["health"]["output_dir"]["status"] == "pass"
        assert report["health"]["config_dir"]["path"] == str(paths.home)
    assert doctor["overall_status"] == "fail"
    assert doctor["status_scope"] == "environment"
