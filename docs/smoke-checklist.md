# Smoke Checklist

Use this checklist before calling Browser CLI done on a real workstation.

## Environment

- Stable Google Chrome is installed.
- Browser CLI managed profile root exists at `~/.browser-cli/default-profile`.
- If testing extension mode, the unpacked extension from `browser-cli-extension/` is loaded in Chrome developer mode.

## Basic Checks

- `browser-cli --help`
- `browser-cli status`
- `browser-cli read https://example.com`
- `browser-cli read https://example.com --snapshot`
- `browser-cli read https://example.com --scroll-bottom`
- `browser-cli reload`
- `browser-cli open https://example.com`
- `browser-cli tabs`
- `browser-cli snapshot`
- `browser-cli html`
- `browser-cli page-reload`
- `browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml`
- `browser-cli stop`
- Confirm `browser-cli read ...` does not leave an extra visible tab behind after it exits.
- Confirm the JSON metadata for daemon-backed commands includes `meta.driver`.

## Multi-Agent Checks

- Run `X_AGENT_ID=agent-a browser-cli open https://example.com`.
- Run `X_AGENT_ID=agent-b browser-cli open https://example.org`.
- Run `X_AGENT_ID=agent-a browser-cli tabs`.
- Confirm only agent A tabs are visible.
- Run `X_AGENT_ID=agent-b browser-cli tabs`.
- Confirm only agent B tabs are visible.
- Confirm logging in under one agent is reflected under the other agent, because storage is shared.

## Managed Profile Checks

- Run `browser-cli open <authenticated-or-test-url>`.
- Confirm Browser CLI starts from its managed profile without touching the primary Chrome user data directory.
- Log in manually inside the Browser CLI window if needed.
- Run `browser-cli read <authenticated-url>` again and confirm the output reflects the managed-profile login state.

## Extension Mode Checks

- Load the unpacked extension from `browser-cli-extension/`.
- Open the extension popup and confirm it reports a healthy runtime summary once the daemon is up.
- Run `browser-cli status` and confirm the backend section shows whether any required extension capabilities are missing.
- Confirm the popup summary, execution path, workspace ownership, and recovery sections reflect the same daemon state class as `browser-cli status`.
- Run `browser-cli open https://example.com`.
- Confirm Browser CLI creates or reuses a dedicated workspace window rather than attaching to arbitrary user tabs.
- Confirm the response metadata reports `meta.driver = extension`.
- Disable the extension or disconnect it, then issue another command.
- Confirm Browser CLI falls back at a safe idle point and the response metadata reports `meta.state_reset = true`.

## Popup Runtime Checks

- Open the Browser CLI extension popup while extension mode is healthy.
- Confirm the popup shows `Runtime Summary`, `Workspace Ownership`, `Recovery`, and `Daemon Config`.
- Disconnect the extension and confirm the popup reports a recovering or degraded runtime state rather than only `disconnected`.
- Confirm `Refresh Status` updates the runtime summary without mutating Browser CLI state.
- Confirm `Reconnect Extension` retries the extension transport and refreshes the runtime snapshot.
- Confirm `Rebuild Workspace` only rebuilds Browser CLI-owned workspace state and does not touch arbitrary user tabs.

## Daemon Checks

- Run `browser-cli status`.
- Confirm it prints a clear runtime summary and guidance section.
- Run `browser-cli reload`.
- Confirm it restarts Browser CLI and prints a refreshed status block.
- Run `browser-cli open <authenticated-url>`.
- Run `browser-cli snapshot`.
- Run `browser-cli html`.
- Run `browser-cli info`.
- Run `browser-cli page-reload`.
- Run `browser-cli resize 1200 800`.
- Run `browser-cli stop`.
- Confirm the first command starts the daemon automatically and `stop` tears it down cleanly.
- If the extension is loaded, confirm the daemon prefers `extension` over `playwright` after a safe idle point.

## Troubleshooting Checks

- With the daemon stopped, run `browser-cli status` and confirm it reports `Status: stopped`.
- Start Browser CLI, then run `browser-cli status` again and confirm it reports a live backend state.
- If the runtime gets wedged, run `browser-cli reload` and confirm Browser CLI returns to a usable state without touching arbitrary user tabs.

## Semantic Ref Checks

- Open a page that can re-render the same semantic target.
- Capture `browser-cli snapshot`.
- Click a ref, trigger a DOM re-render that preserves the role/name, then click the same ref again.
- Confirm the second click still succeeds without a fresh snapshot.
- Trigger a semantic rename and confirm the old ref now fails explicitly.
- Trigger duplicate matching semantics and confirm the old ref fails with an ambiguity error.
- Open a page with an iframe, capture `snapshot`, then click an iframe-local ref and confirm it resolves correctly.

## Action Surface Checks

- Exercise one ref-driven form flow: `snapshot`, then `fill`, `select`, `check`, `verify-value`, `verify-state`.
- Exercise one keyboard/mouse flow: `focus`, `type`, `press`, `mouse-click`, `scroll`.
- Exercise one observation flow: `console-start`, `network-start`, perform a click, then `console`, `network`, `console-stop`, `network-stop`.
- Exercise one dialog flow: `dialog-setup` or `dialog`, then trigger `alert`, `confirm`, or `prompt`.
- Exercise one artifact flow: `screenshot`, `pdf`, then confirm the artifacts exist.
- Exercise one trace flow: `trace-start`, perform a page action, `trace-chunk`, `trace-stop`, then confirm the `.zip` exists and includes `trace.trace`, `trace.network`, `trace.console`, and `trace.metadata.json`.
- Exercise one video flow: `video-start`, perform a page action, `video-stop`, then `close-tab` and confirm the deferred `.webm` is written from the extension screencast pipeline.
- Exercise one storage flow: `cookie-set`, `cookies`, `cookies-clear`, `storage-save`, `storage-load`.

## Task And Workflow Checks

- Run `browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml`.
- Run `browser-cli workflow run tasks/interactive_reveal_capture/workflow.toml --set url=<fixture-url>`.
- Confirm the workflow writes `artifacts/result.json`.
- Confirm the workflow-created HTML artifact contains the expected rendered content.
- Run the lazy-scroll task through Python or a temporary workflow and confirm it writes both HTML and round-history artifacts.

## Failure Checks

- Create a lock under `~/.browser-cli/default-profile`.
- Confirm `browser-cli read https://example.com` now fails with a profile-unavailable error.
- Start one long-running command on an active tab, then issue another page-bound command with the same `X_AGENT_ID`.
- Confirm the second command fails with an explicit busy-tab error instead of silently waiting forever.
- While the extension backend is active, disconnect the extension mid-session.
- Confirm the current in-flight command is not interrupted, but the next safe-point response reports a `state_reset` downgrade.
