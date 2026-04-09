# browser-cli

`browser-cli` is a `CLI-first`, `Python-first` browser tool with four connected layers:

- `read`: one-shot rendered page reading
- daemon-backed browser actions: long-lived browser control for agents
- semantic refs: bridgic-style ref reconstruction for resilient replay
- task/workflow runtime: reusable `task.py`, `task.meta.json`, and `workflow.toml`

## Status

Current scope now has four layers:

```bash
browser-cli read <url>
browser-cli read <url> --snapshot
browser-cli read <url> --scroll-bottom

browser-cli open https://example.com
browser-cli tabs
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli html

browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml
browser-cli workflow run tasks/interactive_reveal_capture/workflow.toml --set url=https://example.com
browser-cli stop
```

`read` stays content-first. The daemon-backed commands and workflow surface are JSON-first and are designed for agents and reusable delivery.

## Requirements

- Python 3.11+
- Playwright Python package
- Stable Google Chrome installed
- For the real profile-reuse path:
  - closing the regular Chrome app is preferred if you want to reuse the real Chrome profile directly

## Install

```bash
python3 -m pip install -e .
python3 -m playwright install chromium
```

The CLI itself targets stable Google Chrome. The Playwright Chromium install is mainly useful for local integration testing.

## Usage

### One-Shot Read

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

Default output is rendered DOM HTML. `--snapshot` returns a bridgic-style tree snapshot. `--scroll-bottom` performs an extra lazy-load pass before capture.

If the real Chrome profile is unavailable, `browser-cli` falls back to a managed profile root at `~/.browser-cli/default-profile`.

### Daemon-Backed Agent Actions

The first daemon-backed call auto-starts a local browser daemon. The daemon keeps one long-lived browser instance alive until you explicitly stop it.

```bash
browser-cli open https://example.com
browser-cli tabs
browser-cli snapshot
browser-cli html
browser-cli click @8d4b03a9
browser-cli stop
```

Agent isolation is controlled by `X_AGENT_ID`:

```bash
X_AGENT_ID=agent-a browser-cli open https://example.com
X_AGENT_ID=agent-a browser-cli tabs

X_AGENT_ID=agent-b browser-cli open https://example.org
X_AGENT_ID=agent-b browser-cli tabs
```

Tabs are isolated by `X_AGENT_ID`, but cookies and local storage are still shared because all commands reuse the same browser profile and browser instance.

Representative action families:

- navigation and page state: `open`, `search`, `info`, `html`, `snapshot`, `reload`, `back`, `forward`
- tab management and lifecycle: `tabs`, `new-tab`, `switch-tab`, `close-tab`, `close`, `resize`, `stop`
- ref actions: `click`, `double-click`, `hover`, `focus`, `fill`, `select`, `check`, `uncheck`, `scroll-to`, `drag`, `upload`
- keyboard, mouse, script, waits: `type`, `press`, `key-down`, `key-up`, `scroll`, `mouse-*`, `eval`, `eval-on`, `wait`, `wait-network`
- observation and state: `console-*`, `network-*`, `dialog-*`, `trace-*`, `video-*`, `screenshot`, `pdf`, `cookies`, `cookie-set`, `cookies-clear`, `storage-save`, `storage-load`
- verification: `verify-text`, `verify-visible`, `verify-url`, `verify-title`, `verify-state`, `verify-value`

Use `browser-cli -h` and per-command help like `browser-cli click -h` to inspect the full surface.

The daemon-backed action catalog is now kept in parity with the current `bridgic-browser` command surface. `browser-cli` intentionally adds two extra commands on top of that surface:

- `html`: return rendered DOM HTML for the active tab
- `stop`: stop the local daemon and shared browser instance

Semantic refs now use bridgic-style reconstruction rather than DOM-injected `data-*` markers. This means:

- refs remain stable across DOM re-renders when page semantics stay the same
- stale and ambiguous ref failures are explicit
- iframe-local refs are reconstructed against the correct frame path

## Task Runtime And Workflow Packaging

Reusable task artifacts now live under [`tasks/`](/Users/hongv/workspace/m-projects/browser-cli/tasks).

Representative layout:

```text
tasks/
  interactive_reveal_capture/
    task.py
    task.meta.json
    workflow.toml
```

`task.py` uses the thin Python runtime:

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    flow.open(inputs["url"])
    snapshot = flow.snapshot()
    ref = snapshot.find_ref(role="button", name="Reveal Message")
    flow.click(ref)
    flow.wait_text("Revealed", timeout=5)
    return {"html": flow.html()}
```

`workflow.toml` is the published wrapper around a task. Validate and run it with:

```bash
browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml
browser-cli workflow run tasks/interactive_reveal_capture/workflow.toml --set url=https://example.com
```

The included reference tasks are:

- [`interactive_reveal_capture`](/Users/hongv/workspace/m-projects/browser-cli/tasks/interactive_reveal_capture/task.py)
- [`lazy_scroll_capture`](/Users/hongv/workspace/m-projects/browser-cli/tasks/lazy_scroll_capture/task.py)

Reusable task scaffolds live under [`tasks/_templates/`](/Users/hongv/workspace/m-projects/browser-cli/tasks/_templates/task.py).

## Explore Skill

A reusable skill for agent-driven exploration now lives in:

- repo source: [`skills/browser-cli-explore-delivery/SKILL.md`](/Users/hongv/workspace/m-projects/browser-cli/skills/browser-cli-explore-delivery/SKILL.md)
- installed discovery path: `/Users/hongv/.agents/skills/browser-cli-explore-delivery`

The skill standardizes:

- preflight checks
- install approval gating
- Browser CLI-first exploration
- convergence into `task.py + task.meta.json`
- optional publish gating for `workflow.toml`

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

## Notes

- If the real Chrome profile is unavailable or locked, the CLI falls back to `~/.browser-cli/default-profile`.
- If both the real profile and the fallback profile are unavailable, the command fails.
- `read` is intentionally small. More complex flows belong in the daemon-backed action layer and future exploration/workflow layers.
- The daemon uses one shared browser instance. `X_AGENT_ID` isolates tab visibility and active-tab state only, not storage.

## Testing

Run the full suite with:

```bash
pytest -q
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
