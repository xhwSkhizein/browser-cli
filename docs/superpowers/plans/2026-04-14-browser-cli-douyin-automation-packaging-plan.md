# Browser CLI Douyin Automation Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package `tasks/douyin_video_download` as a first-class automation example and document the real-workstation publish flow.

**Architecture:** Add a repo-local `automation.toml` beside the existing Douyin task, then update docs and smoke guidance so the task is recognized as a publishable real-site automation example. Keep the runtime contract unchanged and add small unit coverage to prove the manifest loads and the task directory is accepted by publish flows.

**Tech Stack:** Python 3.10, TOML manifests, pytest, repository docs

---

### Task 1: Add the Douyin Automation Manifest

**Files:**
- Create: `tasks/douyin_video_download/automation.toml`
- Test: `tests/unit/test_task_runtime_automation.py`

- [ ] **Step 1: Write the failing manifest test**

```python
def test_load_automation_manifest_resolves_douyin_example() -> None:
    manifest = load_automation_manifest(
        REPO_ROOT / "tasks" / "douyin_video_download" / "automation.toml"
    )
    assert manifest.automation.id == "douyin_video_download"
    assert manifest.task.path.name == "task.py"
    assert manifest.task.meta_path.name == "task.meta.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_task_runtime_automation.py::test_load_automation_manifest_resolves_douyin_example -v`
Expected: FAIL because `tasks/douyin_video_download/automation.toml` does not exist yet.

- [ ] **Step 3: Write the minimal manifest**

```toml
[automation]
id = "douyin_video_download"
name = "Douyin Video Download"
description = "Open a Douyin share link, replay the signed detail request with browser cookies, and download the resolved video artifact."
version = "0.1.0"

[task]
path = "task.py"
meta_path = "task.meta.json"
entrypoint = "run"

[inputs]
url = "https://v.douyin.com/6Zy2Ip3kk-g"
wait_rounds = 8
wait_seconds = 1.0
timeout_seconds = 30.0

[schedule]
mode = "manual"
timezone = "Asia/Shanghai"

[outputs]
artifact_dir = "artifacts"
stdout = "json"

[hooks]
before_run = []
after_success = []
after_failure = []

[runtime]
retry_attempts = 0
log_level = "info"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_task_runtime_automation.py::test_load_automation_manifest_resolves_douyin_example -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tasks/douyin_video_download/automation.toml tests/unit/test_task_runtime_automation.py
git commit -m "feat: package douyin task as automation"
```

### Task 2: Document the Publish Flow

**Files:**
- Modify: `README.md`
- Modify: `docs/examples/task-and-automation.md`
- Modify: `docs/smoke-checklist.md`

- [ ] **Step 1: Write the failing doc assertions by searching for Douyin publish guidance**

```bash
rg -n "automation publish tasks/douyin_video_download|automation inspect douyin_video_download" README.md docs/examples/task-and-automation.md docs/smoke-checklist.md
```

Expected: no matches.

- [ ] **Step 2: Add the minimal doc updates**

```markdown
- keep `interactive_reveal_capture` as the stable fixture-first publish example
- add `douyin_video_download` as the real-site publish example
- in smoke, describe `task validate -> automation publish -> automation inspect/status`
```

- [ ] **Step 3: Re-run the search to verify the new guidance exists**

```bash
rg -n "automation publish tasks/douyin_video_download|automation inspect douyin_video_download" README.md docs/examples/task-and-automation.md docs/smoke-checklist.md
```

Expected: matches in all intended docs.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/examples/task-and-automation.md docs/smoke-checklist.md
git commit -m "docs: add douyin automation publish guidance"
```

### Task 3: Add Small Publish Coverage

**Files:**
- Modify: `tests/unit/test_automation_publish.py`
- Modify: `tests/unit/test_automation_service.py`

- [ ] **Step 1: Write the failing repository-example tests**

```python
def test_publish_task_dir_accepts_douyin_example(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    published = publish_task_dir(REPO_ROOT / "tasks" / "douyin_video_download", app_paths=get_app_paths())
    assert published.automation_id == "douyin_video_download"


def test_douyin_automation_manifest_exists() -> None:
    manifest_path = REPO_ROOT / "tasks" / "douyin_video_download" / "automation.toml"
    payload = manifest_path.read_text(encoding="utf-8")
    assert '[automation]' in payload
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `pytest tests/unit/test_automation_publish.py tests/unit/test_automation_service.py tests/unit/test_task_runtime_automation.py -v`
Expected: FAIL before the new manifest and assertions are in place.

- [ ] **Step 3: Write the minimal test updates**

```python
assert published.manifest_path.exists()
assert (published.snapshot_dir / "automation.toml").exists()
assert 'id = "douyin_video_download"' in payload
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `pytest tests/unit/test_automation_publish.py tests/unit/test_automation_service.py tests/unit/test_task_runtime_automation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_automation_publish.py tests/unit/test_automation_service.py tests/unit/test_task_runtime_automation.py
git commit -m "test: cover douyin automation packaging"
```

### Task 4: Full Validation

**Files:**
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-douyin-automation-packaging-plan.md`

- [ ] **Step 1: Run full repository validation**

```bash
./scripts/check.sh
```

Expected: PASS with lint, tests, and guards green.

- [ ] **Step 2: Mark the plan complete and commit**

```bash
git add docs/superpowers/plans/2026-04-14-browser-cli-douyin-automation-packaging-plan.md
git commit -m "docs: add douyin automation packaging plan"
```
