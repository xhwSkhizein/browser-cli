from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

import browser_cli.daemon.browser_service as browser_service_module
from browser_cli.drivers.models import DriverHealth
from browser_cli.refs.models import RefData, SemanticSnapshot, SnapshotMetadata
from browser_cli.tabs import TabRegistry


@dataclass(slots=True)
class _FakeHello:
    core: bool = True

    def has_required_capabilities(self) -> bool:
        return self.core

    def has_core_capabilities(self) -> bool:
        return self.core

    def missing_required_capabilities(self) -> list[str]:
        return [] if self.core else ["snapshot"]


class _FakeSession:
    def __init__(self, *, core: bool = True) -> None:
        self.hello = _FakeHello(core=core)


class _FakeExtensionHub:
    def __init__(self) -> None:
        self._session = None
        self._event = asyncio.Event()
        self.started = False

    @property
    def session(self):
        return self._session

    async def ensure_started(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self._session = None
        self._event.set()

    async def wait_for_session(self, timeout_seconds: float):
        _ = timeout_seconds
        return self._session

    async def wait_for_change(self) -> None:
        await self._event.wait()
        self._event.clear()

    def connect(self, *, core: bool = True) -> None:
        self._session = _FakeSession(core=core)
        self._event.set()

    def disconnect(self) -> None:
        self._session = None
        self._event.set()


class _FakeDriverBase:
    def __init__(self, name: str) -> None:
        self.name = name
        self.pages: dict[str, dict[str, str]] = {}
        self.started = False
        self.stopped = False
        self.switched_to: str | None = None

    async def health(self):
        return DriverHealth(name=self.name, available=True, details={})

    async def ensure_started(self) -> None:
        self.started = True

    async def stop(self) -> dict:
        self.stopped = True
        return {"closed_pages": sorted(self.pages)}

    async def new_tab(
        self,
        *,
        page_id: str,
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict:
        _ = wait_until
        _ = timeout_seconds
        url = url or "about:blank"
        self.pages[page_id] = {"url": url, "title": f"{self.name}:{page_id}"}
        return {"page_id": page_id, "url": url, "title": self.pages[page_id]["title"]}

    async def close_tab(self, page_id: str) -> dict:
        page = self.pages.pop(page_id)
        return {"page_id": page_id, "url": page["url"], "title": page["title"], "closed": True}

    async def get_page_summary(self, page_id: str) -> dict:
        page = self.pages[page_id]
        return {"page_id": page_id, "url": page["url"], "title": page["title"]}

    async def switch_tab(self, page_id: str) -> dict:
        self.switched_to = page_id
        return await self.get_page_summary(page_id)


class _FakePlaywrightDriver(_FakeDriverBase):
    def __init__(self, chrome_environment=None, *, headless=None) -> None:
        super().__init__("playwright")
        self.chrome_environment = chrome_environment
        self.headless = headless

    def configure_environment(self, chrome_environment) -> None:
        self.chrome_environment = chrome_environment


class _FakeExtensionDriver(_FakeDriverBase):
    def __init__(self, hub: _FakeExtensionHub) -> None:
        super().__init__("extension")
        self.hub = hub

    async def ensure_started(self) -> None:
        await super().ensure_started()
        if self.hub.session is None:
            raise RuntimeError("extension unavailable")


class _FailingStopExtensionDriver(_FakeExtensionDriver):
    async def stop(self) -> dict:
        raise browser_service_module.OperationFailedError("No tab with id: 685338567.")


@pytest.fixture
def _patched_browser_service(monkeypatch: pytest.MonkeyPatch):
    fake_hub = _FakeExtensionHub()
    monkeypatch.setattr(browser_service_module, "ExtensionHub", lambda: fake_hub)
    monkeypatch.setattr(browser_service_module, "PlaywrightDriver", _FakePlaywrightDriver)
    monkeypatch.setattr(browser_service_module, "ExtensionDriver", _FakeExtensionDriver)
    return fake_hub


def test_browser_service_uses_playwright_by_default(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)

        await service.begin_command("info")
        meta = await service.end_command()

        assert service.active_driver_name == "playwright"
        assert meta["driver"] == "playwright"
        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_prefers_extension_when_available(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)

        await service.begin_command("info")
        meta = await service.end_command()

        assert service.active_driver_name == "extension"
        assert meta["driver"] == "extension"
        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_upgrades_at_safe_point_and_reports_state_reset(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)
        await service.ensure_started()

        page = await service.new_tab(url="https://example.com/start")
        await tabs.add_tab(
            page_id=page["page_id"],
            owner_agent_id="agent-a",
            url=page["url"],
            title=page["title"],
        )
        snapshot = SemanticSnapshot(
            tree="root",
            refs={
                "abcd1234": RefData(
                    ref="abcd1234",
                    role="button",
                    snapshot_id="snap-1",
                    page_id=page["page_id"],
                    captured_url=page["url"],
                )
            },
            metadata=SnapshotMetadata(
                snapshot_id="snap-1",
                page_id=page["page_id"],
                captured_url=page["url"],
                captured_at=1.0,
                interactive=False,
                full_page=True,
            ),
        )
        service._snapshot_registry.store(snapshot)  # noqa: SLF001

        await service.begin_command("html")
        _patched_browser_service.connect()
        await asyncio.sleep(0)
        assert service.active_driver_name == "playwright"

        meta = await service.end_command()

        assert service.active_driver_name == "extension"
        assert meta["driver"] == "extension"
        assert meta["driver_reason"] == "extension-connected"
        assert meta["state_reset"] is True
        assert meta["driver_changed_from"] == "playwright"
        assert meta["driver_changed_to"] == "extension"
        assert service._snapshot_registry.get(page["page_id"]) is None  # noqa: SLF001
        tab = await tabs.get_tab("agent-a", page["page_id"])
        assert tab.last_snapshot_id is None
        assert service._extension.switched_to == page["page_id"]  # noqa: SLF001
        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_downgrades_at_safe_point_and_reports_state_reset(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)
        await service.ensure_started()

        page = await service.new_tab(url="https://example.com/inside-extension")
        await tabs.add_tab(
            page_id=page["page_id"],
            owner_agent_id="agent-a",
            url=page["url"],
            title=page["title"],
        )

        await service.begin_command("html")
        _patched_browser_service.disconnect()
        await asyncio.sleep(0)
        assert service.active_driver_name == "extension"

        meta = await service.end_command()

        assert service.active_driver_name == "extension"
        assert meta["driver"] == "extension"
        status = await service.runtime_status()
        assert status["pending_rebind"] == {
            "target": "playwright",
            "reason": "extension-disconnected-waiting-command",
        }
        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_downgrade_survives_previous_driver_stop_failure(
    _patched_browser_service: _FakeExtensionHub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser_service_module, "ExtensionDriver", _FailingStopExtensionDriver)

    async def _scenario() -> None:
        _patched_browser_service.connect()
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)
        await service.ensure_started()

        page = await service.new_tab(url="https://example.com/rebind")
        await tabs.add_tab(
            page_id=page["page_id"],
            owner_agent_id="agent-a",
            url=page["url"],
            title=page["title"],
        )

        await service.begin_command("html")
        _patched_browser_service.disconnect()
        await asyncio.sleep(0)

        meta = await service.end_command()

        assert service.active_driver_name == "extension"
        assert meta["driver"] == "extension"
        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_disconnect_preserves_extension_on_quick_reconnect(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
        service = browser_service_module.BrowserService(TabRegistry())
        await service.ensure_started()

        _patched_browser_service.disconnect()
        await asyncio.sleep(0)
        assert service.active_driver_name == "extension"

        _patched_browser_service.connect()
        await asyncio.sleep(0)
        assert service.active_driver_name == "extension"

        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_command_forces_playwright_when_extension_is_still_disconnected(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
        service = browser_service_module.BrowserService(TabRegistry())
        await service.ensure_started()
        assert service.active_driver_name == "extension"

        _patched_browser_service.disconnect()
        await asyncio.sleep(0)
        assert service.active_driver_name == "extension"

        await service.begin_command("info")
        assert service.active_driver_name == "playwright"
        meta = await service.end_command()
        assert meta["driver"] == "playwright"

        await service.stop()

    asyncio.run(_scenario())
