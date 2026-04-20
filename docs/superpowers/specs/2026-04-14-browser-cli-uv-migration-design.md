# Browser CLI UV Migration Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

This design migrates Browser CLI to a uv-first, uv-only project workflow.

The migration covers four operational surfaces:

- repository development
- CI
- release
- user installation and quickstart documentation

After this change, uv becomes the only primary path for working with the
project:

- maintainers use `uv sync` and `uv run`
- CI uses uv-managed Python and uv-managed dependency execution
- release uses `uv build` and `uv publish`
- end users install with `uv tool install browser-control-and-automation-cli`
  or run with `uvx --from browser-control-and-automation-cli browser-cli`

The migration intentionally does not change Browser CLI product architecture or
replace the current `setuptools` build backend.

## Problem Statement

The repository is currently in a mixed state:

- some scripts already prefer `uv run`
- CI still installs through `pip install -e .`
- release still uses `pip install build twine`
- documentation still presents `pip` as the primary install path
- some runtime error messages still instruct users to run `python3 -m pip`

This creates three problems:

1. development, CI, release, and user installation do not share one canonical
   workflow
2. dependency resolution is not fully locked at the repository level
3. the project communicates contradictory setup guidance depending on which
   surface a user reads first

If Browser CLI is going to move to uv, it should move fully enough that the
default answer is unambiguous.

## Goals

- Make uv the only primary workflow for Browser CLI.
- Cover repository development, CI, release, and end-user installation.
- Add repository-controlled Python and dependency resolution through
  `.python-version` and `uv.lock`.
- Remove fallback behavior in repository scripts that silently switches to
  `pip`, bare `python`, or `.venv/bin/python`.
- Update documentation and user-facing recovery hints so they no longer present
  `pip` as the default path.
- Preserve the current package and CLI product contracts.

## Non-Goals

- No daemon, driver, refs, tabs, automation, or task-runtime architecture
  changes.
- No CLI contract redesign.
- No replacement of the existing `setuptools.build_meta` backend in this
  migration.
- No continued support for a full repository-maintainer workflow without uv.
- No attempt to keep `pip` as a first-class documented path.

## Options Considered

### 1. Minimal Workflow Substitution

Replace obvious commands with `uv sync`, `uv run`, `uv build`, and
`uv publish`, but otherwise keep current project structure and habits mostly
unchanged.

Advantages:

- smallest patch set
- fastest short-term rollout
- lowest immediate migration risk

Disadvantages:

- still feels like a `pip` project with uv wrappers
- leaves too much room for drift between docs, scripts, and CI
- does not clearly establish one canonical project model

Rejected.

### 2. Standard UV Project Migration

Adopt uv as the canonical project workflow:

- add `uv.lock`
- add `.python-version`
- run repository workflows through `uv sync` and `uv run`
- migrate CI and release to uv
- migrate user installation docs to `uv tool install` and `uvx`
- keep the current build backend

Advantages:

- fully satisfies the uv-only goal without broad packaging refactors
- keeps scope bounded to workflow, tooling, and documentation
- aligns local development, CI, and release around one model

Disadvantages:

- still uses `setuptools` under uv instead of changing packaging strategy
- touches several operational surfaces in one migration

Chosen direction.

### 3. Full Packaging-System Rework

Migrate to uv and also refactor the package build model, dependency metadata,
and surrounding packaging conventions in the same change.

Advantages:

- most ideologically complete
- could remove more historical packaging debt in one pass

Disadvantages:

- expands a workflow migration into a packaging redesign
- increases rollout risk significantly
- makes failures harder to isolate

Rejected.

## Chosen Direction

Browser CLI should adopt uv as the only primary workflow while preserving the
existing package build contract.

That means the migration changes how the project is developed, tested,
released, and installed, but it does not change what the package is or how the
Browser CLI product behaves at runtime.

The migration has four explicit audience paths:

### 1. Repository Development Path

Repository maintainers use:

- `uv sync --dev`
- `uv run ...`

This becomes the only supported maintainer path documented in the repository.

### 2. User Installation Path

End users use:

- `uv tool install browser-control-and-automation-cli`
- `uvx --from browser-control-and-automation-cli browser-cli ...`

Git-based installs remain available, but are expressed through uv, for example
`uv tool install git+https://...`.

### 3. CI Path

CI installs Python and executes project commands through uv rather than
rebuilding a separate `pip`-centric workflow.

### 4. Release Path

Release uses uv-native build and publish commands while keeping the existing
PyPI package output contract intact.

## Scope And Change Surfaces

This migration is an engineering workflow change, not a product-runtime change.

### Files and surfaces that should change

- `pyproject.toml`
- `.python-version`
- `uv.lock`
- `scripts/lint.sh`
- `scripts/test.sh`
- `scripts/guard.sh`
- `scripts/check.sh`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `README.md`
- installed-user documentation and migration documentation
- user-facing install and recovery hints in runtime messages where they still
  point to `pip`
- tests and guards that freeze these workflow decisions
- `AGENTS.md`

### Files and surfaces that should not change materially

- Browser CLI daemon behavior
- driver contract
- semantic-ref contract
- task runtime contract
- public CLI JSON response shapes
- package output format

## Key Design Decisions

### Keep `setuptools`

The project should keep `setuptools.build_meta` for now. uv is fully capable of
driving the existing build backend. Replacing the build backend would broaden
scope without helping the primary migration goal.

### Commit `uv.lock`

