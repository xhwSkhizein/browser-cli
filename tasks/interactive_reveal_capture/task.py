from __future__ import annotations

import json
from pathlib import Path

from browser_cli.task_runtime import Flow, FlowContext


def run(flow: Flow, inputs: dict) -> dict:
    url = str(inputs.get("url") or "").strip()
    if not url:
        raise ValueError("url input is required")
    timeout = float(inputs.get("timeout") or 5.0)

    flow.open(url)
    snapshot = flow.snapshot()
    reveal_ref = snapshot.find_ref(role="button", name="Reveal Message")
    flow.click(reveal_ref)
    flow.wait_text("Revealed", timeout=timeout)

    html = flow.html()
    html_path = flow.write_text_artifact("interactive.html", html)
    snapshot_path = flow.write_text_artifact("snapshot.txt", snapshot.tree)

    return {
        "url": url,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_ref_count": len(snapshot.refs),
        "html_path": str(html_path),
        "snapshot_path": str(snapshot_path),
    }


if __name__ == "__main__":
    task_path = Path(__file__).resolve()
    flow = Flow(
        context=FlowContext(
            task_path=task_path,
            task_dir=task_path.parent,
            artifacts_dir=task_path.parent / "artifacts",
        )
    )
    print(json.dumps(run(flow, {}), ensure_ascii=False, indent=2))
