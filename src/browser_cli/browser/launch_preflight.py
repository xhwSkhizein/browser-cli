"""Check host restrictions before starting a browser process."""

from __future__ import annotations

import ctypes
import os
import sys

from browser_cli.errors import BrowserUnavailableError


def ensure_browser_launch_allowed() -> None:
    if sys.platform == "darwin" and _macos_sandbox_blocks_launch():
        raise BrowserUnavailableError(
            "The macOS sandbox blocks Chrome from accessing LaunchServices. "
            "Run browser-cli status --json to check for an existing daemon/extension, "
            "or start Browser CLI outside the agent sandbox with elevated execution permission."
        )


def _macos_sandbox_blocks_launch() -> bool:
    try:
        library = ctypes.CDLL("/usr/lib/libsandbox.1.dylib")
        sandbox_check = library.sandbox_check
        no_report = ctypes.c_int.in_dll(library, "SANDBOX_CHECK_NO_REPORT").value
    except (OSError, AttributeError, ValueError):
        # The sandbox SPI is optional; preserve normal launching if unavailable.
        return False

    # sandbox_check(pid_t, operation, filter, ...) is variadic. Declaring only
    # the fixed arguments is required for the macOS ARM64 calling convention.
    # SANDBOX_FILTER_GLOBAL_NAME = 2; read NO_REPORT from the system library.
    sandbox_check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    sandbox_check.restype = ctypes.c_int
    result = sandbox_check(
        os.getpid(),
        b"mach-lookup",
        2 | no_report,
        ctypes.c_char_p(b"com.apple.coreservices.launchservicesd"),
    )
    # 0 permits access, positive values deny it, and -1 means check failure.
    return result > 0
