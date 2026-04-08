# Browser CLI v1 Implementation Plan

Date: 2026-04-08
Status: Ready for implementation
Related spec: `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-08-browser-cli-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current environment. This document is the direct planning fallback and serves the same purpose: an implementation-ready sequence for building `v1`.

## Objective

Build `v1` of Browser CLI as a `CLI-first`, `Python-first`, one-shot browser reader with the following supported interface:

```bash
browser-cli read <url>
browser-cli read <url> --snapshot
browser-cli read <url> --scroll-bottom
```

`v1` must:

- prefer an existing local stable Google Chrome profile
- fall back to `~/.browser-cli/default-profile` when the primary profile is unavailable
- support macOS and Linux
- output rendered DOM HTML by default
- output a bridgic-style snapshot with `--snapshot`
- fail explicitly when browser/profile requirements are not met

## Out of Scope

The following are explicitly excluded from this implementation plan:

- workflow execution
- explore/record/synthesize flows
- daemon-first command model
- direct compatibility with `opencli` YAML
- arbitrary action chains or custom waits in `read`
- fallback to undocumented browser profiles or alternate browser families

## Delivery Strategy

Build `v1` in six milestones:

1. repo bootstrap and CLI skeleton
2. profile discovery and browser target resolution
3. internal browser core with provenance tracking
4. read runner and output contract
5. automated tests with local fixtures
6. smoke validation and docs polish

The implementation order is important. Browser-core porting should not start before the repo has clean boundaries and the profile rules are encoded in tests.

## Target Repository Shape

Implement the spec's logical layers as concrete Python packages under a single installable package root:

```text
src/browser_cli/
  cli/
  commands/
  runtime/
  browser/
  profiles/
  outputs/
  workflow/
tests/
  unit/
  integration/
  smoke/
