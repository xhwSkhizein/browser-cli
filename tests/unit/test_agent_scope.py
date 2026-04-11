from __future__ import annotations

import asyncio

from browser_cli.agent_scope import resolve_agent_id
from browser_cli.tabs import TabRegistry


def test_resolve_agent_id_defaults_to_public(monkeypatch) -> None:
    monkeypatch.delenv("X_AGENT_ID", raising=False)
    assert resolve_agent_id() == "public"


def test_resolve_agent_id_uses_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("X_AGENT_ID", "agent-42")
    assert resolve_agent_id() == "agent-42"


def test_tab_registry_enforces_busy_active_tab() -> None:
    async def _run() -> None:
        registry = TabRegistry()
        await registry.add_tab(
            page_id="page_0001", owner_agent_id="agent-a", url="https://example.com"
        )
        async with registry.claim_active_tab(
            agent_id="agent-a", request_id="r1", command="snapshot"
        ):
            try:
                async with registry.claim_active_tab(
                    agent_id="agent-a", request_id="r2", command="html"
                ):
                    raise AssertionError("Expected second claim to fail.")
            except Exception as exc:
                assert exc.__class__.__name__ == "BusyTabError"

    asyncio.run(_run())


def test_tab_registry_isolates_tabs_by_agent() -> None:
    async def _run() -> None:
        registry = TabRegistry()
        await registry.add_tab(page_id="page_0001", owner_agent_id="agent-a")
        await registry.add_tab(page_id="page_0002", owner_agent_id="agent-b")
        tabs_a = await registry.list_tabs("agent-a")
        tabs_b = await registry.list_tabs("agent-b")
        assert [tab.page_id for tab in tabs_a] == ["page_0001"]
        assert [tab.page_id for tab in tabs_b] == ["page_0002"]

    asyncio.run(_run())
