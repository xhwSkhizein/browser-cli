# Task And Workflow Examples

Browser CLI now ships with two reference task directories:

- [`interactive_reveal_capture`](/Users/hongv/workspace/m-projects/browser-cli/tasks/interactive_reveal_capture/task.py)
- [`lazy_scroll_capture`](/Users/hongv/workspace/m-projects/browser-cli/tasks/lazy_scroll_capture/task.py)

Both reference tasks also ship with publishable workflow wrappers:

- [`interactive_reveal_capture/workflow.toml`](/Users/hongv/workspace/m-projects/browser-cli/tasks/interactive_reveal_capture/workflow.toml)
- [`lazy_scroll_capture/workflow.toml`](/Users/hongv/workspace/m-projects/browser-cli/tasks/lazy_scroll_capture/workflow.toml)

## Direct Task Runtime Pattern

Use the thin Python runtime inside `task.py`:

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    flow.open(inputs["url"])
    snapshot = flow.snapshot()
    ref = snapshot.find_ref(role="button", name="Reveal Message")
    flow.click(ref)
    flow.wait_text("Revealed", timeout=5)
    return {"html": flow.html()}
```

## Workflow Pattern

Wrap a stable task in `workflow.toml`:

```bash
browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml
browser-cli workflow run tasks/interactive_reveal_capture/workflow.toml --set url=https://example.com
```

The workflow runner:

- loads and validates `workflow.toml`
- validates the referenced `task.meta.json`
- loads the task entrypoint
- runs the task with `browser_cli.task_runtime`
- writes `artifacts/result.json` when configured

## Workflow Service Pattern

For durable recurring automation, publish the workflow into the local workflow
service and manage it through the local Web UI:

```bash
browser-cli workflow import tasks/interactive_reveal_capture/workflow.toml
browser-cli workflow ui
browser-cli workflow service-status
```

The workflow service:

- persists workflow definitions and run history in the Browser CLI home
- schedules repeated execution for supported workflow schedule modes
- exposes a local Web UI for editing workflow parameters and schedule settings
- still executes the underlying task through `task.py + browser_cli.task_runtime + browser daemon`

## Explore Skill

The reusable skill that standardizes Browser CLI-backed exploration lives at:

- repo source: [`skills/browser-cli-explore-delivery/SKILL.md`](/Users/hongv/workspace/m-projects/browser-cli/skills/browser-cli-explore-delivery/SKILL.md)
- installed path: `/Users/hongv/.agents/skills/browser-cli-explore-delivery`