`uv.lock` must be committed. Without a checked-in lockfile, the repository
would still rely on floating dependency resolution in local development and CI,
which would undermine the stated goal of a canonical uv workflow.

### Commit `.python-version`

`.python-version` must be committed and should default to `3.10`.

Rationale:

- the repository currently targets Python 3.10+
- the compatibility guard is anchored to Python 3.10
- a canonical local development version should exist even if CI still validates
  3.11 and 3.12

### Make repository scripts uv-only

Repository scripts should fail fast when uv is unavailable. They should not
fall back to `.venv/bin/python`, `python`, `python3`, or `pip`.

This is necessary to make repository behavior deterministic and consistent with
the declared migration scope.

### Separate maintainer and end-user guidance

The migration should not collapse all install guidance into one sentence.

Two distinct guidance paths must exist:

- repository maintainers: `uv sync --dev`, then `uv run ...`
- end users: `uv tool install browser-control-and-automation-cli` or
  `uvx --from browser-control-and-automation-cli browser-cli`

This separation avoids misdirecting an installed user toward repository setup,
or a contributor toward tool installation.

### Keep the Python compatibility matrix

CI should remain multi-version for Python 3.10, 3.11, and 3.12. uv-only does
not mean single-version testing. It only means one package and execution model.

### Use uv-native release commands

Release should move to `uv build` and `uv publish`, while still publishing the
same standard Python package artifacts.

## Migration Plan

The migration should be delivered in five stages.

### Stage 1: Project Foundations

Changes:

- add `uv.lock`
- add `.python-version`
- update `pyproject.toml` so the repository has one clear uv project workflow
- document `uv sync --dev` as the maintainer entrypoint

Outcome:

- repository development is grounded on committed Python and dependency
  resolution

### Stage 2: Repository Scripts

Changes:

- rewrite `scripts/lint.sh`
- rewrite `scripts/test.sh`
- rewrite `scripts/guard.sh`
- rewrite `scripts/check.sh`

Rules:

- require uv explicitly
- use `uv run` for execution
- remove fallback probing for `.venv/bin/python`, `python`, `python3`, and
  `pip`

Outcome:

- local script execution matches the intended canonical workflow

### Stage 3: CI And Release

Changes:

- migrate `.github/workflows/ci.yml` to uv-managed setup and command execution
- migrate `.github/workflows/release.yml` to `uv build` and `uv publish`

Outcome:

- local and hosted automation now use the same project model

### Stage 4: User Installation And Documentation

Changes:

- rewrite README install and quickstart sections around uv
- replace pip-first user docs with uv-first docs
- keep Git install support, but express it through uv

Outcome:

- users see one clear installation path instead of contradictory instructions

### Stage 5: Message, Guard, And Contract Cleanup

Changes:

- replace runtime and exception hints that still direct users to `pip`
- add or update tests and guards to prevent regression
- update `AGENTS.md` to record uv-only repository navigation guidance

Outcome:

- the migration becomes durable rather than dependent on documentation memory

## Testing Strategy

This migration should be validated as a workflow-contract change.

### Configuration validation

- `uv.lock` exists and is committed
- `.python-version` exists and matches the intended baseline
- `pyproject.toml` works with `uv sync` and `uv build`

### Script validation

- repository scripts only invoke uv-based commands
- repository scripts fail fast with a clear message when uv is not installed

### CI and release validation

- CI workflow no longer uses `pip install -e .` or `python -m pip`
- CI workflow uses uv-managed execution for lint, test, and guard
- release workflow no longer installs `build` or `twine` through pip

### Documentation and message validation

- README presents uv as the primary path
- installed-user guidance presents uv as the primary path
- runtime install/recovery hints no longer default to `pip`

## Risks

### Guidance drift between maintainer and user paths

Risk:

- maintainers and installed users require different commands, and docs can blur
  them together

Mitigation:

- structure docs explicitly around repository development versus installed-user
  usage

### Release-flow surprises

Risk:

- moving from `build` and `twine` to uv-native release commands may expose
  workflow or credential assumptions

Mitigation:

- validate build and publish steps locally before merging workflow changes
- keep PyPI trusted publishing semantics explicit in workflow review

### Residual pip instructions

Risk:

- stale messages or docs may keep pointing users to `pip`, making the migration
  incomplete

Mitigation:

- perform targeted repository searches for `pip install`, `python -m pip`, and
  similar phrases
- add tests or guards where practical

### Lockfile and editable-install edge cases

Risk:

- the move to a committed uv lockfile may expose packaging or editable-install
  assumptions not visible in the current workflow

Mitigation:

- validate `uv sync`, `uv run`, and `uv build` together rather than in
  isolation

## Acceptance Criteria

The migration is complete only when all of the following are true:

1. A new contributor can clone the repository, run `uv sync --dev`, and then
   run repository checks entirely through uv.
2. An end user can install Browser CLI with
   `uv tool install browser-control-and-automation-cli` and run `browser-cli`
   directly without prefixing every command with uv.
3. README and installed-user documentation present uv as the primary path.
4. CI and release workflows no longer depend on `pip` as the primary execution
   path.
5. Repository scripts contain no operational fallback to bare Python or pip.
6. Remaining runtime install or recovery hints are updated to the correct uv
   path for their audience.
7. `AGENTS.md` reflects the uv-only repository workflow.

## Implementation Notes

- This migration should be implemented before any unrelated packaging cleanup.
- If a later project wants to replace `setuptools`, it should be handled as a
  separate design and implementation cycle.
- Existing Python 3.10 compatibility guarantees remain in force during the
  migration.
