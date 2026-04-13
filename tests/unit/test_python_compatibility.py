from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_automation_modules_import_on_current_python() -> None:
    env = dict(os.environ)
    src_path = str(REPO_ROOT / "src")
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_path if not current_pythonpath else os.pathsep.join([src_path, current_pythonpath])
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import browser_cli.automation.api.server; "
                "import browser_cli.automation.persistence.store; "
                "import browser_cli.automation.scheduler.schedule"
            ),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
