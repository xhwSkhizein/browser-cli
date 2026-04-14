# Installed With UV

This guide is for users who install Browser CLI as a tool with uv, not for
repository maintainers working inside this checkout.

The first-day path should be:

1. Install Browser CLI with uv.
2. Run `browser-cli doctor`.
3. Run `browser-cli paths`.
4. Try `browser-cli read https://example.com`.
5. Create a task, then run `browser-cli task validate <task-dir>`.
6. Run `browser-cli task run <task-dir>`.
7. Publish with `browser-cli automation publish <task-dir>`.

## Recommended Starting Point

Start with managed profile mode. It is the default path and the fastest route
to first success. Only spend time on extension mode when you specifically need
real-Chrome behavior or extension-only fidelity.

## Install

Requirements:

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Stable Google Chrome

Typical install flow:

```bash
uv tool install browserctl
browser-cli doctor
browser-cli paths
```

The published package name is `browserctl`. The installed command remains
`browser-cli`.

If `browser-cli` is not on your shell `PATH`, inspect the tool bin directory
with:

```bash
uv tool dir --bin
```

## First Read

Use `read` to verify that Browser CLI can open a page and return output:

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

## One-Off Execution

If you do not want a persistent install, run Browser CLI directly with `uvx`:

```bash
uvx --from browserctl browser-cli read https://example.com
```

## Install From Git

Use a Git source when you want the latest repository version instead of the
latest published package:

```bash
uv tool install git+https://github.com/hongv/browser-cli.git
browser-cli --help
```

## Task Versus Automation

Keep one rule in mind everywhere:

- `task` is local editable source
- `automation` is a published immutable snapshot

Typical local task layout:

```text
my_task/
  task.py
  task.meta.json
  automation.toml
```

Validate and run a task locally:

```bash
browser-cli task validate my_task
browser-cli task run my_task --set url=https://example.com
```

## First Publish

Publish your local task when you want a durable automation snapshot:

```bash
browser-cli automation publish my_task
browser-cli automation list
browser-cli automation inspect <automation-id>
browser-cli automation status
browser-cli automation ui
```

Replace `<automation-id>` with the ID shown by `browser-cli automation list`.
After publish, use the automation CLI to inspect the published snapshot rather
than editing snapshot files directly.

## Remove Browser CLI

To remove Browser CLI later, including Browser CLI home data and local cleanup
steps for maintainers, see [`docs/uninstall.md`](docs/uninstall.md).
