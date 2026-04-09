# Task And Workflow Examples

Browser CLI now ships with two reference task directories:

- [`interactive_reveal_capture`](/Users/hongv/workspace/m-projects/browser-cli/tasks/interactive_reveal_capture/task.py)
- [`lazy_scroll_capture`](/Users/hongv/workspace/m-projects/browser-cli/tasks/lazy_scroll_capture/task.py)

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

## Explore Skill

The reusable skill that standardizes Browser CLI-backed exploration lives at:

- repo source: [`skills/browser-cli-explore-delivery/SKILL.md`](/Users/hongv/workspace/m-projects/browser-cli/skills/browser-cli-explore-delivery/SKILL.md)
- installed path: `/Users/hongv/.agents/skills/browser-cli-explore-delivery`
