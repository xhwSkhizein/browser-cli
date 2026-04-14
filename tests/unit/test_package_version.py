from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import browser_cli


def test_package_version_prefers_current_distribution_name(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_version(name: str) -> str:
        calls.append(name)
        if name == "browser-control-and-automation-cli":
            return "1.2.3"
        raise PackageNotFoundError(name)

    monkeypatch.setattr(browser_cli, "version", _fake_version)

    assert browser_cli._resolve_version() == "1.2.3"
    assert calls == ["browser-control-and-automation-cli"]


def test_package_version_falls_back_to_legacy_distribution_names(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_version(name: str) -> str:
        calls.append(name)
        if name == "browserctl":
            return "2.0.0"
        raise PackageNotFoundError(name)

    monkeypatch.setattr(browser_cli, "version", _fake_version)

    assert browser_cli._resolve_version() == "2.0.0"
    assert calls == ["browser-control-and-automation-cli", "browserctl"]


def test_package_version_uses_unknown_when_no_distribution_metadata_exists(monkeypatch) -> None:
    def _fake_version(_name: str) -> str:
        raise PackageNotFoundError("missing")

    monkeypatch.setattr(browser_cli, "version", _fake_version)

    assert browser_cli._resolve_version() == "0+unknown"
