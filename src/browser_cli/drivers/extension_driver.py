"""Real-Chrome driver backed by the Browser CLI extension session."""

from __future__ import annotations

from browser_cli.extension import ExtensionHub

from ._extension.artifact_actions import ExtensionDriverArtifactActionsMixin
from ._extension.dialog_actions import ExtensionDriverDialogActionsMixin
from ._extension.input_actions import ExtensionDriverInputActionsMixin
from ._extension.locator_actions import ExtensionDriverLocatorActionsMixin
from ._extension.observe_actions import ExtensionDriverObserveActionsMixin
from ._extension.page_actions import ExtensionDriverPageActionsMixin
from ._extension.state_actions import ExtensionDriverStateMixin
from .base import BrowserDriver


class ExtensionDriver(
    ExtensionDriverArtifactActionsMixin,
    ExtensionDriverDialogActionsMixin,
    ExtensionDriverInputActionsMixin,
    ExtensionDriverObserveActionsMixin,
    ExtensionDriverLocatorActionsMixin,
    ExtensionDriverPageActionsMixin,
    ExtensionDriverStateMixin,
    BrowserDriver,
):
    name = "extension"

    def __init__(self, hub: ExtensionHub) -> None:
        self._hub = hub
        self._page_to_tab: dict[str, int] = {}
        self._tab_to_page: dict[int, str] = {}
        self._active_page_id: str | None = None
