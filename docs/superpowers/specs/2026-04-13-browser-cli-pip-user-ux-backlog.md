# Browser CLI Pip User UX Backlog

Date: 2026-04-13
Status: Drafted for review
Repo: `/home/hongv/workspace/browser-cli`

## Summary

This backlog captures the highest-value UX improvements for `pip` users of
Browser CLI after the `task` / `automation` surface cutover.

The target user here is not a repository maintainer. It is someone who:

- installs Browser CLI with `pip`
- wants to run the product outside this repo
- needs to understand where files live, what to do first, and how to recover
  when something fails

The current architecture is much clearer than the old `workflow` model, but the
main remaining gaps are:

- first-run setup and diagnosis are still too implicit
- task templates and runtime paths are not discoverable enough
- published automation snapshots are not observable enough after publication
- error messages and docs still assume more repo context than a `pip` user has

## Product Lens

The product should optimize for these four moments:

1. Install: can I verify the environment quickly?
2. First success: can I run one command and understand the output?
3. First delivery: can I create, validate, run, and publish a task without
   reading source code?
4. First failure: when something breaks, does the product tell me what to do
   next?

## P0

### 1. Add `browser-cli doctor`

Problem:
`pip` users need a single command that answers whether the product is correctly
installed and usable on the current machine.

Why this matters:

- reduces first-run failure rate
- reduces support burden
- shortens the path from install to confidence

Proposed UX:

- add `browser-cli doctor`
- print a compact pass/fail report for:
  - Python package importability
  - Chrome discovery
  - Playwright/runtime readiness
  - Browser CLI home path
  - managed profile directory access
  - daemon status
  - automation service status
  - extension reachability, if configured
- include exact next-step commands when a check fails

Recommended output style:

- human-readable by default
- `--json` for machine-readable diagnostics

Success signal:

- a new user can run `browser-cli doctor` immediately after `pip install` and
  know exactly what remains to be fixed

### 2. Add `browser-cli paths`

Problem:
Users do not have an obvious way to discover the canonical Browser CLI
filesystem layout outside the repository.

Why this matters:

- users need to know where tasks should live
- users need to know where automations and logs are stored
- path transparency reduces confusion during debugging

Proposed UX:

- add `browser-cli paths`
- print:
  - `home`
  - `tasks_dir`
  - `automations_dir`
  - `automation_db_path`
  - `automation_service_run_info_path`
  - `automation_service_log_path`
  - `daemon_log_path`
  - `artifacts_dir`

Success signal:

- a `pip` user can discover the full runtime layout without reading code or
  guessing hidden directories

### 3. Make templates and examples discoverable from the CLI

Problem:
The product now has a clear task contract, but a `pip` user still has to guess
what a valid task directory should look like.

Why this matters:

- task authoring should not require repository browsing
- agents and humans both need a stable contract to copy

Proposed UX:

- add `browser-cli examples` or `browser-cli task examples`
- add `browser-cli task template --print`
- optionally add `browser-cli task template --output <dir>`
- expose the canonical `task.py`, `task.meta.json`, and `automation.toml`
  templates directly from the installed package

Recommendation:

- do not add `task init` yet
- prefer low-friction discovery and optional template emission first

Success signal:

- a new user can create a valid task directory without opening the repo or
  reverse-engineering example files

### 4. Improve action-oriented error messages

Problem:
Many failures still require the user to infer the next recovery step.

Why this matters:

- first-failure UX is a major product quality signal
- `pip` users need commands, not just diagnoses

Proposed UX:

- for common failures, append a short `Next:` hint
- examples:
  - Chrome missing -> `Next: install stable Google Chrome and re-run browser-cli doctor`
  - runtime mismatch -> `Next: run browser-cli reload`
  - bad task layout -> `Next: run browser-cli task validate <task-dir>`
  - profile lock -> `Next: close Browser CLI-owned Chrome windows or inspect browser-cli status`

Success signal:

- users can recover from common failures without searching docs first

## P1

### 5. Add automation observability commands

Problem:
After `automation publish`, users still lack a strong inspection surface for
what was published and what versions exist.

Why this matters:

- immutable snapshots only help if users can inspect them
- publication should feel concrete and queryable

