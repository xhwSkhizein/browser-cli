# Installed With Pip

This guide is for users who installed Browser CLI as a tool, not for repository
maintainers working inside this checkout.

The first-day path should be:

1. Install Browser CLI and its runtime prerequisites.
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
- Stable Google Chrome
- Playwright Python package

Typical install flow:

```bash
python3 -m pip install browser-cli
python3 -m pip install playwright
python3 -m playwright install chromium
browser-cli doctor
browser-cli paths
```

## First Read

Use `read` to verify that Browser CLI can open a page and return output:

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

If a command fails, Browser CLI should print a short `Next:` hint. For a fuller
environment check, re-run `browser-cli doctor`.

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
