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
┌─────────────────────────────────────────────────────────────┐
│  Task/Automation Layer  (task.py + task.meta.json + automation.toml) │
├─────────────────────────────────────────────────────────────┤
│  Browser Daemon  ──►  60+ commands  ──►  Semantic Ref System       │
│  ├─ read: one-shot page capture                                  │
│  ├─ open/snapshot/click/fill: interactive control                │
│  ├─ console/network/trace: observation & debugging               │
│  ├─ verify-*: assertions                                         │
│  └─ ... 60+ commands total                                       │
├─────────────────────────────────────────────────────────────┤
│  Dual Backend: Playwright (default) ◄──► Chrome Extension (opt)  │
└─────────────────────────────────────────────────────────────┘
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
- Stable Google Chrome
- Playwright Python package

Install from source:

```bash
git clone https://github.com/hongv/browser-cli.git
cd browser-cli

python3 -m pip install -e .
python3 -m pip install -e ".[dev]"
python3 -m playwright install chromium
```

The CLI targets stable Google Chrome. Playwright Chromium is mainly useful for
local integration testing.

Installed users should start with [`docs/installed-with-pip.md`](docs/installed-with-pip.md).
The first two commands to run are `browser-cli doctor` and `browser-cli paths`.

### Optional: Extension Mode

For real-Chrome execution:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `browser-cli-extension/`

Once connected, `browser-cli status` reports extension capability state and the
daemon can prefer the extension backend at safe idle points.

## Quick Start

If you installed Browser CLI from `pip`, use the dedicated installed-user guide
at [`docs/installed-with-pip.md`](docs/installed-with-pip.md). The short version
is:

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

Export a persisted automation back to `automation.toml`:

```bash
browser-cli automation export my_task --output /tmp/my_task.automation.toml
```

Included examples:

- [`tasks/interactive_reveal_capture/task.py`](tasks/interactive_reveal_capture/task.py)
- [`tasks/lazy_scroll_capture/task.py`](tasks/lazy_scroll_capture/task.py)
- [`docs/examples/task-and-automation.md`](docs/examples/task-and-automation.md)

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

## Documentation

- Repo navigation and subsystem ownership: [`AGENTS.md`](AGENTS.md)
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
python scripts/guards/run_all.py
```

Run the full local validation flow:

```bash
./scripts/check.sh
```

Fast Python 3.10 compatibility check:

```bash
python scripts/guards/python_compatibility.py
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
