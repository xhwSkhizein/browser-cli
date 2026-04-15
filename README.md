# browser-cli

<p align="center">
  <b>CLI-first browser automation for AI agents</b>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#task-and-automation-model">Task And Automation Model</a> •
  <a href="#testing">Testing</a>
</p>

---

`browser-cli` is a browser automation tool for AI agents and developers who need
reliable browser control from the command line.

## Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Task/Automation Layer  (task.py + task.meta.json + automation.toml) │
├──────────────────────────────────────────────────────────────────────┤
│  Browser Daemon  ──►  60+ commands  ──►  Semantic Ref System         │
│  ├─ read: one-shot page capture                                      │
│  ├─ open/snapshot/click/fill: interactive control                    │
│  ├─ console/network/trace: observation & debugging                   │
│  ├─ verify-*: assertions                                             │
│  └─ ... 60+ commands total                                           │
├──────────────────────────────────────────────────────────────────────┤
│  Dual Backend: Playwright (default) ◄──► Chrome Extension (opt)      │
└──────────────────────────────────────────────────────────────────────┘
```

| Component | Purpose |
|-----------|---------|
| **Browser Daemon** | Long-lived browser instance with daemon-backed CLI commands |
| **Semantic Refs** | Stable element identifiers using bridgic-style reconstruction |
| **Task Runtime** | Reusable `task.py` execution through `browser_cli.task_runtime` |
| **Automation Service** | Persistent local service for published automation snapshots |

## Features

- **Dual Backend Architecture**: managed profile mode by default, extension mode when real Chrome is available
- **Semantic Ref System**: stable refs that survive many DOM re-renders
- **Agent Isolation**: `X_AGENT_ID` isolates visible tabs while sharing browser storage
- **JSON-First API**: daemon-backed commands return structured JSON
- **Task Runtime**: package browser logic as `task.py + task.meta.json`
- **Automation Publish Layer**: publish immutable task snapshots and operate them through a local Web UI

## Installation

Requirements:

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Stable Google Chrome

Install as a tool:

```bash
uv tool install browser-control-and-automation-cli
browser-cli doctor
browser-cli paths
browser-cli read https://example.com
```

The published package name is `browser-control-and-automation-cli`. The
installed command remains `browser-cli`.

Run without installing:

```bash
uvx --from browser-control-and-automation-cli browser-cli read https://example.com
```

Install from Git:

```bash
uv tool install git+https://github.com/hongv/browser-cli.git
browser-cli --help
```

Installed users should start with [`docs/installed-with-uv.md`](docs/installed-with-uv.md).
For removal and local cleanup guidance, see [`docs/uninstall.md`](docs/uninstall.md).

## Install Browser CLI Skills

Browser CLI ships with three packaged skills that can be installed into an
agent skills directory:

- `browser-cli-converge`
- `browser-cli-delivery`
- `browser-cli-explore`

Install them into the default skills root:

```bash
browser-cli install-skills
```

By default, Browser CLI writes the packaged skills into `~/.agents/skills`.
Use `--dry-run` to preview the install and `--target` to override the
destination:

```bash
browser-cli install-skills --dry-run
browser-cli install-skills --target ~/.codex/skills
```

You can rerun the command safely. Existing packaged Browser CLI skills at the
target path are replaced with the packaged versions from the installed wheel.
For a longer installed-user walkthrough, see
[`docs/install-skills.md`](docs/install-skills.md).

## Development

Clone the repository and sync the managed development environment:

```bash
git clone https://github.com/hongv/browser-cli.git
cd browser-cli
uv sync --dev
```

The CLI targets stable Google Chrome. Playwright Chromium is mainly useful for
local integration testing and is installed through the repo environment.

### Optional: Extension Mode

For real-Chrome execution:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `browser-cli-extension/`

Once connected, `browser-cli status` reports extension capability state and the
daemon can prefer the extension backend at safe idle points.

## Quick Start

If you installed Browser CLI with uv, use the dedicated installed-user guide at
[`docs/installed-with-uv.md`](docs/installed-with-uv.md). The short version is:

```bash
browser-cli doctor
browser-cli paths
browser-cli read https://example.com
```

### One-Shot Read

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

### Interactive Control

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli fill @input_ref "value"
browser-cli html
browser-cli status
browser-cli reload
```

### Multi-Agent Tabs

```bash
X_AGENT_ID=agent-a browser-cli open https://example.com
X_AGENT_ID=agent-a browser-cli tabs

X_AGENT_ID=agent-b browser-cli open https://example.org
X_AGENT_ID=agent-b browser-cli tabs
```

## Task And Automation Model

Browser CLI separates local authoring from durable publication:

- `task` is local editable source
- `automation` is a published immutable snapshot

Typical task layout:

```text
tasks/
  my_task/
    task.py
    task.meta.json
    automation.toml
```

