# browser-cli

<p align="center">
  <b>CLI-first browser automation for AI agents</b>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#acknowledgements">Acknowledgements</a>
</p>

---

`browser-cli` is a browser automation tool designed for **AI agents** and **developers** who need reliable, scriptable browser control from the command line.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Task/Workflow Layer  (task.py + task.meta.json + workflow.toml)  │
├─────────────────────────────────────────────────────────────┤
│  Browser Daemon  ──►  60+ commands  ──►  Semantic Ref System       │
│  ├─ read: one-shot page capture                                  │
│  ├─ open/snapshot/click/fill: interactive control                │
│  ├─ console/network/trace: observation & debugging             │
│  ├─ verify-*: assertions                                         │
│  └─ ... 60+ commands total                                      │
├─────────────────────────────────────────────────────────────┤
│  Dual Backend: Playwright (default) ◄──► Chrome Extension (opt)    │
└─────────────────────────────────────────────────────────────┘
```

| Component | Purpose |
|-----------|---------|
| **Browser Daemon** | Long-lived browser instance with 60+ CLI commands |
| **Semantic Refs** | Stable element identifiers using bridgic-style reconstruction |
| **Task/Workflow** | Reusable automation packages for complex scenarios |

## Features

- **Dual Backend Architecture** — Managed Playwright profile mode by default; optional real-Chrome extension mode for higher fidelity
- **Semantic Ref System** — Stable element references that persist across DOM re-renders
- **Agent Isolation** — `X_AGENT_ID` support for multi-agent tab isolation
- **JSON-First API** — All daemon commands return structured JSON for programmatic use
- **Stealth Mode** — Anti-detection strategies for headless and headed browser modes
- **Workflow Runtime** — Package and reuse browser automation tasks
- **Extension Support** — Chrome extension for driving real Chrome instances

## Installation

**Requirements:**
- Python 3.10+
- Stable Google Chrome installed
- Playwright Python package

**Install from source:**

```bash
# Clone the repository
git clone https://github.com/hongv/browser-cli.git
cd browser-cli

# Install CLI/runtime dependencies
python3 -m pip install -e .

# Install development dependencies if you plan to run tests or repo checks
python3 -m pip install -e ".[dev]"

# Install Playwright browser binaries used by local integration tests
python3 -m playwright install chromium
```

The CLI targets stable Google Chrome. Playwright Chromium is mainly useful for local integration testing.
The project baseline is Python 3.10+, and CI validates unit coverage on Python 3.10, 3.11, and 3.12.

### Optional: Real-Chrome Extension Mode

For the highest-fidelity browser control:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select the `browser-cli-extension/` folder from this repo

Once connected, the daemon automatically upgrades to extension-backed real-Chrome mode.

The extension can also be loaded directly from the repo:
- Extension root: [`browser-cli-extension/manifest.json`](browser-cli-extension/manifest.json)
- Background worker: [`browser-cli-extension/src/background.js`](browser-cli-extension/src/background.js)

Once connected, `browser-cli status` reports extension capability status.

## Quick Start

### One-Shot Page Reading

Extract rendered HTML or structured snapshot from any URL:

```bash
# Get rendered DOM HTML
browser-cli read https://example.com

# Get structured accessibility tree with stable refs
browser-cli read https://example.com --snapshot

