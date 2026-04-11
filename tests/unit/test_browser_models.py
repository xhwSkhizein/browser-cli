from __future__ import annotations

from browser_cli.browser.models import BrowserLaunchConfig, default_headless, default_locale


def test_default_headless_false_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("BROWSER_CLI_HEADLESS", raising=False)
    assert default_headless() is False


def test_default_headless_true_for_truthy_env(monkeypatch):
    monkeypatch.setenv("BROWSER_CLI_HEADLESS", "1")
    assert default_headless() is True


def test_launch_config_uses_default_headless(monkeypatch, tmp_path):
    monkeypatch.delenv("BROWSER_CLI_HEADLESS", raising=False)
    config = BrowserLaunchConfig(
        executable_path=None,
        user_data_dir=tmp_path,
    )
    assert config.headless is False


def test_default_locale_prefers_browser_cli_override(monkeypatch):
    monkeypatch.setenv("BROWSER_CLI_LOCALE", "zh_CN.UTF-8")
    assert default_locale() == "zh-CN"


def test_launch_config_uses_default_locale(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_CLI_LOCALE", "fr_FR.UTF-8")
    config = BrowserLaunchConfig(
        executable_path=None,
        user_data_dir=tmp_path,
    )
    assert config.locale == "fr-FR"
