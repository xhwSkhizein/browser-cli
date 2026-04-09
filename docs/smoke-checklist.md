# Smoke Checklist

Use this checklist before calling Browser CLI done on a real workstation.

## Environment

- Stable Google Chrome is installed.
- The target profile exists under the Chrome user data directory.
- `~/.browser-cli/default-profile` is available as the fallback profile root.

## Basic Checks

- `browser-cli --help`
- `browser-cli read https://example.com`
- `browser-cli read https://example.com --snapshot`
- `browser-cli read https://example.com --scroll-bottom`
- `browser-cli open https://example.com`
- `browser-cli tabs`
- `browser-cli snapshot`
- `browser-cli html`
- `browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml`
- `browser-cli stop`

## Multi-Agent Checks

- Run `X_AGENT_ID=agent-a browser-cli open https://example.com`.
- Run `X_AGENT_ID=agent-b browser-cli open https://example.org`.
- Run `X_AGENT_ID=agent-a browser-cli tabs`.
- Confirm only agent A tabs are visible.
- Run `X_AGENT_ID=agent-b browser-cli tabs`.
- Confirm only agent B tabs are visible.
- Confirm logging in under one agent is reflected under the other agent, because storage is shared.

## Authenticated Checks

- Open an already-authenticated site in normal Chrome first.
- Close Chrome.
- Run `browser-cli read <authenticated-url>`.
- Confirm the output reflects the logged-in state rather than a logged-out page.

## Daemon Checks

- Run `browser-cli open <authenticated-url>`.
- Run `browser-cli snapshot`.
- Run `browser-cli html`.
- Run `browser-cli info`.
- Run `browser-cli resize 1200 800`.
- Run `browser-cli stop`.
- Confirm the first command starts the daemon automatically and `stop` tears it down cleanly.

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
- Exercise one artifact flow: `screenshot`, `pdf`, `trace-start`, `trace-chunk`, `trace-stop`, `video-start`, `video-stop`, then close the tab and confirm the trace/video artifacts exist.
- Exercise one storage flow: `cookie-set`, `cookies`, `cookies-clear`, `storage-save`, `storage-load`.

## Task And Workflow Checks

- Run `browser-cli workflow validate tasks/interactive_reveal_capture/workflow.toml`.
- Run `browser-cli workflow run tasks/interactive_reveal_capture/workflow.toml --set url=<fixture-url>`.
- Confirm the workflow writes `artifacts/result.json`.
- Confirm the workflow-created HTML artifact contains the expected rendered content.
- Run the lazy-scroll task through Python or a temporary workflow and confirm it writes both HTML and round-history artifacts.

## Failure Checks

- Start normal Chrome and keep it open so the primary profile is locked.
- Run `browser-cli read https://example.com`.
- Confirm the command succeeds with a fallback-profile notice on `stderr`.
- Create a lock under `~/.browser-cli/default-profile`.
- Confirm the command now fails with a profile-unavailable error.
- Start one long-running command on an active tab, then issue another page-bound command with the same `X_AGENT_ID`.
- Confirm the second command fails with an explicit busy-tab error instead of silently waiting forever.
