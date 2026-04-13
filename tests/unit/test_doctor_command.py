from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from browser_cli.commands.doctor import collect_doctor_report, run_doctor_command


def test_doctor_json_payload_reports_checks(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.doctor.collect_doctor_report",
        lambda: {
            "overall_status": "warn",
            "checks": [
                {
                    "id": "chrome",
                    "status": "fail",
                    "summary": "Chrome missing",
                    "next": "install Chrome",
                }
            ],
        },
    )
    payload = json.loads(run_doctor_command(Namespace(json=True)))
    assert payload["data"]["overall_status"] == "warn"
    assert payload["data"]["checks"][0]["id"] == "chrome"


def test_doctor_text_output_includes_next_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.doctor.collect_doctor_report",
        lambda: {
            "overall_status": "fail",
            "checks": [
                {
                    "id": "chrome",
                    "status": "fail",
                    "summary": "Stable Google Chrome was not found.",
                    "details": "/usr/bin/google-chrome not present",
                    "next": "install stable Google Chrome and re-run browser-cli doctor",
                }
            ],
        },
    )
    text = run_doctor_command(Namespace(json=False))
    assert "Doctor: fail" in text
    assert "chrome: fail" in text
    assert "Next: install stable Google Chrome and re-run browser-cli doctor" in text


def test_doctor_reports_extension_state_from_runtime_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("browser_cli.commands.doctor.probe_socket", lambda: True)
    monkeypatch.setattr(
        "browser_cli.commands.doctor.read_run_info",
        lambda: {"package_version": "x", "runtime_version": "y"},
    )
    monkeypatch.setattr("browser_cli.commands.doctor.run_info_is_compatible", lambda run_info: True)
    monkeypatch.setattr(
        "browser_cli.commands.doctor.send_command",
        lambda action, args=None, start_if_needed=False: {
            "ok": True,
            "data": {
                "extension": {
                    "connected": True,
                    "capability_complete": False,
                    "missing_capabilities": ["video-stop"],
                }
            },
        },
    )
    report = collect_doctor_report()
    extension_check = next(item for item in report["checks"] if item["id"] == "extension")
    assert extension_check["status"] == "warn"
    assert "video-stop" in extension_check["details"]


def test_doctor_home_and_profile_checks_are_read_only(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("BROWSER_CLI_HOME", str(home))
    monkeypatch.setattr("browser_cli.commands.doctor._daemon_runtime_payload", lambda: None)
    monkeypatch.setattr(
        "browser_cli.commands.doctor._discover_chrome_executable", lambda: Path("/tmp/chrome")
    )
    report = collect_doctor_report()
    home_check = next(item for item in report["checks"] if item["id"] == "home")
    profile_check = next(item for item in report["checks"] if item["id"] == "managed_profile")
    assert home_check["status"] == "fail"
    assert profile_check["status"] == "fail"
    assert not home.exists()


def test_doctor_automation_service_requires_reachability(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    run_dir = home / "run"
    run_dir.mkdir(parents=True)
    monkeypatch.setenv("BROWSER_CLI_HOME", str(home))
    monkeypatch.setattr(
        "browser_cli.commands.doctor.read_automation_service_run_info",
        lambda: {"host": "127.0.0.1", "port": 19824},
    )
    monkeypatch.setattr(
        "browser_cli.commands.doctor._probe_automation_service", lambda run_info: False
    )
    check = collect_doctor_report()
    automation_check = next(item for item in check["checks"] if item["id"] == "automation_service")
    assert automation_check["status"] == "warn"
    assert "not reachable" in automation_check["summary"]
