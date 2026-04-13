# Browser CLI Pip User UX Roadmap Design

Date: 2026-04-13
Status: Drafted for review
Repo: `browser-cli`

## Summary

This design turns the existing `pip` user UX backlog into a phased product
roadmap.

The primary optimization target is first-day success for a user who installs
Browser CLI with `pip` outside this repository and wants to:

- verify that the environment is usable
- understand where Browser CLI stores local state
- run a first command successfully
- create and validate a local task
- recover from common failures without reading source code

The roadmap should therefore prioritize user-journey milestones rather than
isolated subsystem work. The recommended sequencing is:

1. install and first success
2. first task delivery
3. published automation observability

## Problem Statement

The current product shape is much clearer after the `task` and `automation`
cutover, but the remaining UX still assumes too much repository context for a
`pip` user.

The current gaps are:

- first-run setup and diagnosis are still too implicit
- runtime paths are not discoverable enough from the CLI
- task examples and templates are not discoverable enough
- common failures do not always tell the user the next recovery step
- publish succeeds without making the snapshot model obvious enough
- published automation state is not observable enough from the CLI

These gaps create friction at three key moments:

1. immediately after install
2. while creating and publishing the first task
3. after publish, when trying to understand what now exists in the automation
   service

## Goals

- Optimize for `pip` user first-day success.
- Organize improvements around the user journey rather than code ownership.
- Make diagnostic, discovery, and recovery commands explicit and easy to find.
- Reinforce one stable mental model:
  - `task` is local editable source
  - `automation` is a published immutable snapshot
- Keep managed profile mode as the default first-run path.
- Preserve existing CLI and daemon architectural boundaries.
- Keep machine-readable surfaces available through structured output.

## Non-Goals

- No second browser runtime.
- No magical bootstrap command that silently mutates user environment state.
- No reintroduction of `workflow` terminology.
- No requirement to add `task init` in this roadmap.
- No attempt to solve full automation run-control and history UX before first
  publish observability is in place.

## Options Considered

### 1. Roadmap by user journey

Structure:

- Phase 1: install and first success
- Phase 2: first task delivery
- Phase 3: published automation operations

Advantages:

- matches the new-user path directly
- makes prioritization defensible
- keeps docs, help text, and commands aligned around the same milestones

Disadvantages:

- requires reordering some items from the raw backlog
- mixes docs and CLI work inside the same phase

Chosen direction.

### 2. Roadmap by implementation cost

Structure:

- docs and help text first
- low-cost CLI output tweaks next
- larger commands later

Advantages:

- easy to start
- low short-term delivery risk

Disadvantages:

- improves wording before product discovery surfaces are in place
- does not produce a coherent first-day user experience

Rejected.

### 3. Roadmap by subsystem ownership

Structure:

- CLI phase
- task authoring phase
- automation service phase
- docs phase

Advantages:

- clean ownership handoff
- suitable for larger parallel teams

Disadvantages:

- does not match the user journey
- produces internally tidy phases with weaker user-facing outcomes

Rejected.

## Chosen Direction

Browser CLI should deliver the `pip` user UX backlog as a three-phase roadmap
centered on first-day success.

### Phase 1: Install And First Success

This phase answers four questions for a new user:

- is my install usable
- where does Browser CLI put files
- what should I run first
- what should I do when the first command fails

This phase includes:

- `browser-cli doctor`
- `browser-cli paths`
- a dedicated pip-user quickstart doc
- action-oriented `Next:` recovery hints for common failures
- explicit guidance to start with managed profile mode before extension mode

This phase does not include publish observability commands because those do not
block first-day success.

### Phase 2: First Delivery

This phase helps a user move from local editable task source to the first
published automation without repository-local assumptions.

This phase includes:

- `browser-cli task examples`
- `browser-cli task template --print`
- optional `browser-cli task template --output <dir>`
- stronger `automation publish` success output
- repeated help copy that reinforces the `task` vs `automation` distinction

This phase intentionally does not introduce `task init`.

### Phase 3: Published Automation Operations

This phase makes the publish result observable from the CLI.

This phase includes:

- `browser-cli automation list`
- `browser-cli automation versions <automation-id>`
- `browser-cli automation inspect <automation-id> [--version N]`

The goal is to let users answer:

- what did I publish
- which version exists
- where is the snapshot
- what is the latest known runtime status

## Cutting Rule

Phase assignment should follow one rule:

