from __future__ import annotations

from browser_cli.task_runtime import Flow


def run(flow: Flow, inputs: dict) -> dict:
    url = str(inputs.get("url") or "").strip()
    if not url:
        raise ValueError("url input is required")

    flow.open(url)
    snapshot = flow.snapshot()
    html = flow.html()
    html_path = flow.write_text_artifact("page.html", html)

    return {
        "url": url,
        "snapshot_id": snapshot.snapshot_id,
        "html_path": str(html_path),
    }
