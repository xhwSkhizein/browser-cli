from __future__ import annotations

from browser_cli.cli.error_hints import next_hint_for_error
from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError


def test_browser_missing_hint_points_to_doctor() -> None:
    hint = next_hint_for_error(BrowserUnavailableError("Stable Google Chrome was not found."))
    assert hint == "install stable Google Chrome and re-run browser-cli doctor"


def test_profile_lock_hint_points_to_status() -> None:
    hint = next_hint_for_error(ProfileUnavailableError("profile appears to be in use"))
    assert hint == "close Browser CLI-owned Chrome windows or inspect browser-cli status"
