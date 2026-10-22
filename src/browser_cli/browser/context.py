"""Validated settings for disposable, repeatable browser contexts."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from browser_cli.browser.capture import CaptureOptions, finite_number
from browser_cli.errors import InvalidInputError


@dataclass(frozen=True)
class ContextOptions:
    viewport_width: int = 1440
    viewport_height: int = 1024
    device_scale_factor: float = 1.0
    zoom: float = 1.0
    locale: str = "en-US"
    timezone_id: str = "UTC"
    font_family: str = "Arial"
    font_files: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_dict(cls, payload: Any) -> ContextOptions:
        if not isinstance(payload, dict):
            raise InvalidInputError("context must be a JSON object.")
        known = set(cls.__dataclass_fields__)
        if set(payload) - known:
            raise InvalidInputError(
                f"Unknown context settings: {', '.join(sorted(set(payload) - known))}"
            )
        defaults = cls()
        values = {key: payload.get(key, getattr(defaults, key)) for key in known}
        capture = CaptureOptions.from_dict(
            {
                key: values[key]
                for key in ("viewport_width", "viewport_height", "device_scale_factor")
            }
        )
        if capture.viewport is None or capture.device_scale_factor is None:
            raise InvalidInputError("Context viewport and device_scale_factor cannot be null.")
        values["zoom"] = finite_number(values["zoom"], "zoom", minimum=0.25, maximum=5)
        for key in ("locale", "timezone_id", "font_family"):
            if (
                not isinstance(values[key], str)
                or not values[key].strip()
                or any(ord(c) < 32 for c in values[key])
            ):
                raise InvalidInputError(f"context.{key} must be a non-empty string.")
        if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", values["locale"]):
            raise InvalidInputError("context.locale must be a language tag such as en-US or zh-CN.")
        try:
            ZoneInfo(values["timezone_id"])
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise InvalidInputError(f"Unknown timezone: {values['timezone_id']}") from exc
        fonts = values["font_files"]
        if not isinstance(fonts, list | tuple) or len(fonts) > 8:
            raise InvalidInputError(
                "font_files must be an array of at most eight {family, path} objects."
            )
        resolved = []
        for item in fonts:
            if not isinstance(item, dict) or set(item) != {"family", "path"}:
                raise InvalidInputError("Each font file requires family and path.")
            family, path = item["family"], item["path"]
            if (
                not isinstance(family, str)
                or not family.strip()
                or not isinstance(path, str)
                or not path.strip()
            ):
                raise InvalidInputError("Font family and path must be non-empty strings.")
            candidate = Path(path).expanduser().resolve()
            if not candidate.is_file() or candidate.stat().st_size > 10 * 1024 * 1024:
                raise InvalidInputError(f"Font file is missing or exceeds 10 MiB: {candidate}")
            resolved.append((family, str(candidate)))
        values["font_files"] = tuple(resolved)
        return cls(**values)

    def playwright_options(self) -> dict[str, Any]:
        return {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "screen": {"width": self.viewport_width, "height": self.viewport_height},
            "device_scale_factor": self.device_scale_factor,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "accept_downloads": True,
            "bypass_csp": True,
        }

    def init_script(self) -> str:
        rules = [
            f"html {{ zoom: {self.zoom} !important; }}",
            f"*, *::before, *::after {{ font-family: {json.dumps(self.font_family, ensure_ascii=False)} !important; }}",
        ]
        for family, path in self.font_files:
            font_path = Path(path)
            encoded = base64.b64encode(font_path.read_bytes()).decode("ascii")
            mime = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff"}.get(
                font_path.suffix.lower(), "font/woff2"
            )
            rules.append(
                f"@font-face {{ font-family: {json.dumps(family, ensure_ascii=False)}; src: url(data:{mime};base64,{encoded}); }}"
            )
        css = json.dumps("\n".join(rules))
        return f"""(() => {{
            const install = () => {{
                if (!document.documentElement) return false;
                const style = document.createElement('style');
                style.textContent = {css};
                document.documentElement.appendChild(style);
                return true;
            }};
            if (!install()) {{
                const observer = new MutationObserver(() => {{ if (install()) observer.disconnect(); }});
                observer.observe(document, {{ childList: true, subtree: true }});
            }}
        }})()"""

    def metadata(self) -> dict[str, Any]:
        return {
            **self.playwright_options(),
            "zoom": self.zoom,
            "font_family": self.font_family,
            "font_files": [{"family": family, "path": path} for family, path in self.font_files],
            "isolated": True,
            "zoom_method": "css",
        }
