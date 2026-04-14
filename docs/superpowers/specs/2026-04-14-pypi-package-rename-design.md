# Browser CLI PyPI Package Rename Design

Date: 2026-04-14
Status: Approved for implementation
Repo: `/home/hongv/workspace/browser-cli`

## Summary

Browser CLI should stop publishing under `browserctl` and instead publish under
`browser-control-and-automation-cli`.

This rename is limited to the distribution layer:

- change the PyPI package name
- keep the installed CLI command as `browser-cli`
- keep the import package as `browser_cli`
- update all user-facing install, reinstall, and uninstall instructions
- update repo guards and tests that lock the published-name contract

## Problem Statement

The current published package name has already conflicted with existing PyPI
names often enough to block or complicate publishing. Reusing another short,
generic package name would likely recreate the same problem.

The project needs a deliberately long and distinctive distribution name while
preserving the product surface users already invoke locally.

## Goals

- Publish with a name that is far less likely to collide on PyPI.
- Preserve `browser-cli` as the installed executable name.
- Preserve `browser_cli` as the Python package path.
- Keep repo scripts, docs, tests, and guards consistent with the new name.
- Regenerate lock metadata so local development installs use the renamed root
  package.

## Non-Goals

- No rename of the repository directory.
- No rename of the CLI executable.
- No rename of the Python import package.
- No change to Browser CLI home paths, environment variables, daemon protocol,
  or command catalog.

## Options Considered

### 1. Keep chasing short generic names

Advantages:

- shorter install commands

Disadvantages:

- high collision risk on PyPI
- repeats the current failure mode

Rejected.

### 2. Add an owner prefix

Advantages:

- strong uniqueness

Disadvantages:

- user explicitly does not want owner-prefixed branding

Rejected for this change.

### 3. Use a long descriptive distribution name

Advantages:

- substantially lower collision risk
- preserves product branding through the unchanged `browser-cli` command
- requires only packaging and documentation changes

Chosen.

## Chosen Direction

Set `[project].name` to `browser-control-and-automation-cli` and propagate that
exact string anywhere the repository describes installation, reinstallation,
uninstallation, or editable-package refresh.

The durable contract after this change is:

- publish as `browser-control-and-automation-cli`
- install and run as `browser-cli`
- import from `browser_cli`

## Affected Surfaces

- `pyproject.toml`
- `uv.lock`
- install and uninstall documentation
- `scripts/test.sh`
- guard expectations in `scripts/guards/docs_sync.py`
- repo text-contract tests
- doctor guidance strings
- `AGENTS.md` durable packaging guidance

## Validation

- run `uv lock`
- run `uv sync --dev --reinstall-package browser-control-and-automation-cli`
- run `scripts/lint.sh`
- run `scripts/test.sh`
- run `scripts/guard.sh`