Validate and run a task directly:

```bash
browser-cli task validate tasks/my_task
browser-cli task run tasks/my_task --set url=https://example.com
```

Publish the current task directory into the automation service:

```bash
browser-cli automation publish tasks/my_task
browser-cli automation status
browser-cli automation ui
```

Publication semantics:

- `automation publish` snapshots `task.py`, `task.meta.json`, and `automation.toml` together under `~/.browser-cli/automations/<automation-id>/versions/<version>/`
- if source `automation.toml` exists, Browser CLI uses it as the publish-time configuration truth
- if source `automation.toml` is absent, Browser CLI publishes generated defaults and reports that explicitly via `manifest_source`

Export a persisted automation back to `automation.toml`:

```bash
browser-cli automation export my_task --output /tmp/my_task.automation.toml
```

Included examples:

- Automation-packaged reference and real-site tasks:
  - [`tasks/interactive_reveal_capture/task.py`](tasks/interactive_reveal_capture/task.py)
  - [`tasks/lazy_scroll_capture/task.py`](tasks/lazy_scroll_capture/task.py)
  - [`tasks/douyin_video_download/task.py`](tasks/douyin_video_download/task.py)
- Additional real-site task examples:
  - [`tasks/karpathy_nitter_latest_five/task.py`](tasks/karpathy_nitter_latest_five/task.py)
- Additional usage notes:
  - [`docs/examples/task-and-automation.md`](docs/examples/task-and-automation.md)

Real-site publish example:

```bash
browser-cli task validate tasks/douyin_video_download
browser-cli automation publish tasks/douyin_video_download
browser-cli automation inspect douyin_video_download
browser-cli automation status
```

Inspect semantics:

- `browser-cli automation inspect <automation-id>` shows the current live automation-service configuration
- `browser-cli automation inspect <automation-id> --version <n>` shows `snapshot_config` for the immutable published version and `live_config` for the current service state
- `latest_run` remains a separate operational view

## Output Contracts

### `read`

- `stdout`: final rendered result only
- `stderr`: diagnostics only

Exit codes:

- `0`: success
- `1`: unexpected internal error
- `2`: usage error
- `66`: empty content
- `69`: browser unavailable
- `73`: profile unavailable
- `75`: temporary read failure

### Daemon-backed Commands

- success `stdout`: JSON only
- failure `stderr`: short error summary
- stable machine-readable error codes include:
  - `NO_ACTIVE_TAB`
  - `AGENT_ACTIVE_TAB_BUSY`
  - `TAB_NOT_FOUND`
  - `NO_SNAPSHOT_CONTEXT`
  - `REF_NOT_FOUND`
  - `STALE_SNAPSHOT`
  - `AMBIGUOUS_REF`

### Runtime Notes

- Managed profile mode is the default backend.
- Extension mode is the preferred real-Chrome backend when connected and healthy.
- Driver rebinding happens only at safe idle points and is reported as `state_reset`.
- `runtime.timeout_seconds` is the total wall-clock timeout for one automation run in the automation service.

## Documentation

- Repo navigation and subsystem ownership: [`AGENTS.md`](AGENTS.md)
- Installed-user guide: [`docs/installed-with-uv.md`](docs/installed-with-uv.md)
- Uninstall and cleanup guide: [`docs/uninstall.md`](docs/uninstall.md)
- Explore-to-task skill: [`skills/browser-cli-explore-delivery/SKILL.md`](skills/browser-cli-explore-delivery/SKILL.md)
- Smoke checklist: [`docs/smoke-checklist.md`](docs/smoke-checklist.md)

## Testing

Run lint:

```bash
./scripts/lint.sh
```

Run tests:

```bash
./scripts/test.sh
```

Run guards:

```bash
./scripts/guard.sh
```

Run the full local validation flow:

```bash
./scripts/check.sh
```

Fast Python 3.10 compatibility check:

```bash
uv run python scripts/guards/python_compatibility.py
```

When the runtime behaves unexpectedly, use:

```bash
browser-cli status
browser-cli reload
browser-cli status
```

The integration coverage is fixture-driven and local-first. It exercises:

- navigation, tabs, and history
- snapshot and rendered HTML capture
- semantic ref reconstruction after DOM re-render
- stale and ambiguous ref failures
- iframe refs
- ref-driven element actions
- console, network, dialogs, trace, video, screenshot, and PDF
- cookies, storage save/load, and `X_AGENT_ID` isolation
- task runtime and automation publishing/service flows

## Acknowledgements

This project is deeply inspired by
[**bridgic-browser**](https://github.com/bitsky-tech/bridgic-browser).
Browser CLI keeps the semantic ref and daemon-backed strengths while pushing the
product toward a CLI-first, agent-first surface with reusable task and
automation layers.
