"""Canonical task templates and example catalog."""

from __future__ import annotations

TASK_TEMPLATE_FILES: dict[str, str] = {
    "task.py": """from __future__ import annotations


def run(flow, inputs):
    url = str(inputs.get("url") or "https://example.com")
    flow.open(url)
    snapshot = flow.snapshot()
    return {"ok": True, "url": url, "snapshot": snapshot.tree}
""",
    "task.meta.json": """{
  "task": {
    "id": "my_task",
    "name": "My Task",
    "goal": "Describe the task goal"
  },
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

[inputs]

[schedule]
mode = "manual"
timezone = "UTC"
""",
}

EXAMPLE_CATALOG: tuple[tuple[str, str], ...] = (
    ("interactive_reveal_capture", "Capture progressively revealed content."),
    ("lazy_scroll_capture", "Scroll and capture lazy-loaded pages."),
)


def render_template_bundle() -> str:
    parts: list[str] = []
    for name, body in TASK_TEMPLATE_FILES.items():
        parts.append(f"=== {name} ===")
        parts.append(body.rstrip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"
