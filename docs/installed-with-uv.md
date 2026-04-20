# Installed With UV

This guide is for users who install Browser CLI as a tool with uv, not for
repository maintainers working inside this checkout.

The first-day path should be:

1. Install Browser CLI with uv.
2. Run `browser-cli doctor`.
3. Run `browser-cli paths`.
4. Optionally run `browser-cli install-skills`.
5. Try `browser-cli read https://example.com`.
6. Run `browser-cli task examples` to see the shipped reference tasks.
7. Scaffold a local task bundle with `browser-cli task template --output <task-dir>`.
8. Validate it with `browser-cli task validate <task-dir>`.
9. Execute it with `browser-cli task run <task-dir>`.
10. Publish it with `browser-cli automation publish <task-dir>`.

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
uv tool install browser-control-and-automation-cli
browser-cli doctor
browser-cli paths
```

The published package name is `browser-control-and-automation-cli`. The
installed command remains `browser-cli`.

If `browser-cli` is not on your shell `PATH`, inspect the tool bin directory
with:

```bash
uv tool dir --bin
```

## Install Browser CLI Skills

Use `install-skills` when you want Browser CLI to copy its packaged skills into
your agent skills directory.

Install the packaged skills into the default target:

```bash
browser-cli install-skills
```

By default, the command writes to `~/.agents/skills`. Preview the result
without writing files:

```bash
browser-cli install-skills --dry-run
```

Choose a different destination root with `--target`:

```bash
browser-cli install-skills --target ~/.codex/skills
```

Browser CLI currently installs exactly three packaged skills:

- `browser-cli-converge`
- `browser-cli-delivery`
- `browser-cli-explore`

If the target already contains those skill directories, Browser CLI replaces
them with the packaged versions from the installed distribution. For a longer
walkthrough, see [`install-skills.md`](install-skills.md).

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
uvx --from browser-control-and-automation-cli browser-cli read https://example.com
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

Discover the shipped examples:

```bash
browser-cli task examples
```

Scaffold a new task bundle:

```bash
browser-cli task template --output my_task
```

`task template` writes `task.py`, `task.meta.json`, and `automation.toml`
together so the local source and publish-time config start from one coherent
bundle.

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
steps for maintainers, see [`uninstall.md`](uninstall.md). In the repository
tree, that guide lives at `docs/uninstall.md`.
