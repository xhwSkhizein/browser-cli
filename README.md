# browser-cli

`browser-cli` is a `CLI-first`, `Python-first` browser reader for turning rendered web pages into command-line-readable output.

## Status

Current scope is intentionally narrow:

```bash
browser-cli read <url>
browser-cli read <url> --snapshot
browser-cli read <url> --scroll-bottom
```

Default output is rendered DOM HTML. `--snapshot` returns a bridgic-style tree snapshot. `--scroll-bottom` performs an extra lazy-load pass before capture.

## Requirements

- Python 3.11+
- Playwright Python package
- Playwright browser runtime or a locally installed Chrome
- For the real profile-reuse path:
  - stable Google Chrome installed
  - closing the regular Chrome app is preferred if you want to reuse the real Chrome profile directly

## Install

```bash
python3 -m pip install -e .
python3 -m playwright install chromium
```

The CLI itself targets stable Google Chrome. The Playwright Chromium install is mainly useful for local integration testing.

## Usage

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

If the real Chrome profile is unavailable, `browser-cli` falls back to a managed profile root at `~/.browser-cli/default-profile`.

## Output Contract

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

## Notes

- If the real Chrome profile is unavailable or locked, the CLI falls back to `~/.browser-cli/default-profile`.
- If both the real profile and the fallback profile are unavailable, the command fails.
- `read` is intentionally small. More complex flows belong in a future workflow layer.