# Scroll to bottom before capture (for lazy-loaded content)
browser-cli read https://example.com --scroll-bottom
```

### Interactive Browser Control

The first command auto-starts a persistent browser daemon. Common workflows:

**Navigation & Page State:**
```bash
browser-cli open https://example.com
browser-cli snapshot                    # Get page with stable refs
browser-cli click @8d4b03a9            # Click element by ref
browser-cli fill @input_ref "value"    # Fill input
browser-cli html                       # Get rendered HTML
```

**Tab Management:**
```bash
browser-cli tabs                       # List visible tabs
browser-cli new-tab https://example.org
browser-cli switch-tab <page_id>
browser-cli close-tab <page_id>
```

**Observation & Debugging:**
```bash
browser-cli console-start              # Start capturing console logs
browser-cli network-start            # Start capturing network requests
browser-cli trace-start              # Start performance tracing
browser-cli screenshot page.png        # Save screenshot
```

**Verification:**
```bash
browser-cli verify-text "Expected text"
browser-cli verify-url "https://example.com/*"
browser-cli verify-visible --role button --name "Submit"
```

### Full Command Catalog

| Category | Commands |
|----------|----------|
| **Navigation** | `open`, `search`, `info`, `back`, `forward`, `page-reload` |
| **Page State** | `html`, `snapshot`, `screenshot`, `pdf` |
| **Element Actions** | `click`, `double-click`, `hover`, `focus`, `fill`, `select`, `check`, `uncheck`, `scroll-to`, `drag`, `upload` |
| **Tabs** | `tabs`, `new-tab`, `switch-tab`, `close-tab`, `close` |
| **Input** | `type`, `press`, `key-down`, `key-up` |
| **Mouse** | `scroll`, `mouse-click`, `mouse-move`, `mouse-drag`, `mouse-down`, `mouse-up` |
| **Wait** | `wait`, `wait-network` |
| **Script** | `eval`, `eval-on` |
| **Console** | `console-start`, `console-stop`, `console` |
| **Network** | `network-start`, `network-stop`, `network` |
| **Dialog** | `dialog-setup`, `dialog`, `dialog-remove` |
| **Storage** | `cookies`, `cookie-set`, `cookies-clear`, `storage-save`, `storage-load` |
| **Verification** | `verify-text`, `verify-visible`, `verify-url`, `verify-title`, `verify-state`, `verify-value` |
| **Trace** | `trace-start`, `trace-chunk`, `trace-stop` |
| **Video** | `video-start`, `video-stop` |
| **Lifecycle** | `status`, `reload`, `stop`, `resize` |

Use `browser-cli <command> -h` for detailed help on any command.

### Multi-Agent Support

Isolate tabs between different agents using `X_AGENT_ID`:

```bash
# Agent A
X_AGENT_ID=agent-a browser-cli open https://example.com
X_AGENT_ID=agent-a browser-cli tabs

# Agent B (separate tab context)
X_AGENT_ID=agent-b browser-cli open https://example.org
X_AGENT_ID=agent-b browser-cli tabs
```

### Lifecycle Commands

| Command | Purpose |
|---------|---------|
| `browser-cli status` | First-line diagnosis: daemon state, backend, workspace |
| `browser-cli reload` | **Runtime reset**: restart daemon and browser |
| `browser-cli page-reload` | Page action: reload current tab |
| `browser-cli stop` | Stop daemon and browser instance |

## Task & Workflow Packaging

Package reusable browser automation as versioned artifacts:

```text
tasks/
  my_task/
    task.py          # Implementation
    task.meta.json   # Metadata (inputs, outputs, version)
    workflow.toml    # Published workflow definition
```

### Example Task

```python
from browser_cli.task_runtime.flow import Flow

def run(flow: Flow, inputs: dict) -> dict:
    flow.open(inputs["url"])
    snapshot = flow.snapshot()
    ref = snapshot.find_ref(role="button", name="Submit")
    flow.click(ref)
    return {"html": flow.html()}
```

### Run Workflows

```bash
# Validate workflow
browser-cli workflow validate tasks/my_task/workflow.toml

