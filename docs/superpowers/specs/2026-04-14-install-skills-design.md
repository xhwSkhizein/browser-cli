# Browser CLI Install Skills Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

This design repairs `browser-cli install-skills` so it works for installed
users and exposes a narrow, intentional public contract.

The command should:

- install exactly three Browser CLI skills
- load them only from packaged assets shipped with the installed distribution
- default to `~/.agents/skills`
- allow `--target <path>` for explicit overrides
- fail fast if any required packaged skill is missing

The three public skills are:

1. `browser-cli-delivery`
2. `browser-cli-explore`
3. `browser-cli-converge`

This design does not expand `install-skills` into a generic skill manager. It
only makes the current public command deterministic and release-safe.

## Problem Statement

`browser-cli install-skills` is currently exposed as a public command, but its
implementation depends on repository-top-level `skills/` content being present
at runtime.

That assumption is not stable for installed users:

- the current wheel does not ship the required skill assets
- the command tries to discover `skills/` via installation-path heuristics
- installed users can receive a runtime failure even though the command is
  advertised as package-backed behavior

This creates two release-quality problems:

1. the public command is broken in the installed package
2. the installation surface is broader and more implicit than intended

At the same time, the repository now has a more intentional three-layer Browser
CLI skill stack:

- `browser-cli-delivery` as the main entrypoint
- `browser-cli-explore` for evidence gathering and metadata capture
- `browser-cli-converge` for validated path convergence into `task.py`

The command should install that explicit stack, not whatever happens to live
under the repository `skills/` directory.

## Goals

- Make `browser-cli install-skills` work from an installed package.
- Restrict the public installation surface to the three Browser CLI skills.
- Stop relying on git-root or pip-location heuristics to find installable
  assets.
- Add an explicit `--target` override while preserving the current default
  target.
- Fail clearly when packaged assets are incomplete rather than silently
  degrading.
- Add release-oriented verification so wheel regressions are caught before
  publish.

## Non-Goals

- This design does not package or install `browser-cli-extension`.
- This design does not install every repository skill.
- This design does not introduce remote fetching or repo-clone fallback.
- This design does not change the Browser CLI daemon, task runtime, or
  automation contracts.
- This design does not turn `install-skills` into a JSON-first machine API.

## Chosen Direction

Browser CLI should treat installable skills as packaged application assets, not
as incidental repository files.

The implementation should move the release-backed skill source to a package-owned
location under `src/browser_cli/`, then access those files through
`importlib.resources`.

The command should install only a hard-coded whitelist of public Browser CLI
skills:

- `browser-cli-delivery`
- `browser-cli-explore`
- `browser-cli-converge`

The command should no longer scan the repository `skills/` directory or infer a
git checkout. If packaged assets are missing, the command should fail because
that is a release defect.

## Options Considered

### 1. Explicit packaged whitelist

Ship the three public skills as package-owned assets and install only those
directories.

Advantages:

- stable for wheel installs
- narrow public contract
- no dependency on repository layout at runtime
- easiest behavior to test as a release artifact

Disadvantages:

- requires explicit packaging configuration
- requires a small amount of asset-copy plumbing

Chosen direction.

### 2. Filter repository or packaged `skills/` at runtime

Continue discovering a `skills/` directory, then filter for Browser CLI skill
names.

Advantages:

- smaller code change

Disadvantages:

- still depends on an implicit directory contract
- still couples runtime behavior to packaging accidents
- easier to widen public surface unintentionally

Rejected.

### 3. Require repository installs for `install-skills`

Document that the command is only supported from a git checkout.

Advantages:

- avoids packaging work

Disadvantages:

- contradicts the command description
- weakens installed-user UX unnecessarily
- leaves a public command broken in the release artifact

Rejected.

## Public Contract

### Command Shape

`browser-cli install-skills` remains a top-level command.

Arguments:

- `--dry-run`
- `--target <path>`

Default target:

- `~/.agents/skills`

### Installed Skill Set

The command installs exactly these three skills:

1. `browser-cli-delivery`
2. `browser-cli-explore`
3. `browser-cli-converge`

No other skill directories are installed by this command, even if additional
skills exist in the repository.

### Source of Truth

