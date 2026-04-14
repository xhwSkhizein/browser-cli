"""Documentation synchronization guards."""

from __future__ import annotations

from pathlib import Path

from scripts.guards.common import Finding, discover_top_level_packages, read_section

REQUIRED_AGENT_PHRASES = [
    "Managed profile mode is the default browser backend.",
    "Extension mode is the preferred real-Chrome backend when the Browser CLI extension is connected and healthy.",
    "Driver rebinding may happen automatically only at safe idle points, and it must be reported as `state_reset` rather than treated as perfectly continuous state.",
    "`browser_cli.task_runtime` owns the public Python read contract and routes one-shot read through the daemon-managed browser lifecycle.",
    "Repository development is uv-only.",
    "`uv.lock`",
    "`.python-version`",
    "`scripts/guards/python_compatibility.py`",
    "`scripts/lint.sh`",
    "`scripts/test.sh`",
    "`scripts/guard.sh`",
    "`scripts/check.sh`",
    "`browser-cli install-skills` installs the packaged Browser CLI skills into `~/.agents/skills` by default and `--target` overrides the destination root.",
]

REQUIRED_README_PHRASES = [
    "Python 3.10+",
    "uv sync --dev",
    "uv tool install browserctl",
    "uvx --from browserctl browser-cli",
    "browser-cli task validate",
    "browser-cli automation publish",
    "./scripts/lint.sh",
    "./scripts/test.sh",
    "./scripts/check.sh",
]


def run(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    agents_path = root / "AGENTS.md"
    readme_path = root / "README.md"

    agents_text = agents_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")

    findings.extend(_check_agents_boundaries(agents_text, root))
    findings.extend(_check_agents_process(agents_text))
    findings.extend(_check_readme_validation(readme_text))
    return findings


def _check_agents_boundaries(agents_text: str, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    section = read_section(agents_text, "Architectural Boundaries")
    documented = {
        line.split("`")[1].removeprefix("browser_cli.").split(".", 1)[0]
        for line in section.splitlines()
        if line.startswith("- `browser_cli.")
    }
    expected = discover_top_level_packages(root)
    missing = sorted(expected - documented)
    if missing:
        findings.append(
            Finding(
                "error",
                "DOC001",
                "AGENTS.md Architectural Boundaries is missing package entries for: "
                + ", ".join(missing),
            )
        )
    return findings


def _check_agents_process(agents_text: str) -> list[Finding]:
    findings: list[Finding] = []
    for phrase in REQUIRED_AGENT_PHRASES:
        if phrase not in agents_text:
            findings.append(
                Finding(
                    "error",
                    "DOC002",
                    f"AGENTS.md must include the maintained rule or command: {phrase}",
                )
            )
    if "After each code change, run lint, tests, and guard." not in agents_text:
        findings.append(
            Finding(
                "error",
                "DOC003",
                "AGENTS.md must state that lint, tests, and guard run after each code change.",
            )
        )
    return findings


def _check_readme_validation(readme_text: str) -> list[Finding]:
    findings: list[Finding] = []
    for phrase in REQUIRED_README_PHRASES:
        if phrase not in readme_text:
            findings.append(
                Finding(
                    "warning",
                    "DOC004",
                    f"README.md should document the validation command: {phrase}",
                )
            )
    return findings