- if an issue blocks first-day success, ship it earlier
- if an issue happens mainly after publish, ship it later
- docs, help text, and output wording should ship with the matching journey
  milestone rather than as a separate documentation-only phase

## UX Principles

### 1. Prefer explicit next steps over passive diagnosis

User-facing surfaces should tell the user what to do next, not just describe the
state of the system.

Applications:

- `doctor` failures must include concrete recovery actions
- common errors should append `Next: ...`
- `publish` success should include follow-up commands
- quickstart content should be a runnable sequence, not a conceptual overview

### 2. Treat `~/.browser-cli` as a product surface

For a `pip` user, the Browser CLI home is part of the product contract rather
than a hidden implementation detail.

Applications:

- `paths` should reveal canonical runtime locations
- docs should explain the default filesystem layout explicitly
- error messages may reference these paths directly when useful

### 3. Reinforce one mental model everywhere

The core model must remain stable across CLI help, docs, and success output:

- `task` is local editable source
- `automation` is a published immutable snapshot

Applications:

- help text should repeat this distinction
- quickstart should repeat this distinction
- `automation publish` output should repeat this distinction

### 4. Start with managed profile mode

Extension mode should remain opt-in guidance for cases that truly need
real-Chrome fidelity. It should not dominate the first-run path.

Applications:

- quickstart should begin with managed profile mode
- `doctor` should treat missing extension connectivity as warning-level unless
  the user explicitly depends on it
- docs should explain when extension mode is worth enabling

### 5. Separate discovery from mutation

New users should be able to inspect and understand the system before issuing
mutating commands.

Applications:

- `doctor`, `paths`, `task examples`, and `automation inspect` should be safe
  read-only surfaces
- `publish`, `import`, and `stop` remain the main mutating automation commands

### 6. Keep JSON-first compatibility

These improvements should primarily improve human understanding without breaking
the agent-first nature of the product.

Applications:

- new discovery commands should support `--json` where structured automation is
  useful
- success and failure rendering should keep stable machine-readable fields where
  the surrounding command family already expects them

### 7. Organize docs by user sequence

Docs for installed users should mirror the order of real actions rather than
the package structure.

Applications:

- quickstart should follow `doctor -> paths -> read -> task validate -> task run
  -> automation publish`
- docs should minimize repository-maintainer assumptions

## Command-Level Design

### `browser-cli doctor`

Purpose:

- single first-run diagnostic entrypoint

Checks should be grouped by stable sections:

- package
- browser
- runtime
- automation
- extension

Recommended checks:

- Python package importability
- CLI entrypoint availability
- stable Google Chrome discovery
- Browser CLI home path readiness
- managed profile directory access
- Playwright/runtime readiness
- daemon reachability or startup readiness
- automation service status
- extension reachability and capability state, when configured or connected

Output rules:

- default output is compact and human-readable
- each check reports `pass`, `warn`, or `fail`
- `warn` is used for non-blocking conditions such as extension not connected
- every `fail` includes a `Next:` action
- `--json` returns structured check results

Acceptance:

- a new user can run `browser-cli doctor` after install and understand whether
  Browser CLI is ready for `read`, `task`, and `automation` usage
- common first-day problems map to explicit checks and concrete next steps

### `browser-cli paths`

Purpose:

- canonical filesystem discovery for installed users

Recommended output keys:

- `home`
- `tasks_dir`
- `automations_dir`
- `artifacts_dir`
- `daemon_log_path`
- `automation_db_path`
- `automation_service_run_info_path`
- `automation_service_log_path`

Output rules:

- default output is human-readable key/value text
- `--json` returns stable field names
- paths should be resolved product paths rather than repo-relative development
  assumptions

Acceptance:

- users can find the Browser CLI home, task workspace, published automations,
  logs, and artifacts without reading source code

### `browser-cli task examples`

Purpose:

- let users discover canonical example tasks from the installed package

Recommended behavior:

- list available examples with a short description
- optional future follow-up may add example printing or copying, but listing is
  sufficient for the first release

Acceptance:

- users can discover examples without browsing repository docs first

### `browser-cli task template`

Purpose:

- let users inspect or emit the canonical minimal task contract

Recommended behavior:

- `browser-cli task template --print`
- optional `browser-cli task template --output <dir>`

Template contents should expose:

- `task.py`
- `task.meta.json`
- `automation.toml`

Acceptance:

- a user can create a valid minimal task directory without reverse-engineering
  repository examples
- template output reinforces the `task` vs `automation` distinction

