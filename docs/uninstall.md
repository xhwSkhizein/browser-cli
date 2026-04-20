# Uninstall Browser CLI

This guide is for repository maintainers and local developers who want to fully
remove Browser CLI from a machine. It covers:

- stopping Browser CLI runtime processes
- backing up high-value local data first
- removing the repository development environment
- removing Browser CLI home data
- optionally removing any uv tool installation

## Before You Delete Anything

Inspect the current Browser CLI runtime paths and status first:

```bash
browser-cli paths
browser-cli status
```

If you set `BROWSER_CLI_HOME`, Browser CLI home may not be `~/.browser-cli`.
Use the `home` path shown by `browser-cli paths` as the deletion target.

## Back Up What You Want To Keep

Before deleting Browser CLI home, consider backing up these paths from
`browser-cli paths`:

- `tasks_dir`
- `automations_dir`
- `automation_db_path`
- optionally `artifacts_dir`

Deleting Browser CLI home removes any task source stored under the Browser CLI
home `tasks/` directory, published automation snapshots, automation
persistence, runtime logs, and artifacts.

## Stop Runtime Processes

Stop the automation service and clear daemon runtime state before deleting files:

```bash
browser-cli automation stop
browser-cli reload
```

`browser-cli reload` is runtime cleanup, not uninstall. It resets Browser CLI
state before deletion, but it does not remove Browser CLI files by itself.

## Remove The Repository Development Environment

From the repository root, remove the local development environment:

```bash
rm -rf .venv
rm -rf .pytest_cache
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
```

This step only removes repo-local development state. It does not remove Browser
CLI home data.

## Remove Browser CLI Home Data

Delete the Browser CLI home reported by `browser-cli paths`. The default path is
usually:

```bash
rm -rf ~/.browser-cli
```

If `browser-cli paths` showed a different `home`, delete that path instead.

Removing Browser CLI home deletes:

- `run/` runtime state and logs
- `artifacts/`
- `tasks/`
- `automations/`
- `automations.db`
- managed-profile runtime state stored under Browser CLI home

## Optional: Remove uv Tool Installation

If you also installed Browser CLI as a uv tool, remove it separately:

```bash
uv tool uninstall browser-control-and-automation-cli
```

This does not remove:

- the repository checkout
- Browser CLI home data

## Verify Removal

Verify repo-local cleanup:

```bash
test ! -d .venv && echo "repo venv removed"
```

Verify Browser CLI home removal by checking the path you identified earlier:

```bash
test ! -d ~/.browser-cli && echo "browser-cli home removed"
```

If you used a custom `BROWSER_CLI_HOME`, replace `~/.browser-cli` with the
actual `home` path shown by `browser-cli paths`.
