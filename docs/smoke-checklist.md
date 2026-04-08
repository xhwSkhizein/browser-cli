# Smoke Checklist

Use this checklist before calling `v1` done on a real workstation.

## Environment

- Stable Google Chrome is installed.
- Regular Chrome is fully closed.
- The target profile exists under the Chrome user data directory.

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

- Start normal Chrome and keep it open.
- Run `browser-cli read https://example.com`.
- Confirm the command fails with a profile-unavailable error rather than silently using a new profile.

