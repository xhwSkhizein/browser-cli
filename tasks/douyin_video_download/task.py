from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - depends on the caller's Python env
    requests = None

from browser_cli.task_runtime import Flow, FlowContext


DEFAULT_URL = "https://v.douyin.com/6Zy2Ip3kk-g"


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("requests is required. Run this task with the same Python environment that provides browser-cli.")


def _page_probe(flow: Flow) -> dict[str, Any]:
    payload = flow.eval(
        """() => {
            const resources = performance.getEntriesByType('resource').map((entry) => entry.name);
            const detailUrl = resources.find((url) => url.includes('/aweme/v1/web/aweme/detail/')) || null;
            const mediaUrls = resources.filter((url) => url.includes('douyinvod.com')).slice(0, 10);
            const match = location.pathname.match(/\\/video\\/(\\d+)/);
            return {
                href: location.href,
                title: document.title || '',
                readyState: document.readyState,
                userAgent: navigator.userAgent,
                awemeIdFromPath: match ? match[1] : null,
                hasRenderData: !!document.getElementById('RENDER_DATA'),
                detailUrl,
                mediaUrls,
            };
        }"""
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected page probe payload.")
    return payload


def _wait_for_detail_url(flow: Flow, *, rounds: int, wait_seconds: float) -> dict[str, Any]:
    last_probe: dict[str, Any] | None = None
    for _ in range(rounds):
        probe = _page_probe(flow)
        last_probe = probe
        if probe.get("detailUrl"):
            return probe
        flow.wait(wait_seconds)
    raise RuntimeError(f"Timed out waiting for Douyin detail URL. Last probe: {json.dumps(last_probe, ensure_ascii=False)}")


def _collect_browser_cookies(flow: Flow) -> list[dict[str, Any]]:
    payload = flow.command("cookies")
    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        raise RuntimeError("browser-cli cookies command returned an invalid payload.")
    return [cookie for cookie in cookies if isinstance(cookie, dict)]


def _build_session(cookies: list[dict[str, Any]]) -> requests.Session:
    _require_requests()
    session = requests.Session()
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        if not name:
            continue
        session.cookies.set(
            name,
            str(cookie.get("value") or ""),
            domain=str(cookie.get("domain") or "") or None,
            path=str(cookie.get("path") or "/"),
        )
    return session


def _build_detail_headers(page: dict[str, Any], session: requests.Session) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": str(page.get("href") or "https://www.douyin.com/"),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": str(page.get("userAgent") or ""),
        "X-Requested-With": "XMLHttpRequest",
    }
    csrf = session.cookies.get("passport_csrf_token", domain=".douyin.com") or session.cookies.get("passport_csrf_token")
    if csrf:
        headers["x-secsdk-csrf-request"] = "1"
        headers["x-secsdk-csrf-token"] = csrf
    return headers


