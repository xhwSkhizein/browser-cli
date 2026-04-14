# Browser CLI Uninstall Doc Design

Date: 2026-04-14
Status: Drafted for review
Repo: `/home/hongv/workspace/browser-cli`

## Summary

This spec adds a maintainer-oriented uninstall guide for Browser CLI.

The new documentation should cover:

- complete removal of the repository development environment
- complete removal of Browser CLI runtime data under the Browser CLI home
- optional removal of any uv tool installation
- backup guidance for high-value local task and automation data before deletion

The guide is not primarily an installed-user quick-uninstall note. It is a
full cleanup document for maintainers and developers who may have both a local
repository checkout and Browser CLI runtime state on the same machine.

## Problem Statement

The repository currently documents installation and first-run guidance, but it
does not document how to remove Browser CLI cleanly.

Current docs include:

- `README.md`
- `docs/installed-with-uv.md`
- `docs/installed-with-pip.md`

Those docs explain install and migration paths, but they do not explain:

- which runtime paths Browser CLI actually owns
- how to stop the daemon and automation service before deletion
- how to remove the repo-local development environment
- how to distinguish uninstalling the uv tool from deleting Browser CLI home
  data
- how to avoid accidentally deleting high-value task and automation data

Without an uninstall guide, maintainers have to infer removal steps from the
source code and path layout.

## Goals

- Add a single uninstall document for Browser CLI.
- Make the primary audience repository maintainers and developers.
- Default to a full uninstall path rather than a minimal uninstall path.
- Warn users to back up high-value Browser CLI home data before deletion.
- Use only commands and paths that exist in the current implementation.
- Clarify the difference between:
  - runtime cleanup
  - repo development-environment cleanup
  - Browser CLI home deletion
  - uv tool uninstall

## Non-Goals

- This spec does not add a new `browser-cli uninstall` command.
- This spec does not redesign Browser CLI runtime storage.
- This spec does not make installed-user removal the primary focus.
- This spec does not automate backups.

## Current Implementation Constraints

The uninstall doc must align with current code behavior.

### Runtime Path Model

`src/browser_cli/constants.py` defines the Browser CLI home and its owned
paths.

Relevant paths include:

- `home`
- `run/`
- `artifacts/`
- `tasks/`
- `automations/`
- `automations.db`
- daemon log and run-info files
- automation-service log and run-info files

The home path is:

- `BROWSER_CLI_HOME` when set
- otherwise `~/.browser-cli`

The uninstall guide must therefore tell users to discover the real home path
before deleting anything.

### Discovery Commands

The current implementation already exposes the right discovery surfaces:

- `browser-cli paths`
- `browser-cli status`

`paths` exposes the canonical filesystem paths that matter for cleanup.
`status` exposes runtime state and helps users understand whether daemon or
automation processes are still active.

### Runtime Cleanup Surfaces

The current implementation provides:

- `browser-cli automation stop`
- `browser-cli reload`

These are runtime cleanup tools, not uninstall commands.

The uninstall doc must explain that:

- `automation stop` is used to stop the automation service and clear stale
  runtime metadata
- `reload` is used to reset daemon runtime state before deletion
- final uninstall still depends on deleting directories and files

## Chosen Direction

Add a new document:

- `docs/uninstall.md`

This document should be the primary uninstall reference and should be linked
from:

- `README.md`
- `docs/installed-with-uv.md`

The document should be structured around a full cleanup flow, but it should
also call out narrower removal cases inside that flow.

## Documentation Structure

The uninstall guide should use this structure.

### 1. Summary

Explain that the document targets full removal for maintainers and local
developers.

Clarify that full removal can include:

- repo-local development environment cleanup
- Browser CLI home deletion
- optional uv tool uninstall

### 2. Before You Delete Anything

Require users to inspect current state first:

```bash
browser-cli paths
browser-cli status
```

Explain why this matters:

- Browser CLI home may not be `~/.browser-cli`
- active daemon or automation-service processes may still exist

### 3. Back Up What You Want To Keep

Explicitly list high-value paths:

- `tasks_dir`
- `automations_dir`
- `automation_db_path`
- optionally `artifacts_dir`

Explain that deleting Browser CLI home removes local task sources, published
automation snapshots, and automation persistence.

### 4. Stop Runtime Processes

Use only existing commands:

```bash
browser-cli automation stop
browser-cli reload
```

Explain that these commands reduce residual runtime state before deletion but do
not by themselves uninstall Browser CLI.

### 5. Remove The Repository Development Environment

Provide commands for maintainers working inside the repository checkout, such as
removing:

- `.venv`
- `.pytest_cache`
- `__pycache__` directories

Make it explicit that this step only affects the checkout, not Browser CLI home.

### 6. Remove Browser CLI Home Data

Tell users to delete the home path reported by `browser-cli paths`.

Use `~/.browser-cli` only as the default example, not as the sole target.

The doc must explain that removing Browser CLI home deletes:

- run state
- logs
- artifacts
- local tasks
- published automations
- automation database
- managed-profile runtime state stored there

### 7. Optional: Remove uv Tool Installation

Include:

```bash
uv tool uninstall browser-cli
```

Explain that this only removes the installed CLI tool and does not remove:

- the repository checkout
- Browser CLI home data

### 8. Verify Removal

Show how to verify that:

- the repo development environment is gone
- Browser CLI home is gone
- any optional uv tool install has been removed

The doc should avoid assuming that `browser-cli` is still available after the
user removes the tool install.

## Required Warnings

The uninstall doc must explicitly warn about these four cases:

1. Deleting Browser CLI home deletes high-value local task and automation data.
2. `browser-cli reload` is runtime cleanup, not uninstall.
3. `BROWSER_CLI_HOME` changes the deletion target.
4. `uv tool uninstall browser-cli` does not remove Browser CLI home or the repo
   checkout.

## Related Documentation Changes

`README.md` should gain a link to `docs/uninstall.md`.

`docs/installed-with-uv.md` should also point to `docs/uninstall.md` so
installed users can still find the removal guide even though the guide is
maintainer-oriented.

## Acceptance Criteria

This design is complete when:

- `docs/uninstall.md` exists
- the guide is based on current Browser CLI commands and paths
- the guide defaults to full cleanup for maintainers
- the guide warns users to back up task and automation data first
- `README.md` links to the guide
- `docs/installed-with-uv.md` links to the guide
