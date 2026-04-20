# Migrating From Pip To UV

Browser CLI is now uv-first for installation and execution.

If you previously used pip, move to one of these flows:

```bash
uv tool install browser-control-and-automation-cli
browser-cli --help
```

or:

```bash
uvx --from browser-control-and-automation-cli browser-cli --help
```

The current installed-user guide lives at
[`installed-with-uv.md`](installed-with-uv.md).