def _fetch_detail_payload(
    session: requests.Session,
    *,
    detail_url: str,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    response = session.get(detail_url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("Douyin detail response was empty. Full browser cookies are likely missing or stale.")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Douyin detail response did not decode to a JSON object.")
    return payload


def _first_urls(node: Any) -> list[str]:
    if not isinstance(node, dict):
        return []
    value = node.get("url_list")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _pick_video_url(detail_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    aweme = detail_payload.get("aweme_detail")
    if not isinstance(aweme, dict):
        aweme_list = detail_payload.get("aweme_list")
        if isinstance(aweme_list, list) and aweme_list and isinstance(aweme_list[0], dict):
            aweme = aweme_list[0]
    if not isinstance(aweme, dict):
        raise RuntimeError("Douyin detail payload is missing aweme_detail.")

    video = aweme.get("video")
    if not isinstance(video, dict):
        raise RuntimeError("Douyin detail payload is missing aweme_detail.video.")

    candidates: list[tuple[str, str]] = []
    for label, value in (
        ("play_addr", _first_urls(video.get("play_addr"))),
        ("play_addr_h264", _first_urls(video.get("play_addr_h264"))),
        ("play_addr_265", _first_urls(video.get("play_addr_265"))),
    ):
        for url in value:
            candidates.append((label, url))

    bit_rates = video.get("bit_rate")
    if isinstance(bit_rates, list):
        for index, item in enumerate(bit_rates):
            if not isinstance(item, dict):
                continue
            for url in _first_urls(item.get("play_addr")):
                candidates.append((f"bit_rate[{index}].play_addr", url))

    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for label, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        deduped.append((label, url))

    if not deduped:
        raise RuntimeError("No playable video URL candidates were found in the Douyin detail JSON.")

    source, url = deduped[0]
    summary = {
        "aweme_id": aweme.get("aweme_id"),
        "desc": aweme.get("desc"),
        "selected_source": source,
        "candidate_count": len(deduped),
        "candidate_preview": [{"source": label, "url": candidate} for label, candidate in deduped[:5]],
    }
    return url, summary


def _safe_filename(aweme_id: str | None, fallback: str = "douyin-video") -> str:
    raw = aweme_id or fallback
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")
    return cleaned or fallback


def _download_video(
    *,
    session: requests.Session,
    video_url: str,
    referer: str,
    user_agent: str,
    output_path: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    headers = {
        "Accept": "*/*",
        "Referer": referer,
        "User-Agent": user_agent,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with session.get(video_url, headers=headers, stream=True, timeout=timeout_seconds) as response:
        response.raise_for_status()
        size = 0
        with output_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                handle.write(chunk)
                size += len(chunk)
    return {"path": str(output_path.resolve()), "bytes": size}


def run(flow: Flow, inputs: dict) -> dict:
    _require_requests()
    url = str(inputs.get("url") or DEFAULT_URL).strip()
    if not url:
        raise ValueError("url input is required")

    wait_rounds = int(inputs.get("wait_rounds") or 8)
    wait_seconds = float(inputs.get("wait_seconds") or 1.0)
    timeout_seconds = float(inputs.get("timeout_seconds") or 30.0)

    result: dict[str, Any] = {
        "ok": False,
        "task_id": "douyin_video_download",
        "input_url": url,
        "artifacts": {},
    }

    try:
        flow.open(url)
        page = _wait_for_detail_url(flow, rounds=wait_rounds, wait_seconds=wait_seconds)
        flow.write_json_artifact("page-state.json", page)

        cookies = _collect_browser_cookies(flow)
        session = _build_session(cookies)
        detail_headers = _build_detail_headers(page, session)
        detail_payload = _fetch_detail_payload(
            session,
            detail_url=str(page["detailUrl"]),
            headers=detail_headers,
            timeout_seconds=timeout_seconds,
        )
        detail_path = flow.write_json_artifact("detail.json", detail_payload)

        video_url, video_summary = _pick_video_url(detail_payload)
        filename = f"{_safe_filename(str(video_summary.get('aweme_id') or ''))}.mp4"
        download_info = _download_video(
            session=session,
            video_url=video_url,
            referer=str(page.get("href") or "https://www.douyin.com/"),
            user_agent=str(page.get("userAgent") or ""),
            output_path=flow.artifacts_dir / filename,
            timeout_seconds=timeout_seconds,
        )
        summary_path = flow.write_json_artifact(
            "download-summary.json",
            {
                "page": page,
                "cookie_count": len(cookies),
                "detail_url": page["detailUrl"],
                "selected_video_url": video_url,
                "video_summary": video_summary,
                "download": download_info,
            },
        )

        result.update(
            {
                "ok": True,
                "resolved_url": page.get("href"),
                "title": page.get("title"),
                "aweme_id": video_summary.get("aweme_id"),
                "detail_url": page.get("detailUrl"),
                "selected_video_url": video_url,
                "selected_video_source": video_summary.get("selected_source"),
                "cookie_count": len(cookies),
                "download_bytes": download_info["bytes"],
                "artifacts": {
                    "page_state_path": str((flow.artifacts_dir / "page-state.json").resolve()),
                    "detail_path": str(detail_path),
                    "summary_path": str(summary_path),
                    "video_path": download_info["path"],
                },
            }
        )
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
    candidate = Path(raw)
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
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
