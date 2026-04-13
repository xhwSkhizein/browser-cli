# Browser CLI Pip User UX Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `pip` user UX roadmap in phased, independently releasable batches that improve first-day success, first task delivery, and post-publish observability.

**Architecture:** Keep the existing CLI/daemon/task-runtime split intact. Add small, user-facing discovery commands (`doctor`, `paths`), expand the `task` and `automation` surfaces without reintroducing `workflow`, and keep automation/service state on existing persistence and HTTP service layers rather than inventing a second runtime. Where possible, prefer CLI-only composition over new backend complexity; add service/API support only where inspectability truly needs it.

**Tech Stack:** Python 3.10+, argparse, dataclasses, pathlib, sqlite3, existing Browser CLI daemon/service clients, pytest, repository guards

---

## Scope Note

The approved spec spans multiple subsystems. This plan keeps one roadmap-level
document, but decomposes implementation into seven shippable task groups:

1. `doctor`
2. `paths`
3. error hints plus first-run docs
4. task examples and template discovery
5. stronger `automation publish` output
6. automation observability commands
7. docs, guards, AGENTS sync, and full validation

Each task group should land cleanly and keep the repo working on its own.

## File Structure

### Create

- `src/browser_cli/commands/doctor.py`
  - Human-readable and JSON-capable first-run diagnostics.
- `src/browser_cli/commands/paths.py`
  - Filesystem layout discovery for installed users.
- `src/browser_cli/cli/error_hints.py`
  - Maps typed CLI failures to short `Next:` recovery guidance.
- `src/browser_cli/task_runtime/templates.py`
  - Canonical task template text and example catalog metadata for installed-package discovery.
- `tests/unit/test_doctor_command.py`
  - `doctor` report rendering, check classification, and JSON contract tests.
- `tests/unit/test_paths_command.py`
  - `paths` output contract tests.
- `tests/unit/test_error_hints.py`
  - Recovery-hint mapping tests.
- `docs/installed-with-pip.md`
  - Dedicated pip-user quickstart.

### Modify

- `src/browser_cli/cli/main.py`
  - Wire new top-level commands and new `task`/`automation` subcommands; append `Next:` hints on failures.
- `src/browser_cli/constants.py`
  - Reuse existing app-path fields as the source of truth for `paths`.
- `src/browser_cli/commands/task.py`
  - Handle `task examples` and `task template`.
- `src/browser_cli/commands/automation.py`
  - Expand publish output and add `list`, `versions`, and `inspect`.
- `src/browser_cli/automation/api/server.py`
  - Include `latest_run` on single-automation lookups for `inspect`.
- `src/browser_cli/errors.py`
  - Keep typed errors stable; add only if the new CLI surfaces need a missing specific exception.
- `src/browser_cli/error_codes.py`
  - Add missing stable codes only if required by new automation-inspection failure paths.
- `tests/unit/test_cli.py`
  - Parser/help coverage for new commands.
- `tests/unit/test_task_commands.py`
  - `task examples` and `task template` behavior.
- `tests/unit/test_automation_commands.py`
  - `list`, `versions`, `inspect`, and enriched publish payloads.
- `tests/unit/test_automation_publish.py`
  - Snapshot metadata expectations used by publish and inspect.
- `README.md`
  - Installed-user oriented install/quickstart flow.
- `AGENTS.md`
  - Durable navigation and contract notes for the new CLI surfaces.
- `scripts/guards/product_contracts.py`
  - Freeze the expanded public command catalog.
- `scripts/guards/docs_sync.py`
  - Keep README/AGENTS durable phrases aligned with the new surfaces.

### Notes

- Do not introduce a new top-level package.
- Keep `doctor` and `paths` as hand-wired top-level commands in `src/browser_cli/cli/main.py`.
- Keep `task examples` and `task template` under `task`; do not introduce `task init`.
- Keep automation observability on the existing automation service and snapshot filesystem contract.
- Update `AGENTS.md` because this change adds public CLI surfaces and new recurring navigation paths.

### Task 1: Add `browser-cli doctor`

**Files:**
- Create: `src/browser_cli/commands/doctor.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `tests/unit/test_cli.py`
- Test: `tests/unit/test_doctor_command.py`

- [ ] **Step 1: Write the failing parser/help and report tests**

```python
from argparse import Namespace
import json

