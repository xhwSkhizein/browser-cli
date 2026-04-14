# Browser CLI Daemon Parameter Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make daemon numeric argument parsing return stable `INVALID_INPUT` errors instead of leaking `INTERNAL_ERROR` for malformed user input.

**Architecture:** Keep all request parsing changes inside `src/browser_cli/daemon/app.py`, where daemon handlers normalize `request.args` before calling `browser_service`. Add shared numeric parsing helpers on `BrowserDaemonApp`, migrate every direct `int(...)` and `float(...)` conversion in the handler layer to those helpers, and lock the behavior with request-level regression tests that execute `BrowserDaemonApp.execute()`.

**Tech Stack:** Python 3.10, pytest, Browser CLI daemon request/response models, `InvalidInputError`

---

## File Map

- Create: `tests/unit/test_daemon_app_validation.py`
  Responsibility: request-level regression tests for malformed numeric daemon input.
- Modify: `src/browser_cli/daemon/app.py`
  Responsibility: add shared numeric parsing helpers and route all direct numeric request parsing through them.
- Modify: `docs/superpowers/plans/2026-04-14-daemon-parameter-validation-implementation-plan.md`
  Responsibility: update checkbox state during execution if this plan is used as the working log.

## Task 1: Add Request-Level Regression Tests For Numeric Input Failures

**Files:**
- Create: `tests/unit/test_daemon_app_validation.py`
- Test: `tests/unit/test_daemon_app_validation.py`

- [ ] **Step 1: Write the failing regression tests**

Create `tests/unit/test_daemon_app_validation.py`:

```python
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from browser_cli import error_codes
from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.models import DaemonRequest


class _FakeTabs:
    @asynccontextmanager
    async def claim_active_tab(self, **_kwargs):
        yield SimpleNamespace(page_id="page_0001")

    async def update_tab(self, *_args, **_kwargs) -> None:
        return None


class _FakeBrowserService:
    async def begin_command(self, _action: str) -> None:
        return None

    async def end_command(self) -> dict[str, str]:
        return {"driver": "playwright"}

    @property
    def active_driver_name(self) -> str:
        return "playwright"

    @property
    def chrome_environment(self):
        return None

    async def get_page_summary(self, _page_id: str) -> dict[str, str]:
        return {"url": "https://example.com", "title": "Example"}

    async def mouse_click(
        self,
        page_id: str,
        *,
        x: int,
        y: int,
        button: str,
        count: int,
    ) -> dict[str, object]:
        return {"page_id": page_id, "x": x, "y": y, "button": button, "count": count}

    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, object]:
        return {"page_id": page_id, "width": width, "height": height}

    async def wait_for_network_idle(
        self, page_id: str, *, timeout_seconds: float = 30.0
    ) -> dict[str, object]:
        return {"page_id": page_id, "timeout_seconds": timeout_seconds}


class _FakeState:
    def __init__(self) -> None:
        self.tabs = _FakeTabs()
        self.browser_service = _FakeBrowserService()


def _execute(request: DaemonRequest) -> dict[str, object]:
    async def _scenario() -> dict[str, object]:
        app = BrowserDaemonApp(state=_FakeState())  # type: ignore[arg-type]
        response = await app.execute(request)
        return response.to_dict()

    return asyncio.run(_scenario())


def test_mouse_click_missing_x_returns_invalid_input() -> None:
    payload = _execute(
        DaemonRequest(
            action="mouse-click",
            args={"y": 10},
            agent_id="agent-a",
            request_id="req-1",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "x is required."


def test_mouse_drag_invalid_coordinate_returns_invalid_input() -> None:
    payload = _execute(
        DaemonRequest(
            action="mouse-drag",
            args={"x1": 1, "y1": 2, "x2": "bad", "y2": 4},
            agent_id="agent-a",
            request_id="req-2",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "x2 must be an integer."


def test_wait_network_invalid_timeout_returns_invalid_input() -> None:
    payload = _execute(
        DaemonRequest(
            action="wait-network",
            args={"timeout": "slow"},
            agent_id="agent-a",
            request_id="req-3",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "timeout must be a number."


def test_resize_non_positive_values_keep_handler_level_constraint() -> None:
    payload = _execute(
        DaemonRequest(
            action="resize",
            args={"width": 0, "height": 100},
            agent_id="agent-a",
            request_id="req-4",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "width and height must be positive integers."
```