Proposed UX:

- add:
  - `browser-cli automation list`
  - `browser-cli automation versions <automation-id>`
  - `browser-cli automation inspect <automation-id> [--version N]`
- inspection should show:
  - automation id
  - current persisted version
  - available versions
  - snapshot paths
  - task path inside the snapshot
  - schedule
  - latest run status

Success signal:

- users can answer “what did I publish?” and “which version is running?” from
  the CLI alone

### 6. Strengthen `automation publish` output

Problem:
Publication succeeds, but the result still does not feel fully self-explanatory
to a first-time user.

Why this matters:

- publish is a key user milestone
- the command should immediately teach the mental model

Proposed UX:

- publish output should clearly show:
  - source task directory
  - automation id
  - published version
  - snapshot directory
  - service import result
  - next useful commands, such as:
    - `browser-cli automation inspect <id>`
    - `browser-cli automation ui`
    - `browser-cli automation export <id> --output ...`

Success signal:

- the command output itself is enough to orient a first-time publisher

### 7. Add a pip-user quickstart section to the docs

Problem:
The current docs are improving, but the repo still speaks partly to maintainers
instead of a user who installed from `pip`.

Why this matters:

- quickstart quality strongly affects whether the product feels usable
- command naming changes need a crisp tutorial path

Proposed content:

- install
- `browser-cli doctor`
- `browser-cli paths`
- first `read`
- first `task validate`
- first `task run`
- first `automation publish`
- first `automation ui`

Recommendation:

- make this a dedicated “Installed With Pip” doc, not just a README paragraph

Success signal:

- a `pip` user can reach a first task publication without repository-local
  assumptions

### 8. Add explicit “task vs automation” help copy everywhere

Problem:
The new model is better, but users still need the distinction reinforced.

Proposed rule:

- repeat this sentence in CLI help, docs, and publish output:
  - `task` is local editable source
  - `automation` is a published immutable snapshot

Success signal:

- users stop asking whether they should edit the automation snapshot directly

## P2

### 9. Add `browser-cli setup` as a guided bootstrap flow

Problem:
`doctor` diagnoses, but some users will still want a guided first-run path.

Proposed UX:

- add a guided helper that:
  - prints the Browser CLI home
  - points to templates
  - explains managed profile mode
  - explains when extension mode is worth enabling
  - recommends the first three commands to run

Recommendation:

- do this after `doctor`
- keep it informational, not magical

Success signal:

- new users can follow one guided path without reading multiple docs

### 10. Add automation run and history shortcuts

Problem:
Users will want quick access to recent automation activity without always using
the Web UI.

Proposed UX:

- add:
  - `browser-cli automation runs <automation-id>`
  - `browser-cli automation run <automation-id>`
  - `browser-cli automation logs <run-id>`

Why this is P2:

- useful, but not as foundational as install/setup/task discovery

### 11. Clarify upgrade and migration policy for pip users

Problem:
As the product evolves, users need to know what happens to their local home
state on upgrade.

Proposed scope:

- document:
  - compatibility expectations for `~/.browser-cli`
  - whether schema or runtime upgrades are automatic
  - when users should run repair or migration commands

Why this is P2:

- important for trust
- less urgent than first-run usability

### 12. Add opinionated extension-mode guidance

Problem:
Users can over-focus on extension mode too early, even when managed profile mode
is the faster path to first success.

Proposed UX:

- explicitly recommend:
  - start with managed profile mode
  - only enable extension mode when site fidelity or real Chrome behavior is
    needed

Why this is P2:

- the product already works without this, but clearer guidance will reduce
  premature complexity

## Recommended Implementation Order

1. `browser-cli doctor`
2. `browser-cli paths`
3. template and examples discovery
4. better action-oriented error hints
5. automation observability commands
6. stronger publish output
7. dedicated pip-user quickstart doc

## Final Recommendation

If only three improvements ship next, they should be:

1. `browser-cli doctor`
2. `browser-cli paths`
3. `browser-cli automation inspect` plus version/list support

This combination improves the three biggest `pip` user pain points:

- “is my install usable?”
- “where does Browser CLI put things?”
- “what exactly did publish create?”
