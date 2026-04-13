from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from browser_cli.automation.models import PersistedAutomationDefinition
from browser_cli.automation.persistence import AutomationStore
from browser_cli.automation.scheduler import compute_next_run_at, normalize_schedule

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_normalize_interval_schedule() -> None:
    kind, payload, timezone_name = normalize_schedule(
        "interval",
        {"interval_seconds": 300},
        timezone_name="Asia/Shanghai",
    )
    assert kind == "interval"
    assert payload == {"interval_seconds": 300}
    assert timezone_name == "Asia/Shanghai"


def test_compute_next_run_at_daily_is_future() -> None:
    next_run = compute_next_run_at(
        "daily",
        {"hour": 9, "minute": 30},
        timezone_name="UTC",
        now=datetime(2026, 4, 12, 9, 29, tzinfo=timezone.utc),
    )
    assert next_run == "2026-04-12T09:30:00+00:00"


def test_store_persists_and_queues_due_runs(tmp_path: Path) -> None:
    store = AutomationStore(tmp_path / "automations.db")
    automation = PersistedAutomationDefinition(
        id="interactive_reveal_capture",
        name="Interactive Reveal Capture",
        task_path=REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.py",
        task_meta_path=REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.meta.json",
        enabled=True,
        schedule_kind="interval",
        schedule_payload={"interval_seconds": 60},
        timezone="UTC",
        output_dir=tmp_path / "runs",
        input_overrides={"url": "https://example.com"},
    )
    created = store.upsert_automation(automation)
    assert created.definition_status == "valid"
    assert created.next_run_at is not None
    assert store.get_automation(automation.id).name == "Interactive Reveal Capture"

    with store._connect() as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE automations SET next_run_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", created.id),
        )

    queued = store.enqueue_due_runs()
    assert len(queued) == 1
    run = store.claim_next_run()
    assert run is not None
    assert run.status == "running"


def test_retry_run_respects_effective_inputs(tmp_path: Path) -> None:
    store = AutomationStore(tmp_path / "automations.db")
    automation = store.upsert_automation(
        PersistedAutomationDefinition(
            id="lazy_scroll_capture",
            name="Lazy Scroll Capture",
            task_path=REPO_ROOT / "tasks" / "lazy_scroll_capture" / "task.py",
            task_meta_path=REPO_ROOT / "tasks" / "lazy_scroll_capture" / "task.meta.json",
            enabled=False,
            schedule_kind="manual",
            schedule_payload={},
            timezone="UTC",
            output_dir=tmp_path / "runs",
            input_overrides={"url": "https://example.com", "max_rounds": 4},
            retry_attempts=2,
            retry_backoff_seconds=5,
        )
    )
    run = store.create_run(
        automation.id,
        trigger_type="manual",
        effective_inputs={"url": "https://retry.example.com"},
    )
    retried = store.retry_run(run.run_id)
    assert retried.trigger_type == "retry"
    assert retried.effective_inputs == {"url": "https://retry.example.com"}
    assert retried.attempt_number == 1


def test_create_run_preserves_explicit_empty_inputs(tmp_path: Path) -> None:
    store = AutomationStore(tmp_path / "automations.db")
    automation = store.upsert_automation(
        PersistedAutomationDefinition(
            id="empty_inputs",
            name="Empty Inputs",
            task_path=REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.py",
            task_meta_path=REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.meta.json",
            enabled=False,
            schedule_kind="manual",
            schedule_payload={},
            timezone="UTC",
            output_dir=tmp_path / "runs",
            input_overrides={"url": "https://example.com"},
        )
    )
    run = store.create_run(automation.id, trigger_type="manual", effective_inputs={})
    assert run.effective_inputs == {}


def test_blank_output_dir_uses_default_automation_runs_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    store = AutomationStore(tmp_path / "automations.db")
    automation = store.upsert_automation(
        PersistedAutomationDefinition(
            id="default_output",
            name="Default Output",
            task_path=REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.py",
            task_meta_path=REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.meta.json",
            enabled=False,
            schedule_kind="manual",
            schedule_payload={},
            timezone="UTC",
            output_dir=Path(),
        )
    )
    assert automation.output_dir == (tmp_path / "home" / "automations" / "runs" / automation.id)


def test_lazy_scroll_automation_manifest_exists() -> None:
    manifest_path = REPO_ROOT / "tasks" / "lazy_scroll_capture" / "automation.toml"
    payload = manifest_path.read_text(encoding="utf-8")
    assert "[automation]" in payload


def test_douyin_automation_manifest_exists() -> None:
    manifest_path = REPO_ROOT / "tasks" / "douyin_video_download" / "automation.toml"
    payload = manifest_path.read_text(encoding="utf-8")
    assert "[automation]" in payload
    assert 'id = "douyin_video_download"' in payload