- [ ] **Step 2: Run the regression tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/test_daemon_app_validation.py -v
```

Expected: FAIL because `mouse-click`, `mouse-drag`, and `wait-network` still leak raw numeric conversion failures instead of returning `InvalidInputError`.

- [ ] **Step 3: Commit the failing-test scaffold**

```bash
git add tests/unit/test_daemon_app_validation.py
git commit -m "test: add daemon parameter validation regressions"
```

## Task 2: Add Shared Numeric Parsing Helpers And Migrate All Direct Conversions

**Files:**
- Modify: `src/browser_cli/daemon/app.py`
- Test: `tests/unit/test_daemon_app_validation.py`

- [ ] **Step 1: Add shared numeric parsing helpers to `BrowserDaemonApp`**

Insert these helpers below `_optional_str()` in `src/browser_cli/daemon/app.py`:

```python
    @classmethod
    def _require_int(cls, args: dict[str, Any], key: str) -> int:
        raw = args.get(key)
        if raw is None or str(raw).strip() == "":
            raise InvalidInputError(f"{key} is required.")
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError(f"{key} must be an integer.") from exc

    @classmethod
    def _optional_int(cls, args: dict[str, Any], key: str) -> int | None:
        raw = args.get(key)
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError(f"{key} must be an integer.") from exc

    @classmethod
    def _require_float(cls, args: dict[str, Any], key: str) -> float:
        raw = args.get(key)
        if raw is None or str(raw).strip() == "":
            raise InvalidInputError(f"{key} is required.")
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError(f"{key} must be a number.") from exc

    @classmethod
    def _optional_float(cls, args: dict[str, Any], key: str) -> float | None:
        raw = args.get(key)
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError(f"{key} must be a number.") from exc
```

- [ ] **Step 2: Replace all direct numeric request parsing in handlers**

Update these handler fragments in `src/browser_cli/daemon/app.py`:

```python
    async def _handle_scroll(self, request: DaemonRequest) -> dict[str, Any]:
        dx = self._optional_int(request.args, "dx") or 0
        dy = self._optional_int(request.args, "dy") or 700
        return await self._run_active_page_action(
            request, lambda page_id: self._state.browser_service.wheel(page_id, dx=dx, dy=dy)
        )
```

```python
    async def _handle_mouse_click(self, request: DaemonRequest) -> dict[str, Any]:
        x = self._require_int(request.args, "x")
        y = self._require_int(request.args, "y")
        count = self._optional_int(request.args, "count") or 1
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_click(
                page_id,
                x=x,
                y=y,
                button=str(request.args.get("button") or "left"),
                count=count,
            ),
        )
```

```python
    async def _handle_mouse_move(self, request: DaemonRequest) -> dict[str, Any]:
        x = self._require_int(request.args, "x")
        y = self._require_int(request.args, "y")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_move(page_id, x=x, y=y),
        )
```

```python
    async def _handle_mouse_drag(self, request: DaemonRequest) -> dict[str, Any]:
        x1 = self._require_int(request.args, "x1")
        y1 = self._require_int(request.args, "y1")
        x2 = self._require_int(request.args, "x2")
        y2 = self._require_int(request.args, "y2")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_drag(
                page_id, x1=x1, y1=y1, x2=x2, y2=y2
            ),
        )
```

```python
    async def _handle_wait(self, request: DaemonRequest) -> dict[str, Any]:
        seconds = self._optional_float(request.args, "seconds")
        text = request.args.get("text")
        gone = bool(request.args.get("gone"))
        exact = bool(request.args.get("exact"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.wait(
                page_id,
                seconds=seconds,
                text=str(text) if text else None,
                gone=gone,
                exact=exact,
            ),
        )
```

```python
    async def _handle_wait_network(self, request: DaemonRequest) -> dict[str, Any]:
        timeout_seconds = self._optional_float(request.args, "timeout") or 30.0
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.wait_for_network_idle(
                page_id, timeout_seconds=timeout_seconds
            ),
        )
```

```python
    async def _handle_network_wait(self, request: DaemonRequest) -> dict[str, Any]:
        filters = self._network_filters_from_request(request.args)
        timeout_seconds = self._optional_float(request.args, "timeout_seconds") or 30.0
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.wait_for_network_record(
                page_id,
                **filters,
                timeout_seconds=timeout_seconds,
            ),
        )
```

```python
    async def _handle_verify_text(self, request: DaemonRequest) -> dict[str, Any]:
        text = self._require_str(request.args, "text")
        exact = bool(request.args.get("exact"))
        timeout = self._optional_float(request.args, "timeout") or 5.0
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_text(
                page_id, text=text, exact=exact, timeout_seconds=timeout
            ),
        )
