from __future__ import annotations

from browser_cli.task_runtime import Flow


def run(flow: Flow, inputs: dict) -> dict:
    url = str(inputs.get("url") or "").strip()
    if not url:
        raise ValueError("url input is required")
    max_rounds = int(inputs.get("max_rounds") or 8)
    wait_seconds = float(inputs.get("wait_seconds") or 0.3)

    flow.open(url)
    scroll_result = flow.scroll_until_stable(max_rounds=max_rounds, wait_seconds=wait_seconds)
    html = flow.html()
    html_path = flow.write_text_artifact("lazy.html", html)
    rounds_path = flow.write_json_artifact("scroll-rounds.json", scroll_result)

    return {
      "url": url,
      "stabilized": bool(scroll_result["stabilized"]),
      "round_count": len(scroll_result["rounds"]),
      "html_path": str(html_path),
      "rounds_path": str(rounds_path)
    }
