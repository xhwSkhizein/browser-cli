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
  - the regular Chrome app fully closed before execution

## Install

```bash
python3 -m pip install -e .
python3 -m playwright install chromium
```

The CLI itself reuses stable Google Chrome for the real profile path. The Playwright Chromium install is mainly useful for local integration testing.

## Usage

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

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

- The CLI does not silently fall back to a fresh profile.
- If Chrome profile lock files are present, close Chrome and retry.
- `read` is intentionally small. More complex flows belong in a future workflow layer.