```

```python
    async def _handle_verify_visible(self, request: DaemonRequest) -> dict[str, Any]:
        role = self._require_str(request.args, "role")
        name = self._require_str(request.args, "name")
        timeout = self._optional_float(request.args, "timeout") or 5.0
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_visible(
                page_id, role=role, name=name, timeout_seconds=timeout
            ),
        )
```

```python
    async def _handle_video_start(self, request: DaemonRequest) -> dict[str, Any]:
        width = self._optional_int(request.args, "width")
        height = self._optional_int(request.args, "height")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.start_video(
                page_id,
                width=width,
                height=height,
            ),
        )
```

```python
    @classmethod
    def _network_filters_from_request(cls, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "url_contains": cls._optional_str(args, "url_contains"),
            "url_regex": cls._optional_str(args, "url_regex"),
            "method": cls._optional_str(args, "method"),
            "status": cls._optional_int(args, "status"),
            "resource_type": cls._optional_str(args, "resource_type"),
            "mime_contains": cls._optional_str(args, "mime_contains"),
            "include_static": bool(args.get("include_static")),
        }
```

Also update `resize` and `cookie-set`:

```python
    async def _handle_resize(self, request: DaemonRequest) -> dict[str, Any]:
        width = self._require_int(request.args, "width")
        height = self._require_int(request.args, "height")
        if width <= 0 or height <= 0:
            raise InvalidInputError("width and height must be positive integers.")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.resize(page_id, width=width, height=height),
        )
```

```python
                expires=self._optional_float(request.args, "expires"),
```

- [ ] **Step 3: Run the regression tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/test_daemon_app_validation.py -v
```

Expected: PASS

- [ ] **Step 4: Add one focused success-path test for parsed values**

Append to `tests/unit/test_daemon_app_validation.py`:

```python
def test_mouse_click_successfully_parses_integer_fields() -> None:
    payload = _execute(
        DaemonRequest(
            action="mouse-click",
            args={"x": "12", "y": "14", "count": "2"},
            agent_id="agent-a",
            request_id="req-5",
        )
    )

    assert payload["ok"] is True
    assert payload["data"] == {
        "page_id": "page_0001",
        "x": 12,
        "y": 14,
        "button": "left",
        "count": 2,
    }
```

Run:

```bash
uv run pytest tests/unit/test_daemon_app_validation.py::test_mouse_click_successfully_parses_integer_fields -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/browser_cli/daemon/app.py tests/unit/test_daemon_app_validation.py
git commit -m "fix: normalize daemon numeric parameter validation"
```

## Task 3: Run Focused And Full Validation

**Files:**
- Modify: `docs/superpowers/plans/2026-04-14-daemon-parameter-validation-implementation-plan.md`
- Test: `tests/unit/test_daemon_app_validation.py`

- [ ] **Step 1: Run the focused daemon validation suite**

Run:

```bash
uv run pytest tests/unit/test_daemon_app_validation.py -v
```

Expected: PASS

- [ ] **Step 2: Run repository validation**

Run:

```bash
./scripts/lint.sh
./scripts/test.sh
./scripts/guard.sh
```

Expected: all three scripts exit `0`.

- [ ] **Step 3: Update this plan file to mark the completed steps**

Update the completed steps in this file:

```markdown
- [x] **Step 1: Run the focused daemon validation suite**
- [x] **Step 2: Run repository validation**
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-14-daemon-parameter-validation-implementation-plan.md
git commit -m "docs: mark daemon parameter validation plan complete"
```

## Self-Review

Spec coverage:

- shared helper methods in `BrowserDaemonApp`: covered by Task 2
- handler-layer-only scope: covered by Task 2 file scope
- malformed numeric values return `INVALID_INPUT`: covered by Task 1 tests and Task 2 implementation
- preserve handler-level range validation: covered by the `resize` regression in Task 1 and Task 2
- regression protection through `BrowserDaemonApp.execute()`: covered by Task 1

Placeholder scan:

- no `TODO`, `TBD`, or deferred “handle later” markers remain
- every code-edit step includes concrete code blocks
- every verification step includes an exact command and expected result

Type consistency:

- helper names `_require_int`, `_optional_int`, `_require_float`, `_optional_float` are defined once and used consistently
- request/response assertions use the existing `DaemonRequest` and `DaemonResponse.to_dict()` flow
