# Smoke Checklist

Use this checklist before calling `v1` done on a real workstation.

## Environment

- Stable Google Chrome is installed.
- The target profile exists under the Chrome user data directory.
- `~/.browser-cli/default-profile` is available as the fallback profile root.

## Basic Checks

- `browser-cli --help`
- `browser-cli read https://example.com`
- `browser-cli read https://example.com --snapshot`
- `browser-cli read https://example.com --scroll-bottom`

## Authenticated Checks

- Open an already-authenticated site in normal Chrome first.
- Close Chrome.
- Run `browser-cli read <authenticated-url>`.
- Confirm the output reflects the logged-in state rather than a logged-out page.

## Failure Checks

- Start normal Chrome and keep it open so the primary profile is locked.
- Run `browser-cli read https://example.com`.
- Confirm the command succeeds with a fallback-profile notice on `stderr`.
- Create a lock under `~/.browser-cli/default-profile`.
- Confirm the command now fails with a profile-unavailable error.