# Execute with parameters
browser-cli workflow run tasks/my_task/workflow.toml --set url=https://example.com
```

**Included examples:**
- [`interactive_reveal_capture`](tasks/interactive_reveal_capture/task.py)
- [`lazy_scroll_capture`](tasks/lazy_scroll_capture/task.py)

## Explore Skill

For agent-driven exploration, install the skill from [`skills/browser-cli-explore-delivery/SKILL.md`](skills/browser-cli-explore-delivery/SKILL.md). It standardizes:

- Preflight checks and install approval
- Browser CLI-first exploration
- Convergence to `task.py + task.meta.json`

## Output Contracts

### `read`

- `stdout`: final result only
- `stderr`: diagnostics only

Exit codes:

- `0`: success
- `1`: unexpected internal error
- `2`: usage error
- `66`: empty content
- `69`: browser unavailable
- `73`: profile unavailable
- `75`: temporary read failure

### Daemon-backed commands

- success `stdout`: JSON only
- failure `stderr`: short error summary
- the daemon also returns stable machine-readable error codes such as:
  - `NO_ACTIVE_TAB`
  - `AGENT_ACTIVE_TAB_BUSY`
  - `TAB_NOT_FOUND`
  - `NO_SNAPSHOT_CONTEXT`
  - `REF_NOT_FOUND`
  - `STALE_SNAPSHOT`
  - `AMBIGUOUS_REF`

## Documentation

### Architecture Notes

- **Managed Profile Mode** — Default backend using Playwright with isolated Chrome profile at `~/.browser-cli/default-profile`
- **Extension Mode** — Real-Chrome backend via Chrome extension; controls dedicated workspace window only
- **Driver Rebinding** — Automatic backend switching at safe idle points, reported as `state_reset` in metadata
- **Agent Isolation** — `X_AGENT_ID` isolates tab visibility, but cookies/storage are shared within the same browser instance

### Response Metadata

| Field | Meaning |
|-------|---------|
| `meta.driver == "playwright"` | Command handled by managed profile backend |
| `meta.driver == "extension"` | Command handled by real-Chrome extension backend |
| `meta.state_reset == true` | Driver rebind occurred; old refs are invalid |

## Testing

Run the full suite with:

```bash
pytest -q
```

Run repository lint and architecture guards with:

```bash
python scripts/guards/python_compatibility.py
python scripts/guards/run_all.py
./scripts/lint.sh
./scripts/guard.sh
./scripts/check.sh
```

`python scripts/guards/python_compatibility.py` is the fastest local check for Python 3.10 compatibility when you are developing on a newer interpreter.

When the runtime behaves unexpectedly, use:

```bash
browser-cli status
browser-cli reload
browser-cli status
```

The integration coverage is fixture-driven and local-first. The suite uses a local HTTP fixture app that exercises:

- navigation, tabs, and history
- snapshot and rendered HTML capture
- semantic ref reconstruction after DOM re-render
- stale and ambiguous ref failure cases
- iframe ref reconstruction
- ref-based element actions
- keyboard and mouse actions
- waits, eval, and verification
- console, network, dialogs, trace, video, screenshot, and PDF
- cookies, localStorage save/load, and `X_AGENT_ID` isolation
- task runtime, workflow validation, and workflow execution against local fixtures

The action catalog also has a parity test that fails if the daemon-backed command surface drops below the current `bridgic-browser` catalog.

## Acknowledgements

This project is deeply inspired by and built upon the excellent work of [**bridgic-browser**](https://github.com/bitsky-tech/bridgic-browser), a Python library for LLM-driven browser automation created by [bitsky-tech](https://github.com/bitsky-tech).

**What we learned from bridgic-browser:**

- **Semantic Ref System** - bridgic-browser's innovative approach to element identification using stable refs that persist across page reloads
- **Snapshot Model** - The accessibility tree-based page representation with semantic invariance
- **CLI Design Patterns** - The daemon-backed architecture enabling fast, stateful browser control
- **Stealth Mode Implementation** - Anti-detection strategies for headless and headed browser modes
- **Comprehensive Tool Organization** - The 67-tool catalog spanning 15 categories that we aim to maintain parity with

We are grateful to the bridgic-browser team for pioneering many of the concepts that make browser-cli possible. This project stands on their shoulders while pursuing a CLI-first approach with additional layers for task packaging and workflow execution.