The source of truth for the command is the packaged asset set included in the
installed distribution.

Runtime fallback to:

- git repository discovery
- repository root scanning
- network download

is explicitly out of scope.

### Update Behavior

If a target skill directory already exists:

- `--dry-run` reports `would update`
- a real run replaces the existing directory contents

The command does not perform partial merges inside a skill directory.

### Failure Semantics

The command should fail immediately when:

- any required packaged skill is missing
- packaged skill contents cannot be read
- the target directory cannot be created or written

Failure should stop installation rather than returning a partial-success result.

## Packaging Design

### Asset Location

The installable skill assets should live under this package-owned path:

```text
src/browser_cli/packaged_skills/
  browser-cli-delivery/
    SKILL.md
  browser-cli-explore/
    SKILL.md
  browser-cli-converge/
    SKILL.md
```

These files must be present inside the wheel and readable through
`importlib.resources`.

### Repository Editing Model

The packaged path becomes the release-backed source for `install-skills`.

Repository-top-level `skills/` may still exist for other workflows, but it is
not the runtime source for this command and must not silently widen the install
surface.

This design intentionally prefers one release-backed truth over dual-source
runtime discovery.

## Command Design

The implementation should separate discovery, validation, and copy behavior.

### Discovery Layer

A helper should enumerate the packaged whitelist and verify that every required
skill exists before any target mutation begins.

The helper should return a structured list of installable assets keyed by skill
name.

### Installation Layer

For each whitelisted skill:

- resolve the target path under the chosen target directory
- report `would install` or `would update` during dry-run
- otherwise replace the target directory with the packaged contents

Replacement should be directory-level replacement, not per-file merge logic.

### CLI Layer

The CLI handler should:

- resolve `--target` or the default path
- call packaged-skill discovery
- run dry-run or real copy
- render the existing plain-text summary format

The command may keep text output because it is a user-facing helper rather than
part of the daemon JSON contract.

## Error Handling

The command should distinguish packaging defects from user-environment failures.

### Packaging Defects

Examples:

- one of the three public skills is absent from packaged assets
- a packaged skill lacks `SKILL.md`
- resource extraction fails unexpectedly

These should produce a direct error that identifies the missing or unreadable
skill by name.

### User Environment Failures

Examples:

- target path parent cannot be created
- an existing target directory cannot be removed
- copy to target fails due to permissions

These should produce a direct error that includes the target path and underlying
filesystem cause.

## Testing And Validation

This change needs release-oriented validation, not only repo-local unit tests.

### Unit Tests

Add or update tests to cover:

- only the three whitelisted skills are considered installable
- `--target` overrides the default path
- dry-run reports `would install` and `would update`
- missing packaged assets fail fast
- existing directories are replaced on real install

### Build-Artifact Tests

Add a test or guard that validates the built wheel contains the three packaged
skill directories and their `SKILL.md` files.

### Installed-Smoke Validation

Add a release-oriented smoke step that:

1. builds the distribution artifacts
2. installs the wheel into a clean environment
3. runs `browser-cli install-skills --dry-run --target <tmpdir>`
4. verifies the command succeeds

This should run before publish, because this class of regression is invisible in
repository-local development environments.

## Files Expected To Change

Primary implementation areas:

- `src/browser_cli/commands/install_skills.py`
- `src/browser_cli/cli/main.py`
- `pyproject.toml`
- packaging metadata needed to include packaged skill assets in the wheel
- tests covering install-skills behavior and release artifacts

New package-owned asset paths are expected under `src/browser_cli/`.

## Risks

- dual-maintenance risk if repository-top-level `skills/` and packaged assets
  drift
- future accidental widening of the install surface if tests only verify command
  success and not the exact installed set
- release regressions if artifact checks are omitted from CI or release flow

The design addresses these risks by using:

- an explicit skill whitelist
- package-owned runtime assets
- wheel-level validation

## Acceptance Criteria

This design is complete when all of the following are true:

- `browser-cli install-skills` installs only the three Browser CLI skills
- the command works from an installed wheel without a git checkout
- `--target` overrides the default install directory
- missing packaged assets produce a hard failure
- the wheel contains the packaged skill assets
- CI or release validation exercises the built artifact, not just source-tree
  execution
