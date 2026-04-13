"""automation service helpers."""

from browser_cli.automation.service.client import (
    ensure_automation_service_running,
    request_automation_service,
)

__all__ = ["ensure_automation_service_running", "request_automation_service"]
