# Task And Automation Examples

Browser CLI currently ships with three automation-packaged reference and real-site tasks:

- [`tasks/interactive_reveal_capture/task.py`](../../tasks/interactive_reveal_capture/task.py)
- [`tasks/lazy_scroll_capture/task.py`](../../tasks/lazy_scroll_capture/task.py)
- [`tasks/douyin_video_download/task.py`](../../tasks/douyin_video_download/task.py)

All three also include `automation.toml` examples for import/export review.

The repository also includes a real-site task example that remains task-first:

- [`tasks/karpathy_nitter_latest_five/task.py`](../../tasks/karpathy_nitter_latest_five/task.py)

That task is useful for direct `browser-cli task run ...` validation, but it
does not yet serve as the canonical automation publish example.

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

Run it directly:

```bash
browser-cli task validate tasks/interactive_reveal_capture
browser-cli task run tasks/interactive_reveal_capture --set url=https://example.com
```

Real-site examples can be run the same way:

```bash
browser-cli task validate tasks/douyin_video_download
browser-cli task run tasks/douyin_video_download --set url=https://v.douyin.com/6Zy2Ip3kk-g

browser-cli task validate tasks/karpathy_nitter_latest_five
browser-cli task run tasks/karpathy_nitter_latest_five
```

## One-Shot Read Pattern

Use `Flow.read(...)` when a task wants the same one-shot behavior as CLI `read`:

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    result = flow.read(inputs["url"], output_mode="snapshot", scroll_bottom=True)
    return {"snapshot": result.body}
```

## Automation Pattern

For durable recurring automation, publish or import an automation:

```bash
browser-cli automation publish tasks/interactive_reveal_capture
browser-cli automation publish tasks/douyin_video_download
browser-cli automation inspect douyin_video_download
browser-cli automation ui
browser-cli automation status
```

The automation service:

- persists automation definitions and run history in the Browser CLI home
- schedules repeated execution for supported automation schedule modes
- exposes a local Web UI for editing automation parameters and schedule settings
- still executes the underlying task through `task.py + browser_cli.task_runtime + browser daemon`
