"""Schedule normalization and next-run calculation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from browser_cli.errors import InvalidInputError

WEEKDAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def normalize_schedule(
    kind: str,
    payload: dict[str, Any] | None,
    *,
    timezone_name: str,
) -> tuple[str, dict[str, Any], str]:
    normalized_kind = (kind or "manual").strip().lower() or "manual"
    normalized_payload = dict(payload or {})
    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise InvalidInputError(f"Invalid workflow timezone: {timezone_name}") from exc

    if normalized_kind == "manual":
        return normalized_kind, {}, timezone_name
    if normalized_kind == "interval":
        seconds = int(normalized_payload.get("interval_seconds") or 0)
        if seconds <= 0:
            raise InvalidInputError("Interval workflows require positive interval_seconds.")
        return normalized_kind, {"interval_seconds": seconds}, timezone_name
    if normalized_kind == "daily":
        hour = int(
            normalized_payload.get("hour") if normalized_payload.get("hour") is not None else -1
        )
        minute = int(
            normalized_payload.get("minute") if normalized_payload.get("minute") is not None else -1
        )
        _validate_hour_minute(hour, minute)
        return normalized_kind, {"hour": hour, "minute": minute}, timezone_name
    if normalized_kind == "weekly":
        weekday = str(normalized_payload.get("weekday") or "").strip().lower()
        hour = int(
            normalized_payload.get("hour") if normalized_payload.get("hour") is not None else -1
        )
        minute = int(
            normalized_payload.get("minute") if normalized_payload.get("minute") is not None else -1
        )
        if weekday not in WEEKDAY_NAMES:
            expected = ", ".join(sorted(WEEKDAY_NAMES))
            raise InvalidInputError(f"Weekly workflows require weekday in {{{expected}}}.")
        _validate_hour_minute(hour, minute)
        return normalized_kind, {"weekday": weekday, "hour": hour, "minute": minute}, timezone_name
    raise InvalidInputError(f"Unsupported workflow schedule mode: {normalized_kind}")


def compute_next_run_at(
    kind: str,
    payload: dict[str, Any] | None,
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> str | None:
    normalized_kind, normalized_payload, timezone_name = normalize_schedule(
        kind, payload, timezone_name=timezone_name
    )
    if normalized_kind == "manual":
        return None
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if normalized_kind == "interval":
        seconds = int(normalized_payload["interval_seconds"])
        return _to_utc_iso(moment + timedelta(seconds=seconds))
    zone = ZoneInfo(timezone_name)
    local_now = moment.astimezone(zone)
    if normalized_kind == "daily":
        hour = int(normalized_payload["hour"])
        minute = int(normalized_payload["minute"])
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate = candidate + timedelta(days=1)
        return _to_utc_iso(candidate.astimezone(timezone.utc))
    weekday = WEEKDAY_NAMES[str(normalized_payload["weekday"])]
    hour = int(normalized_payload["hour"])
    minute = int(normalized_payload["minute"])
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - local_now.weekday()) % 7
    candidate = candidate + timedelta(days=days_ahead)
    if candidate <= local_now:
        candidate = candidate + timedelta(days=7)
    return _to_utc_iso(candidate.astimezone(timezone.utc))


def _validate_hour_minute(hour: int, minute: int) -> None:
    if hour < 0 or hour > 23:
        raise InvalidInputError("Workflow schedule hour must be between 0 and 23.")
    if minute < 0 or minute > 59:
        raise InvalidInputError("Workflow schedule minute must be between 0 and 59.")


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
