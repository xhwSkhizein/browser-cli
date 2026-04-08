# SiteCLI Design

Date: 2026-04-08
Status: Approved for planning
Repo: `/Users/hongv/workspace/m-projects/sitecli`

## Summary

SiteCLI is a new `CLI-first`, `Python-first` browser automation project for turning websites into reliable command-line readable surfaces and, later, scriptable workflows. The first release focuses on a narrow, opinionated `read` command that reuses an existing local Chrome profile, applies Playwright-based browser control with stealth protections, and returns either rendered DOM HTML or a bridgic-style accessibility snapshot.

This project does not depend on `opencli` or the published `bridgic-browser` package. Instead, it will internalize selected browser-core techniques from `bridgic-browser` and explicitly track provenance and license information in-repo. `opencli` is treated as an architectural reference for future workflow and explore-to-script concepts, not as a compatibility target.

## Context

Two existing repositories shape this design:

- `opencli` contributes the upper-layer idea: CLI discovery, command orchestration, workflows, and the `explore -> synthesize` path for building reusable site automations.
- `bridgic-browser` contributes the lower-layer idea: Playwright-native browser control, persistent user data reuse, stealth, snapshot/ref modeling, and agent-friendly page-state capture.

The user goal is not to merge those repositories directly. The goal is to create a new project that starts with a stable browser reading CLI and later grows into workflow execution and guided exploration.

## Goals

- Build a new repository instead of extending `opencli` or `bridgic-browser` directly.
- Make the primary interface a CLI because it is easier to test and easier for agents to understand.
- Keep the implementation Python-first and Playwright-first.
- Reuse an existing local Chrome user profile instead of requiring a separate browser session.
- Return rendered DOM HTML by default.
- Support `--snapshot` output using a bridgic-style tree representation.
- Support macOS and Linux from the first version.
- Keep `v1` focused on universal page reading, not full workflow authoring.

## Non-Goals for v1

- No direct compatibility with `opencli` YAML adapters.
- No direct dependency on the `bridgic-browser` package.
- No daemon-first or session-first interaction model.
- No generalized click chains, multi-step browser scripting, or mini-DSL embedded into `read`.
- No `explore`, `record`, or `synthesize` command in `v1`.
- No silent fallback to temporary or unauthenticated browser profiles.

## Chosen Direction

Three broad approaches were considered:

1. Build a narrow reader first and refactor later.
2. Define a layered platform now, but only fully implement the reader in `v1`.
3. Build an immediate full replacement for `opencli`.

The chosen direction is approach 2. The repository will be layered from the start so that workflow execution and exploration can be added later without reworking the browser core, but `v1` will only make the universal reading path production-grade.

## Product Shape

The product shape is:

- `CLI-first`
- `Python-first`
- `v1 = universal reading`
- one-shot command execution rather than a long-lived daemon workflow

This keeps the first feature simple for both humans and agents:

```bash
sitecli read <url>
sitecli read <url> --snapshot
sitecli read <url> --scroll-bottom
```

## v1 Command Contract

`read` is intentionally opinionated and intentionally limited.

### Command Surface

`v1` supports:

```bash
sitecli read <url>
sitecli read <url> --snapshot
sitecli read <url> --scroll-bottom
```

### Default Behavior

Without extra flags, `read`:

1. resolves the configured browser/profile environment
2. launches a controlled browser using the existing local Chrome profile
3. navigates to the URL
4. waits for the initial page render to stabilize
5. captures the rendered DOM HTML
6. writes the result to stdout
7. closes the browser

The default wait policy is:

- navigate with a normal page-load target suitable for rendered pages
- after load, apply a short settle window so client-side rendering can finish
- when `--scroll-bottom` is enabled, apply the same settle window again after the final scroll pass

`v1` does not expose this as user-tunable flags. It is part of the command's opinionated behavior.

### `--snapshot`

`--snapshot` switches output mode from rendered DOM HTML to a bridgic-style accessibility tree with stable element refs.

### `--scroll-bottom`

`--scroll-bottom` performs a built-in bottom-scroll pass before capture. This exists specifically for lazy-loaded or infinite-scroll pages. No additional scroll tuning flags are exposed in `v1`.

### Deliberate Restrictions

`read` does not support arbitrary action chains, custom waits, selector clicks, or script injection. Those requirements are explicitly deferred to the future workflow layer. The design principle is that `read` should solve the common cases cleanly and reject complexity instead of growing into a mini workflow engine.

## Architecture

The system is split into stable module boundaries from day one.

### 1. CLI Surface

`sitecli.cli`

Responsibilities:

- top-level argument parsing
- help text and usage
- exit code mapping
- stdout/stderr discipline

This layer contains no browser logic.

### 2. Command Layer

`sitecli.commands.read`

Responsibilities:

- own the `read` command contract
- translate command flags into a runtime request
- invoke the read runner
- return a final success or failure result

This layer performs orchestration only.

### 3. Read Runner

`sitecli.runtime.read_runner`

Responsibilities:

- execute the one-shot read lifecycle
- call the profile resolver
- launch the browser core
- apply the default waiting behavior
- optionally scroll to bottom
- collect HTML or snapshot
- enforce cleanup on both success and failure

This is the main `v1` workflow engine, but it remains single-purpose.

### 4. Browser Core

`sitecli.browser`

Responsibilities:

- wrap Playwright browser launch and shutdown
- attach to a controlled Chrome process using a real user data directory
- apply stealth settings and init scripts
- expose DOM HTML capture
- expose snapshot/ref capture
- normalize browser/platform differences between macOS and Linux

This layer is where selected `bridgic-browser` ideas or code may be internalized. It must be reusable by future workflow and exploration features.

