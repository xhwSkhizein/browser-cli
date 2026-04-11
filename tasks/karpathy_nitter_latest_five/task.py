from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from browser_cli.task_runtime import Flow, FlowContext

DEFAULT_PROFILE_URL = "https://nitter.net/karpathy"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _page_state(flow: Flow) -> dict[str, Any]:
    state = flow.eval(
        """(() => ({
            readyState: document.readyState,
            href: location.href,
            title: document.title || "",
            bodyTextLength: document.body ? document.body.innerText.trim().length : 0,
            bodyChildElementCount: document.body ? document.body.childElementCount : 0,
            timelineCount: document.querySelectorAll(".timeline-item").length,
            bodyPreview: document.body ? document.body.innerText.trim().slice(0, 280) : ""
        }))()"""
    )
    if isinstance(state, dict):
        return state
    return {"raw": state}


def _extract_tweets(flow: Flow, limit: int) -> list[dict[str, Any]]:
    payload = flow.eval(
        f"""(() => {{
            const limit = {limit};
            const pick = (root, selectors) => {{
                for (const selector of selectors) {{
                    const node = root.querySelector(selector);
                    if (node) return node;
                }}
                return null;
            }};
            const text = (node) => node ? node.textContent.replace(/\\s+/g, " ").trim() : null;
            const absolute = (href) => {{
                if (!href) return null;
                try {{
                    return new URL(href, location.origin).toString();
                }} catch {{
                    return href;
                }}
            }};
            const unique = (values) => Array.from(new Set(values.filter(Boolean)));
            const isPinned = (item) => /(^|\\n)\\s*Pinned Tweet\\b/i.test(item.innerText || "");
            const items = Array.from(document.querySelectorAll(".timeline-item"))
                .filter((item) => !isPinned(item))
                .slice(0, limit);
            return items.map((item, index) => {{
                const statusLink = pick(item, [
                    ".tweet-date a[href*='/status/']",
                    "a.tweet-link[href*='/status/']",
                    "a[href*='/status/']"
                ]);
                const contentNode = pick(item, [
                    ".tweet-content.media-body",
                    ".tweet-content",
                    ".tweet-body .tweet-content"
                ]);
                const authorNameNode = pick(item, [".fullname", ".tweet-header .fullname"]);
                const authorHandleNode = pick(item, [".username", ".tweet-header .username"]);
                const replyingToNode = item.querySelector(".replying-to");
                const statsNode = item.querySelector(".tweet-stats");
                const statusHref = statusLink ? statusLink.getAttribute("href") : null;
                const statusUrl = absolute(statusHref);
                const match = statusHref ? statusHref.match(/\\/status\\/(\\d+)/) : null;
                const contentLinks = Array.from((contentNode || item).querySelectorAll("a[href]"))
                    .map((node) => absolute(node.getAttribute("href")));
                const mediaUrls = Array.from(item.querySelectorAll("img[src], video[src], video source[src]"))
                    .map((node) => absolute(node.getAttribute("src")));
                return {{
                    index,
                    tweet_id: match ? match[1] : null,
                    tweet_url: statusUrl,
                    published_label: text(statusLink),
                    author_name: text(authorNameNode),
                    author_handle: text(authorHandleNode),
                    content_text: text(contentNode),
                    replying_to: text(replyingToNode),
                    stats_text: text(statsNode),
                    media_urls: unique(mediaUrls),
                    external_links: unique(contentLinks.filter((href) => href && !href.startsWith(location.origin))),
                    is_pinned: isPinned(item),
                    is_retweet: item.classList.contains("retweet-header") || !!item.querySelector(".retweet-header"),
                    is_reply: !!replyingToNode
                }};
            }});
        }})()"""
    )
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _make_failure(*, code: str, message: str, profile_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "profile_state": profile_state,
    }


def run(flow: Flow, inputs: dict) -> dict:
    profile_url = str(inputs.get("url") or DEFAULT_PROFILE_URL).strip()
    limit = int(inputs.get("limit") or 5)
    wait_seconds = float(inputs.get("wait_seconds") or 3.0)

    result: dict[str, Any] = {
        "ok": False,
        "task_id": "karpathy_nitter_latest_five",
        "attempted_at": _utc_now(),
        "source": {
            "site": "nitter.net",
            "profile_url": profile_url,
        },
        "requested_count": limit,
        "tweet_count": 0,
        "tweets": [],
        "artifacts": {},
    }

    try:
        flow.open(profile_url)
        flow.wait(wait_seconds)
        profile_state = _page_state(flow)
        profile_state_path = flow.write_json_artifact("profile-state.json", profile_state)
        result["artifacts"]["profile_state_path"] = str(profile_state_path)

        tweets = _extract_tweets(flow, limit)
        result["tweet_count"] = len(tweets)
        result["tweets"] = tweets
        result["ok"] = len(tweets) == limit

        if len(tweets) != limit:
            result["error"] = _make_failure(
                code="PARTIAL_RESULT" if tweets else "NO_TWEETS_FOUND",
                message=(
                    f"Expected {limit} tweets but extracted {len(tweets)}."
                    if tweets
                    else "The profile rendered, but no timeline items could be extracted."
                ),
                profile_state=profile_state,
            )

        result["artifacts"]["result_path"] = str((flow.artifacts_dir / "result.json").resolve())
        result_path = flow.write_json_artifact("result.json", result)
        result["artifacts"]["result_path"] = str(result_path)
        return result
    finally:
        try:
            flow.close()
        except Exception:
            pass


def _load_inputs(argv: list[str]) -> dict[str, Any]:
    if len(argv) < 2:
        return {}
    raw = argv[1]
    path = Path(raw)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(raw)


if __name__ == "__main__":
    task_path = Path(__file__).resolve()
    flow = Flow(
        context=FlowContext(
            task_path=task_path,
            task_dir=task_path.parent,
            artifacts_dir=task_path.parent / "artifacts",
        )
    )
    print(json.dumps(run(flow, _load_inputs(sys.argv)), ensure_ascii=False, indent=2))
