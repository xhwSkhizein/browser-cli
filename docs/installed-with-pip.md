# Migrating From Pip To UV

Browser CLI now documents uv as the primary installation and execution path.

If you previously used pip, move to one of these flows:

```bash
uv tool install browser-cli
browser-cli --help
```

or:

```bash
uvx browser-cli --help
```

The current installed-user guide lives at
[`docs/installed-with-uv.md`](docs/installed-with-uv.md).