### `automation publish` output

Purpose:

- turn a successful publish into an explanatory milestone rather than a bare
  success message

Success output should show:

- source task directory
- automation id
- published version
- snapshot directory
- service import result
- next useful commands

Recommended next commands:

- `browser-cli automation inspect <id>`
- `browser-cli automation status`
- `browser-cli automation ui`

Required wording:

- source task remains editable local source
- published automation is an immutable snapshot

Acceptance:

- a first-time publisher can understand what was created and what to run next

### `browser-cli automation list`

Purpose:

- high-level summary of published automations

Recommended fields:

- automation id
- current version
- enabled or service status summary

Acceptance:

- users can answer what automations exist without opening the Web UI

### `browser-cli automation versions <automation-id>`

Purpose:

- version navigation for one automation

Recommended fields:

- version number
- publish time summary
- latest run status summary, when available

Acceptance:

- users can answer which versions exist for a published automation

### `browser-cli automation inspect <automation-id> [--version N]`

Purpose:

- central read-only inspection surface for one published automation

Recommended fields:

- automation id
- selected version
- available versions
- snapshot path
- task path inside snapshot
- schedule
- latest run status
- related path hints for logs and artifacts when available

Acceptance:

- users can answer what publish created, which version is active, and where the
  snapshot lives from the CLI alone

### Error hints

Purpose:

- reduce the need to search docs after common failures

First-wave coverage should focus on:

- Chrome missing
- managed profile lock
- daemon or runtime mismatch
- bad task layout
- automation not found
- version not found
- extension unavailable when optional

Rules:

- use a short `Next: ...` format
- keep hints to one or two concrete actions
- prefer existing commands such as `doctor`, `paths`, `status`, `reload`,
  `task validate`, and `automation inspect`

Acceptance:

- the first recovery action is obvious from the error output itself for common
  failures

## Rollout Plan

Recommended implementation order:

1. `browser-cli doctor`
2. `browser-cli paths`
3. dedicated pip-user quickstart doc
4. common `Next:` error hints
5. `browser-cli task examples`
6. `browser-cli task template`
7. stronger `automation publish` output
8. `task` vs `automation` help-copy sweep
9. `browser-cli automation list`
10. `browser-cli automation versions`
11. `browser-cli automation inspect`

This order is intentional:

- `doctor` and `paths` provide the discovery primitives that docs and error
  hints should point to
- task discovery and publish clarity matter before deeper post-publish
  observability
- automation observability should stabilize around `inspect` as the center of
  gravity rather than fragmenting into too many commands too early

## Dependencies

- docs should not treat `doctor` or `paths` as the main happy path until those
  commands exist
- error hints should only point to stable supported commands
- `automation publish` output should reference `inspect` as the primary follow-up
  surface once its naming and role are stable
- all new CLI surfaces should follow the existing parser and action conventions
  in the repository

## Documentation Strategy

- add a dedicated installed-with-pip quickstart doc
- update README installation and quick-start sections so they do not assume
  repository-maintainer context
- repeat the `task` vs `automation` distinction consistently across help text,
  docs, and publish output
- explain extension mode as optional guidance, not the first-run default

## Validation Strategy

Validation should cover both CLI contracts and the end-to-end user journey.

Test layers:

- parser and help coverage for all new commands
- unit tests for:
  - `doctor` result aggregation
  - `paths` field contracts
  - success output rendering
  - automation inspection rendering and JSON shape
- integration tests for:
  - `doctor -> paths -> read -> task validate -> task run -> automation publish`
  - common failure hints
- documentation checks to ensure quickstart commands remain runnable

Repository validation remains:

- `scripts/lint.sh`
- `scripts/test.sh`
- `scripts/guard.sh`

## Success Metrics

### Phase 1

- a new user can determine environment readiness with `browser-cli doctor`
- a new user can find Browser CLI runtime paths with `browser-cli paths`
- common first-run failures provide concrete next-step recovery

### Phase 2

- a user can create and validate a minimal task without repository browsing
- a first publish clearly teaches the source-task versus snapshot distinction

### Phase 3

- a user can answer what was published, which versions exist, and where the
  snapshot lives using the CLI alone

## Deferred Work

The following items remain intentionally outside the first three phases:

- `browser-cli setup` as a guided helper
- automation run and run-history shortcuts such as `run`, `runs`, and `logs`
- detailed upgrade and migration policy commands

These are useful, but they should not displace first-day diagnosis, discovery,
or publish observability.