### 5. Profile Resolution

`sitecli.profiles`

Responsibilities:

- discover default Chrome user data directories on macOS and Linux
- select a profile, defaulting to `Default`
- resolve browser executable locations
- detect lock conflicts and missing profiles
- return actionable diagnostic errors

This is a dedicated module because profile handling is a core product requirement, not a side detail.

### 6. Output Rendering

`sitecli.outputs`

Responsibilities:

- render HTML output mode
- render snapshot output mode
- keep stdout contract stable

### 7. Reserved Future Layer

`sitecli.workflow`

This namespace is reserved for `v2` and later. It is not implemented in `v1`, but the package boundary exists so the browser core and read runner do not need to be restructured later.

## Repository Layout

The repository layout should stay minimal:

```text
src/
  sitecli/cli/
  sitecli/commands/
  sitecli/runtime/
  sitecli/browser/
  sitecli/profiles/
  sitecli/outputs/
  sitecli/workflow/
tests/
docs/
third_party/
```

`third_party/` is required for provenance and license tracking of any internalized code or adapted implementation notes.

## Browser and Profile Strategy

### Profile Reuse Model

`v1` reuses an existing local Chrome profile by launching a controlled browser process against that profile's user data directory.

The user must close the normal Chrome instance before running `read`. The tool does not attempt to piggyback on an actively running Chrome process.

### Supported Platforms

`v1` supports:

- macOS
- Linux

The profile-resolution and browser-launch logic should be explicitly abstracted per platform.

### Browser Target

`v1` targets the locally installed stable Google Chrome layout first because the product requirement is reuse of an existing real user profile.

The launch path should:

- discover the local Google Chrome executable on macOS and Linux
- discover the corresponding user data directory
- fail clearly if the expected browser installation is missing

It should not silently substitute another browser family in `v1`.

### Failure Policy

If the desired profile cannot be used, SiteCLI fails explicitly. It does not silently fall back to:

- a temporary profile
- a fresh logged-out browser context
- a different installed browser

This preserves the core guarantee that a successful run truly reflects the user's existing authenticated state.

## Output Contract

### Default Output

Rendered DOM HTML, meaning the page state after browser execution and initial render rather than the raw server response.

### Alternate Output

`--snapshot` returns a tree representation modeled after bridgic's page snapshot format.

### Output Discipline

- `stdout` contains only the requested output body
- `stderr` contains diagnostics and errors
- error handling should preserve machine readability and agent usability

## Failure Semantics

The CLI should use stable exit categories that distinguish at least:

- argument and usage errors
- browser executable or launch errors
- profile discovery or profile lock errors
- page navigation or timeout errors
- successful command with empty resulting content

The command should prefer explicit failure over speculative fallback behavior. It should not quietly retry through multiple strategies or mutate the runtime model when the main path fails.

The initial concrete exit codes are:

- `0`: success
- `1`: unexpected internal error
- `2`: usage or argument error
- `66`: successful run but empty resulting content
- `69`: browser executable missing or browser launch unavailable
- `73`: profile missing, unreadable, or locked by another Chrome instance
- `75`: navigation timeout or page-read temporary failure

## Testing Strategy

Testing should be split into three layers.

### Unit Tests

Cover:

- profile path discovery
- platform-specific path logic
- command parsing
- output mode selection
- error mapping

### Integration Tests

Use local fixture sites to validate:

- basic page reading
- DOM-after-render capture
- lazy-loaded pages with `--scroll-bottom`
- snapshot output

This is the main automated validation layer.

### Smoke Tests

Use a small set of real websites to validate:

- reuse of an actual local Chrome profile
- ability to read authenticated pages
- stealth behavior not breaking normal page rendering

These tests should remain outside the main CI critical path because they are inherently more fragile.

## Future Evolution

### v2: Workflow Execution

After `read` is stable, SiteCLI should add a new Python-first workflow layer. This is not `opencli` YAML compatibility. It is a new DSL and runtime shaped around the internal browser core.

The workflow layer should own:

- reusable named workflows
- site-specific pre-read automation
- controlled action sequences
- future extraction pipelines

### v3: Explore to Workflow

After workflow execution exists, SiteCLI should add exploration and synthesis tooling inspired by `opencli`:

- guided exploration
- action recording or semi-structured traces
- conversion into durable workflow definitions

That later system should build on top of the `sitecli.browser` core and the `sitecli.workflow` runtime instead of bypassing them.

## Provenance and Licensing

The repository may internalize or adapt implementation techniques from `bridgic-browser`, but this must be done with explicit provenance tracking and preserved license information.

Implementation rule:

- every copied or adapted third-party module must be traceable
- the original source repository and file path must be recorded
- the applicable license text must be retained in-repo

No code will be copied from `opencli` or `bridgic-browser` during the design phase. This rule applies when implementation starts.

## Decision Record

The following decisions are fixed by this design:

- New repo: yes
- Working repo name: `sitecli`
- CLI-first: yes
- Python-first: yes
- `v1` focus: universal reading
- Runtime style: one-shot command, not daemon-first
- Default output: rendered DOM HTML
- Alternate output: `--snapshot`
- Extra `v1` flag: `--scroll-bottom`
- Profile model: reuse existing Chrome user data, requiring normal Chrome to be closed
- Platforms in `v1`: macOS and Linux
- Workflow DSL: future Python-first redesign, not `opencli` compatibility
- Third-party reuse: internalize selected browser-core implementation with explicit provenance and license tracking

## Scope Check

This design is intentionally scoped to a single implementation plan centered on `v1` reading. It does not attempt to design the full workflow DSL or the full exploration system in detail. Those remain explicit later phases rather than hidden scope inside the first build.
