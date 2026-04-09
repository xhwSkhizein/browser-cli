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
- Run `browser-cli stop`.
- Confirm the first command starts the daemon automatically and `stop` tears it down cleanly.

## Failure Checks

- Start normal Chrome and keep it open so the primary profile is locked.
- Run `browser-cli read https://example.com`.
- Confirm the command succeeds with a fallback-profile notice on `stderr`.
- Create a lock under `~/.browser-cli/default-profile`.
- Confirm the command now fails with a profile-unavailable error.
- Start one long-running command on an active tab, then issue another page-bound command with the same `X_AGENT_ID`.
- Confirm the second command fails with an explicit busy-tab error instead of silently waiting forever.