third_party/
docs/
```

`workflow/` exists as a reserved namespace but remains effectively empty in `v1`.

## Milestone 1: Repo Bootstrap and CLI Skeleton

### Deliverables

- Python package scaffolding
- packaging metadata and console entrypoint
- minimal `browser-cli read` command shell
- shared exit-code constants
- top-level test runner configuration

### Tasks

1. Add packaging and tooling files.
   Expected files:
   - `pyproject.toml`
   - `.gitignore`
   - optional formatter/linter config if chosen

2. Create package skeleton under `src/browser_cli/`.
   Expected directories:
   - `src/browser_cli/cli/`
   - `src/browser_cli/commands/`
   - `src/browser_cli/runtime/`
   - `src/browser_cli/browser/`
   - `src/browser_cli/profiles/`
   - `src/browser_cli/outputs/`
   - `src/browser_cli/workflow/`

3. Add a console entrypoint for `browser-cli`.

4. Implement a placeholder `read` command path that validates arguments and returns a not-yet-implemented runtime error while preserving the intended command shape.

5. Define shared exit-code constants matching the approved spec.

### Acceptance Criteria

- `browser-cli --help` works.
- `browser-cli read --help` shows the intended contract.
- The package installs in editable mode.
- Exit code constants are centralized rather than scattered through command handlers.

## Milestone 2: Profile Discovery and Browser Target Resolution

### Deliverables

- browser executable discovery for stable Google Chrome
- user data directory discovery on macOS and Linux
- default profile selection (`Default`)
- fallback profile root selection under `~/.browser-cli/default-profile`
- explicit lock/conflict detection
- structured profile errors mapped to CLI exit codes

### Tasks

1. Implement platform-specific Chrome executable discovery.
   Scope:
   - macOS stable Google Chrome
   - Linux stable Google Chrome

2. Implement platform-specific user data directory discovery.

3. Add profile selection logic.
   `v1` behavior:
   - default to `Default`
   - no user-facing profile flag is required unless implementation proves it is necessary later
   - if the primary profile is unavailable, fall back to `~/.browser-cli/default-profile`

4. Implement conflict detection for active profile locks or running Chrome ownership conflicts.

5. Define profile-layer error types:
   - browser missing
   - user data missing
   - profile missing
   - profile locked

6. Add unit tests for all supported platform branches using mocked filesystem/process conditions.

### Acceptance Criteria

- macOS and Linux path resolution are test-covered.
- Missing Chrome produces the browser-unavailable exit category.
- Locked or missing primary profile uses the managed fallback profile.
- If both primary and fallback profiles are unavailable, return the profile-unavailable exit category.

## Milestone 3: Internal Browser Core and Provenance Tracking

### Deliverables

- minimal internal browser core based on Playwright
- third-party provenance records for adapted `bridgic-browser` material
- minimal stealth integration
- minimal snapshot/ref support
- rendered DOM HTML capture

### Tasks

1. Create `third_party/` provenance structure.
   Expected artifacts:
   - copied license text where required
   - provenance note identifying source repo, commit or version, and original file paths

2. Decide the exact minimum subset to internalize from `bridgic-browser`.
   Candidate areas:
   - stealth init script logic
   - browser launch/session wrapper patterns
   - snapshot/ref generator

3. Port only the minimum code required for `v1`.
   Exclude unrelated tools such as tabs, mouse, keyboard, network capture, or daemon transport.

4. Implement a thin browser-session wrapper for Browser CLI:
   - launch browser with resolved executable and user data dir
   - navigate to URL
   - expose DOM HTML capture
   - expose snapshot capture
   - close cleanly on success and failure

5. Normalize browser-core errors into internal error classes suitable for CLI mapping.

6. Add focused unit/integration tests for:
   - browser startup with fixture pages
   - HTML capture
   - snapshot capture

### Acceptance Criteria

- Browser core can launch against a real user-data-dir input.
- HTML capture returns rendered DOM, not a raw HTTP response body.
- Snapshot capture returns the intended tree format.
- Third-party provenance is documented before adapted code lands.

## Milestone 4: Read Runner and Output Contract

### Deliverables

- one-shot read runner
- default wait behavior
- `--scroll-bottom` behavior
- stdout/stderr discipline
- final exit-code mapping

### Tasks

1. Implement `ReadRequest` and `ReadResult` models.
   Inputs should only represent:
   - URL
   - output mode (`html` or `snapshot`)
   - `scroll_bottom` boolean

2. Implement the read runner lifecycle:
   - resolve browser/profile environment
   - start browser
   - navigate
   - apply default settle behavior
   - optionally scroll to bottom
   - capture output
   - cleanup

3. Implement output renderers:
   - raw rendered HTML to stdout
   - snapshot tree to stdout

4. Implement empty-result handling and exit code `66`.

5. Wire runtime errors to the approved exit codes:
   - `0`
   - `1`
   - `2`
   - `66`
   - `69`
   - `73`
   - `75`

6. Add command-level tests that assert stdout, stderr, and exit code behavior.

### Acceptance Criteria

- `browser-cli read <url>` returns only rendered HTML on stdout.
- `browser-cli read <url> --snapshot` returns only snapshot text on stdout.
- `browser-cli read <url> --scroll-bottom` performs an additional bottom-load pass before capture.
- Error messages go to stderr and preserve stable exit categories.

## Milestone 5: Automated Tests with Local Fixtures

### Deliverables

- fixture web pages for deterministic integration tests
- integration coverage for render, lazy load, and snapshot
- local test utilities for browser/profile setup

### Tasks

1. Create fixture pages served locally during tests.
   Required fixtures:
   - static page
   - client-rendered page
   - lazy-load/infinite-scroll-like page

2. Add integration tests covering:
   - plain HTML read
   - HTML-after-render read
   - `--scroll-bottom`
   - `--snapshot`

3. Keep fixture behavior deterministic and free of external network dependencies.

4. Add smoke-test harness scaffolding separately from the main integration suite.

### Acceptance Criteria

- CI can validate core read behavior without relying on external websites.
- Scroll and render behavior are reproducible locally.
- Snapshot output is checked against stable expected assertions rather than brittle full-file snapshots whenever possible.

## Milestone 6: Smoke Validation and Docs Polish

### Deliverables

- manual or scripted smoke validation checklist
- initial README or usage docs
- release notes for `v1` scope and limitations

### Tasks

1. Create a smoke-test checklist for real-world validation.
   Must verify:
   - stable Google Chrome discovery
   - closed-Chrome requirement
   - authenticated profile reuse
   - normal page reading

2. Add user-facing docs for:
   - install and setup
   - supported platforms
   - Chrome/profile requirements
   - command examples
   - common failure cases

3. Document known `v1` limitations clearly so users do not mistake `read` for a full automation runner.

### Acceptance Criteria

- A new user can install and run `browser-cli read <url>` from docs alone.
- The closed-Chrome and profile-lock requirements are clearly documented.
- The distinction between `v1` read and future workflow features is explicit.

## Recommended Implementation Order

Implement in this exact order:

1. package/bootstrap
2. exit-code and CLI surface
3. profile discovery
4. profile error mapping tests
5. third-party provenance scaffolding
6. minimal browser-core port
7. HTML capture path
8. snapshot capture path
9. read runner
10. `--scroll-bottom`
11. integration fixtures
12. smoke checklist and docs

This ordering reduces the chance of importing large third-party browser logic before the product contract is encoded in tests.

## Risks and Mitigations

### Risk: Chrome profile lock behavior differs by platform

Mitigation:

- test detection logic independently from real launch
- keep explicit user-facing diagnostics
- do not auto-fallback to fresh profiles

### Risk: Ported stealth logic becomes too large or too coupled

Mitigation:

- port only the `v1` minimum subset
- document provenance before merging
- keep adapted code isolated under `browser_cli.browser`

### Risk: Render-stability timing is flaky across sites

Mitigation:

- encode a simple default settle policy in the runner
- validate behavior first with deterministic local fixtures
- avoid exposing a large wait-tuning surface in `v1`

### Risk: Snapshot port introduces unnecessary complexity

Mitigation:

- bring over the narrowest useful snapshot/ref subset
- skip unrelated tool abstractions and daemon plumbing

## Definition of Done for v1

`v1` is complete when all of the following are true:

- `browser-cli read <url>` works on macOS and Linux for supported Chrome setups
- `browser-cli read <url> --snapshot` works
- `browser-cli read <url> --scroll-bottom` works
- rendered DOM HTML is the default output
- browser/profile failures map to stable CLI exit codes
- no hidden fallback to temporary profiles exists
- local integration tests cover render and lazy-load behavior
- third-party provenance is documented for any adapted browser-core code
- docs explain setup, usage, and failure cases

## First Implementation Slice

The first coding slice after this plan should be:

1. scaffold package and console entrypoint
2. add exit code constants
3. implement `browser-cli read --help`
4. implement profile discovery stubs plus unit tests

This slice is intentionally small and creates the foundation needed before porting any browser-core code.
