# browser-cli

`browser-cli` is a `CLI-first`, `Python-first` browser tool with two surfaces:

- `read`: one-shot rendered page reading
- daemon-backed browser actions: long-lived browser control for agents

## Status

Current scope now has two layers:

```bash
browser-cli read <url>
browser-cli read <url> --snapshot
browser-cli read <url> --scroll-bottom

browser-cli open https://example.com
browser-cli tabs
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli html
browser-cli stop
```

`read` stays content-first. The daemon-backed commands are JSON-first and are designed for agents.

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
  - `REF_NOT_FOUND`
  - `STALE_SNAPSHOT`

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
- ref-based element actions
- keyboard and mouse actions
- waits, eval, and verification
- console, network, dialogs, trace, video, screenshot, and PDF
- cookies, localStorage save/load, and `X_AGENT_ID` isolation

The action catalog also has a parity test that fails if the daemon-backed command surface drops below the current `bridgic-browser` catalog.