from browser_cli.cli.main import main
from browser_cli.commands.doctor import run_doctor_command


def test_doctor_help_mentions_json(capsys) -> None:
    exit_code = main(["doctor", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "diagnose" in captured.out.lower()


def test_doctor_json_payload_reports_checks(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.doctor.collect_doctor_report",
        lambda: {
            "overall_status": "warn",
            "checks": [
                {"id": "chrome", "status": "fail", "summary": "Chrome missing", "next": "install Chrome"}
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
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest tests/unit/test_cli.py -k doctor_help_mentions_json -v`
Expected: FAIL because the `doctor` parser does not exist.

Run: `pytest tests/unit/test_doctor_command.py -v`
Expected: FAIL because `browser_cli.commands.doctor` does not exist.

- [ ] **Step 3: Implement `src/browser_cli/commands/doctor.py`**

```python
from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from dataclasses import asdict, dataclass

from browser_cli.automation.service.client import read_automation_service_run_info
from browser_cli.constants import get_app_paths
from browser_cli.daemon.transport import probe_socket, read_run_info
from browser_cli.outputs.json import render_json_payload
from browser_cli.profiles.discovery import (
    discover_chrome_executable,
    discover_default_profile_dir,
)


@dataclass(slots=True, frozen=True)
class DoctorCheck:
    id: str
    status: str
    summary: str
    details: str | None = None
    next: str | None = None


def collect_doctor_report() -> dict[str, object]:
    app_paths = get_app_paths()
    checks = [
        _package_check(),
        _chrome_check(),
        _playwright_check(),
        _home_check(app_paths),
        _managed_profile_check(),
        _daemon_check(),
        _automation_service_check(),
    ]
    overall_status = "fail" if any(item.status == "fail" for item in checks) else "warn" if any(
        item.status == "warn" for item in checks
    ) else "pass"
    return {
        "overall_status": overall_status,
        "checks": [asdict(item) for item in checks],
    }


def run_doctor_command(args: Namespace) -> str:
    report = collect_doctor_report()
    if getattr(args, "json", False):
        return render_json_payload({"ok": True, "data": report, "meta": {"action": "doctor"}})
    return render_doctor_report(report)
```

- [ ] **Step 4: Wire the new top-level parser**

```python
from browser_cli.commands.doctor import run_doctor_command


doctor_parser = subparsers.add_parser(
    "doctor",
    help="Diagnose whether Browser CLI is ready on this machine.",
    description="Run install, browser, runtime, and service checks with next-step guidance.",
)
doctor_parser.add_argument(
    "--json",
    action="store_true",
    help="Return machine-readable diagnostic results.",
)
doctor_parser.set_defaults(handler=run_doctor_command)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_cli.py -k doctor_help_mentions_json -v`
Expected: PASS

Run: `pytest tests/unit/test_doctor_command.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/browser_cli/commands/doctor.py src/browser_cli/cli/main.py tests/unit/test_cli.py tests/unit/test_doctor_command.py
git commit -m "feat: add doctor command"
```

### Task 2: Add `browser-cli paths`

**Files:**
- Create: `src/browser_cli/commands/paths.py`
- Modify: `src/browser_cli/cli/main.py`
- Test: `tests/unit/test_paths_command.py`

- [ ] **Step 1: Write the failing `paths` tests**

```python
from argparse import Namespace
import json

from browser_cli.commands.paths import run_paths_command


def test_paths_text_output_lists_runtime_locations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    text = run_paths_command(Namespace(json=False))
    assert "home:" in text
    assert "tasks_dir:" in text
    assert "automations_dir:" in text
    assert "automation_db_path:" in text


def test_paths_json_payload_uses_stable_keys(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    payload = json.loads(run_paths_command(Namespace(json=True)))
    assert payload["data"]["home"].endswith("/home")
    assert payload["data"]["tasks_dir"].endswith("/home/tasks")
    assert payload["data"]["automation_service_log_path"].endswith(
        "/home/run/automation-service.log"
    )
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest tests/unit/test_paths_command.py -v`
Expected: FAIL because `browser_cli.commands.paths` does not exist.

- [ ] **Step 3: Implement `src/browser_cli/commands/paths.py`**

```python
from __future__ import annotations

from argparse import Namespace

from browser_cli.constants import get_app_paths
from browser_cli.outputs.json import render_json_payload


def _paths_payload() -> dict[str, str]:
    app_paths = get_app_paths()
    return {
        "home": str(app_paths.home),
        "tasks_dir": str(app_paths.tasks_dir),
        "automations_dir": str(app_paths.automations_dir),
        "artifacts_dir": str(app_paths.artifacts_dir),
        "daemon_log_path": str(app_paths.daemon_log_path),
        "automation_db_path": str(app_paths.automation_db_path),
        "automation_service_run_info_path": str(app_paths.automation_service_run_info_path),
        "automation_service_log_path": str(app_paths.automation_service_log_path),
    }


def run_paths_command(args: Namespace) -> str:
    payload = _paths_payload()
    if getattr(args, "json", False):
        return render_json_payload({"ok": True, "data": payload, "meta": {"action": "paths"}})
    lines = ["Paths", ""]
    lines.extend(f"{key}: {value}" for key, value in payload.items())
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Wire the parser**

```python
from browser_cli.commands.paths import run_paths_command


paths_parser = subparsers.add_parser(
    "paths",
    help="Show Browser CLI runtime paths.",
    description="Print the canonical Browser CLI home, task, automation, log, and artifact paths.",
)
paths_parser.add_argument(
    "--json",
    action="store_true",
    help="Return machine-readable path data.",
)
paths_parser.set_defaults(handler=run_paths_command)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_paths_command.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/browser_cli/commands/paths.py src/browser_cli/cli/main.py tests/unit/test_paths_command.py
git commit -m "feat: add runtime paths command"
```

### Task 3: Add `Next:` Error Hints And First-Run Docs

**Files:**
- Create: `src/browser_cli/cli/error_hints.py`
- Create: `tests/unit/test_error_hints.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `README.md`
- Create: `docs/installed-with-pip.md`

- [ ] **Step 1: Write the failing error-hint tests**

```python
from browser_cli.cli.error_hints import next_hint_for_error
from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError


def test_browser_missing_hint_points_to_doctor() -> None:
    hint = next_hint_for_error(BrowserUnavailableError("Stable Google Chrome was not found."))
    assert hint == "install stable Google Chrome and re-run browser-cli doctor"


def test_profile_lock_hint_points_to_status() -> None:
    hint = next_hint_for_error(ProfileUnavailableError("profile appears to be in use"))
    assert hint == "close Browser CLI-owned Chrome windows or inspect browser-cli status"
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest tests/unit/test_error_hints.py -v`
Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Implement the hint helper**

```python
from __future__ import annotations

from browser_cli import error_codes
from browser_cli.errors import BrowserCliError


def next_hint_for_error(exc: BrowserCliError) -> str | None:
    if exc.error_code == error_codes.BROWSER_UNAVAILABLE:
        return "install stable Google Chrome and re-run browser-cli doctor"
    if exc.error_code == error_codes.PROFILE_UNAVAILABLE:
        return "close Browser CLI-owned Chrome windows or inspect browser-cli status"
    if exc.error_code == error_codes.DAEMON_NOT_AVAILABLE:
        return "run browser-cli reload"
    if exc.error_code == error_codes.INVALID_INPUT and "task" in str(exc).lower():
        return "run browser-cli task validate <task-dir>"
    if "version" in str(exc).lower() and "not found" in str(exc).lower():
        return "run browser-cli automation versions <automation-id>"
    if "automation" in str(exc).lower() and "not found" in str(exc).lower():
        return "run browser-cli automation list"
    return None
```

- [ ] **Step 4: Append the hint in `src/browser_cli/cli/main.py`**

```python
from browser_cli.cli.error_hints import next_hint_for_error


except BrowserCliError as exc:
    sys.stderr.write(f"Error: {exc}\n")
    hint = next_hint_for_error(exc)
    if hint:
        sys.stderr.write(f"Next: {hint}\n")
    return exc.exit_code
```

- [ ] **Step 5: Write the first-run docs**

```markdown
## Installed With Pip

1. Install Browser CLI and its runtime prerequisites.
2. Run `browser-cli doctor`.
3. Run `browser-cli paths`.
4. Try `browser-cli read https://example.com`.
5. Create a task, then run `browser-cli task validate <task-dir>`.
6. Run `browser-cli task run <task-dir>`.
7. Publish with `browser-cli automation publish <task-dir>`.
```

Put the full walkthrough in `docs/installed-with-pip.md`, then add a short README
pointer to that doc from the Installation and Quick Start sections.

- [ ] **Step 6: Run the tests and spot-check the docs**

Run: `pytest tests/unit/test_error_hints.py tests/unit/test_cli.py -k "error_hints or runtime_error_maps_to_stderr" -v`
Expected: PASS

Run: `rg -n "browser-cli doctor|browser-cli paths|Installed With Pip" README.md docs/installed-with-pip.md`
Expected: matches in both files

- [ ] **Step 7: Commit**

```bash
git add src/browser_cli/cli/error_hints.py src/browser_cli/cli/main.py tests/unit/test_error_hints.py README.md docs/installed-with-pip.md
git commit -m "docs: add pip first-run guidance and error hints"
```

### Task 4: Add `task examples` And `task template`

**Files:**
- Create: `src/browser_cli/task_runtime/templates.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `src/browser_cli/commands/task.py`
- Modify: `tests/unit/test_task_commands.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing task-discovery tests**

```python
from argparse import Namespace

from browser_cli.commands.task import run_task_command


def test_task_examples_lists_curated_examples() -> None:
    payload = run_task_command(Namespace(task_subcommand="examples"))
    assert "interactive_reveal_capture" in payload
    assert "lazy_scroll_capture" in payload


def test_task_template_prints_three_contract_files(tmp_path) -> None:
    payload = run_task_command(
        Namespace(task_subcommand="template", print_template=True, output=None)
    )
    assert "task.py" in payload
    assert "task.meta.json" in payload
    assert "automation.toml" in payload


def test_task_template_output_writes_files(tmp_path) -> None:
    output_dir = tmp_path / "demo"
    run_task_command(
        Namespace(task_subcommand="template", print_template=False, output=str(output_dir))
    )
    assert (output_dir / "task.py").exists()
    assert (output_dir / "task.meta.json").exists()
    assert (output_dir / "automation.toml").exists()
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest tests/unit/test_task_commands.py -k "examples or template" -v`
Expected: FAIL because the `task` subcommands do not exist.

- [ ] **Step 3: Add canonical task assets**

```python
TASK_TEMPLATE_FILES = {
    "task.py": """from __future__ import annotations

def run(flow, inputs):
    url = str(inputs.get("url") or "https://example.com")
    flow.open(url)
    snapshot = flow.snapshot()
    return {"ok": True, "url": url, "snapshot": snapshot}
""",
    "task.meta.json": """{
  "task": {"id": "my_task", "name": "My Task", "goal": "Describe the task goal"},
  "environment": {},
  "success_path": {},
  "recovery_hints": {},
  "failures": [],
  "knowledge": {}
}
""",
    "automation.toml": """[automation]
id = "my_task"
name = "My Task"

[task]
path = "task.py"
meta_path = "task.meta.json"
entrypoint = "run"
""",
}

EXAMPLE_CATALOG = [
    ("interactive_reveal_capture", "Capture progressively revealed content."),
    ("lazy_scroll_capture", "Scroll and capture lazy-loaded pages."),
]
```

- [ ] **Step 4: Extend the parser and command handler**

```python
task_examples_parser = task_subparsers.add_parser(
    "examples",
    help="List built-in task examples.",
    description="Show canonical task examples available from the installed package.",
)
task_examples_parser.set_defaults(handler=run_task_command)

task_template_parser = task_subparsers.add_parser(
    "template",
    help="Print or write a minimal task template.",
    description="Expose canonical task.py, task.meta.json, and automation.toml templates.",
)
task_template_parser.add_argument(
    "--print",
    dest="print_template",
    action="store_true",
    help="Print the template files to stdout.",
)
task_template_parser.add_argument(
    "--output",
    help="Write the template files into the given directory.",
)
task_template_parser.set_defaults(handler=run_task_command)
```

```python
if args.task_subcommand == "examples":
    return "\n".join([f"{name}: {summary}" for name, summary in EXAMPLE_CATALOG]) + "\n"

if args.task_subcommand == "template":
    if getattr(args, "output", None):
        output_dir = Path(args.output).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, body in TASK_TEMPLATE_FILES.items():
            (output_dir / name).write_text(body, encoding="utf-8")
        return f"Template written to {output_dir}\n"
    return render_template_bundle(TASK_TEMPLATE_FILES)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_task_commands.py -k "examples or template" -v`
Expected: PASS

Run: `pytest tests/unit/test_cli.py -k "task" -v`
Expected: PASS with help text still showing `task`

- [ ] **Step 6: Commit**

```bash
git add src/browser_cli/task_runtime/templates.py src/browser_cli/cli/main.py src/browser_cli/commands/task.py tests/unit/test_task_commands.py tests/unit/test_cli.py
git commit -m "feat: add task examples and template discovery"
```

### Task 5: Strengthen `automation publish` Output

**Files:**
- Modify: `src/browser_cli/commands/automation.py`
- Modify: `tests/unit/test_automation_commands.py`

- [ ] **Step 1: Write the failing publish-output test**

```python
from argparse import Namespace
import json
from pathlib import Path

from browser_cli.commands.automation import run_automation_command


def test_automation_publish_reports_next_commands(monkeypatch, tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("browser_cli.commands.automation.ensure_automation_service_running", lambda: None)
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {"ok": True, "data": {"id": "demo"}},
    )
    payload = json.loads(run_automation_command(Namespace(automation_subcommand="publish", path=str(task_dir))))
    assert payload["data"]["published"]["source_task_dir"] == str(task_dir.resolve())
    assert payload["data"]["next_commands"]["inspect"] == "browser-cli automation inspect demo"
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `pytest tests/unit/test_automation_commands.py -k publish_reports_next_commands -v`
Expected: FAIL because the response does not include `source_task_dir` or `next_commands`.

- [ ] **Step 3: Expand the publish payload**

```python
return render_json_payload(
    {
        "ok": True,
        "data": {
            "published": {
                "automation_id": published.automation_id,
                "automation_name": published.automation_name,
                "version": published.version,
                "source_task_dir": str(Path(args.path).expanduser().resolve()),
                "snapshot_dir": str(published.snapshot_dir),
                "manifest_path": str(published.manifest_path),
            },
            "service": payload.get("data") or {},
            "next_commands": {
                "inspect": f"browser-cli automation inspect {published.automation_id}",
                "status": "browser-cli automation status",
                "ui": "browser-cli automation ui",
            },
            "model": {
                "task": "local editable source",
                "automation": "published immutable snapshot",
            },
        },
        "meta": {"action": "automation-publish"},
    }
)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_automation_commands.py -k publish_reports_next_commands -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/browser_cli/commands/automation.py tests/unit/test_automation_commands.py
git commit -m "feat: enrich automation publish output"
```

### Task 6: Add `automation list`, `versions`, And `inspect`

**Files:**
- Modify: `src/browser_cli/cli/main.py`
- Modify: `src/browser_cli/commands/automation.py`
- Modify: `src/browser_cli/automation/api/server.py`
- Modify: `tests/unit/test_automation_commands.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing observability tests**

```python
from argparse import Namespace
import json
from pathlib import Path

from browser_cli.commands.automation import run_automation_command


def test_automation_list_returns_service_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": [{"id": "demo", "version": "2", "enabled": True, "latest_run": None}],
        },
    )
    payload = json.loads(run_automation_command(Namespace(automation_subcommand="list")))
    assert payload["data"]["automations"][0]["id"] == "demo"


def test_automation_versions_reads_snapshot_versions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "3"
    version_dir.mkdir(parents=True)
    (version_dir / "publish.json").write_text(
        '{"automation_id":"demo","version":3,"source_task_path":"/tmp/task","snapshot_dir":"%s"}'
        % version_dir,
        encoding="utf-8",
    )
    payload = json.loads(
        run_automation_command(Namespace(automation_subcommand="versions", automation_id="demo"))
    )
    assert payload["data"]["versions"][0]["version"] == 3


def test_automation_inspect_combines_service_and_snapshot_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "2"
    version_dir.mkdir(parents=True)
    (version_dir / "publish.json").write_text(
        '{"automation_id":"demo","version":2,"source_task_path":"/tmp/task","snapshot_dir":"%s"}'
        % version_dir,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {
                "id": "demo",
                "version": "2",
                "task_path": str(version_dir / "task.py"),
                "task_meta_path": str(version_dir / "task.meta.json"),
                "schedule_kind": "manual",
                "schedule_payload": {"mode": "manual"},
                "latest_run": {"status": "success"},
            },
        },
    )
    payload = json.loads(
        run_automation_command(
            Namespace(automation_subcommand="inspect", automation_id="demo", version=None)
        )
    )
    assert payload["data"]["automation"]["id"] == "demo"
    assert payload["data"]["versions"][0]["version"] == 2
    assert payload["data"]["latest_run"]["status"] == "success"
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest tests/unit/test_automation_commands.py -k "automation_list_returns_service_items or automation_versions_reads_snapshot_versions or automation_inspect_combines_service_and_snapshot_data" -v`
Expected: FAIL because the parser and command branches do not exist.

- [ ] **Step 3: Add parser entries for the new automation subcommands**

```python
automation_list_parser = automation_subparsers.add_parser(
    "list",
    help="List published automations.",
    description="Show persisted automation ids, versions, and latest run summaries.",
)
automation_list_parser.set_defaults(handler=run_automation_command)

automation_versions_parser = automation_subparsers.add_parser(
    "versions",
    help="List published snapshot versions for one automation.",
    description="Inspect the local snapshot history for a published automation.",
)
automation_versions_parser.add_argument("automation_id", help="Persisted automation id.")
automation_versions_parser.set_defaults(handler=run_automation_command)

automation_inspect_parser = automation_subparsers.add_parser(
    "inspect",
    help="Inspect one published automation.",
    description="Combine service metadata, latest run status, and local snapshot version details.",
)
automation_inspect_parser.add_argument("automation_id", help="Persisted automation id.")
automation_inspect_parser.add_argument("--version", type=int, help="Specific snapshot version.")
automation_inspect_parser.set_defaults(handler=run_automation_command)
```

- [ ] **Step 4: Implement CLI-side snapshot inspection and extend the API**

```python
def _load_snapshot_versions(automation_id: str) -> list[dict[str, object]]:
    versions_dir = get_app_paths().automations_dir / automation_id / "versions"
    if not versions_dir.exists():
        return []
    versions: list[dict[str, object]] = []
    for entry in sorted(versions_dir.iterdir(), key=lambda item: int(item.name), reverse=True):
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        publish_path = entry / "publish.json"
        publish_data = json.loads(publish_path.read_text(encoding="utf-8")) if publish_path.exists() else {}
        versions.append(
            {
                "version": int(entry.name),
                "snapshot_dir": str(entry),
                "publish": publish_data,
                "task_path": str(entry / "task.py"),
                "task_meta_path": str(entry / "task.meta.json"),
            }
        )
    return versions
```

```python
if subcommand == "list":
    payload = request_automation_service("GET", "/api/automations", start_if_needed=True)
    return render_json_payload({"ok": True, "data": {"automations": payload.get("data") or []}, "meta": {"action": "automation-list"}})

if subcommand == "versions":
    versions = _load_snapshot_versions(args.automation_id)
    return render_json_payload({"ok": True, "data": {"automation_id": args.automation_id, "versions": versions}, "meta": {"action": "automation-versions"}})

if subcommand == "inspect":
    payload = request_automation_service("GET", f"/api/automations/{args.automation_id}", start_if_needed=True)
    versions = _load_snapshot_versions(args.automation_id)
    selected = next((item for item in versions if item["version"] == args.version), versions[0] if versions else None)
    return render_json_payload(
        {
            "ok": True,
            "data": {
                "automation": payload.get("data") or {},
                "versions": versions,
                "selected_version": selected,
                "latest_run": (payload.get("data") or {}).get("latest_run"),
            },
            "meta": {"action": "automation-inspect"},
        }
    )
```

```python
if path.startswith("/api/automations/") and method == "GET":
    automation_id = path.split("/")[3]
    automation = self.server.runtime.store.get_automation(automation_id)
    self._send_json(
        {
            "ok": True,
            "data": self._serialize_automation(automation, include_latest_run=True),
            "meta": {},
        }
    )
    return
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_automation_commands.py -k "automation_list_returns_service_items or automation_versions_reads_snapshot_versions or automation_inspect_combines_service_and_snapshot_data" -v`
Expected: PASS

Run: `pytest tests/unit/test_cli.py -k "automation" -v`
Expected: PASS with the new subcommands visible in help text

- [ ] **Step 6: Commit**

```bash
git add src/browser_cli/cli/main.py src/browser_cli/commands/automation.py src/browser_cli/automation/api/server.py tests/unit/test_automation_commands.py tests/unit/test_cli.py
git commit -m "feat: add automation inspection commands"
```

### Task 7: Update Docs, Guards, AGENTS, And Run Full Validation

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `scripts/guards/product_contracts.py`
- Modify: `scripts/guards/docs_sync.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing contract and docs expectations**

```python
def test_top_level_help_lists_doctor_and_paths(capsys) -> None:
    exit_code = main(["--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "doctor" in captured.out
    assert "paths" in captured.out


def test_task_help_lists_examples_and_template(capsys) -> None:
    exit_code = main(["task", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "examples" in captured.out
    assert "template" in captured.out


def test_automation_help_lists_observability_commands(capsys) -> None:
    exit_code = main(["automation", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "list" in captured.out
    assert "versions" in captured.out
    assert "inspect" in captured.out
```

- [ ] **Step 2: Update the product-contract guard**

```python
if "doctor" not in top_level_commands:
    findings.append(Finding("error", "CONTRACT018", "Top-level 'doctor' command is required."))
if "paths" not in top_level_commands:
    findings.append(Finding("error", "CONTRACT019", "Top-level 'paths' command is required."))

expected = {"examples", "run", "template", "validate"}
```

```python
expected = {
    "export",
    "import",
    "inspect",
    "list",
    "publish",
    "status",
    "stop",
    "ui",
    "versions",
}
```

- [ ] **Step 3: Update durable docs and repo guidance**

```markdown
- CLI shape, command names, help text, and top-level parser wiring:
  `src/browser_cli/cli/main.py`
- pip-user diagnostics:
  `src/browser_cli/commands/doctor.py`
- runtime path discovery:
  `src/browser_cli/commands/paths.py`
- task examples and templates:
  `src/browser_cli/task_runtime/templates.py`, `src/browser_cli/commands/task.py`
- automation observability:
  `src/browser_cli/commands/automation.py`, `src/browser_cli/automation/api/server.py`
```

Also update README to point installed users to `docs/installed-with-pip.md` and
keep the `task` versus `automation` distinction visible in the task and publish
examples.

- [ ] **Step 4: Run the complete validation suite**

Run: `./scripts/lint.sh`
Expected: PASS

Run: `./scripts/test.sh`
Expected: PASS

Run: `./scripts/guard.sh`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md scripts/guards/product_contracts.py scripts/guards/docs_sync.py tests/unit/test_cli.py
git add docs/installed-with-pip.md
git commit -m "docs: finalize pip user ux roadmap surfaces"
```

## Self-Review Checklist

Spec coverage:

- `doctor`: Task 1
- `paths`: Task 2
- `Next:` recovery hints and first-run guidance: Task 3
- task example/template discovery: Task 4
- stronger publish output: Task 5
- automation list/versions/inspect: Task 6
- docs, AGENTS, guards, and final validation: Task 7

Placeholder scan:

- No `TODO`, `TBD`, or "implement later" placeholders remain in the plan.
- Every task includes exact file paths, commands, and concrete code snippets.

Type consistency:

- `run_doctor_command(args: Namespace)` and `run_paths_command(args: Namespace)` match existing command-handler patterns.
- `task examples`, `task template`, `automation list`, `automation versions`, and `automation inspect` use parser names that match their command-handler branches.

