# AGENTS.md

## Project Mission

Browser CLI is a `CLI-first`, `Python-first` browser tool for turning websites into reliable command-line readable surfaces first, then durable workflows later.

The repository started with a narrow `read` command and now includes:

- `v1` read
- `v2` daemon-backed browser actions
- `v3a` semantic ref reconstruction
- `v3b` task runtime, task artifacts, and workflow packaging

Future exploration tooling must build on these layers rather than bypass them.

## Current Phase

Current phase: implemented `v1 read`, `v2` daemon-backed agent actions, `v3a` semantic refs, and `v3b` task/workflow packaging.

Do not introduce a public `browser-cli explore` surface or a second browser runtime. Exploration remains an agent activity layered on top of `browser-cli`.

## Frozen Product Decisions

The following decisions are currently fixed unless explicitly revised in a later spec:

- Primary interface is CLI.
- Primary implementation language is Python.
- `v1` only needs a one-shot `read` command.
- Default output is rendered DOM HTML.
- Alternate output is `--snapshot`.
- The only extra `v1` read flag is `--scroll-bottom`.
- Managed profile mode is the default browser backend.
- Managed profile mode uses Browser CLI's dedicated Chrome data root at `~/.browser-cli/default-profile`.
- Extension mode is the preferred real-Chrome backend when the Browser CLI extension is connected and healthy.
- `browser-cli status` is the first-line lifecycle diagnosis command.
- Top-level `browser-cli reload` is reserved for Browser CLI runtime reset.
- Page reload remains available, but the public CLI spelling is `browser-cli page-reload`.
- If extension mode is unavailable or disconnects, Browser CLI may automatically rebind to the managed Playwright backend only at safe idle points.
- Driver rebinding may happen automatically only at safe idle points, and it must be reported as `state_reset` rather than treated as perfectly continuous state.
- `v1` targets stable Google Chrome first and should not silently swap browser families.
- `v1` must support macOS and Linux.
- `v2` uses one daemon-managed browser instance.
- `v2` command output is JSON-first.
- `v2` uses `X_AGENT_ID` to isolate tab visibility and active-tab state.
- `v2` must not expose session concepts or global `--page` targeting flags.
- Semantic refs should follow bridgic-style reconstruction rather than DOM marker lookup.
- Daemon-side semantic refs remain the only ref system; drivers must not fork product semantics.
- Dual-driver support must preserve one CLI/daemon JSON contract across both `playwright_driver` and `extension_driver`.
- Driver parity is enforced through an explicit driver contract. Do not reintroduce dynamic backend passthrough through `__getattr__` or similar implicit escape hatches.
- Reusable browser logic belongs in `task.py` through `browser_cli.task_runtime`.
- `task.meta.json` stores structured knowledge, not transcripts.
- `workflow.toml` publishes a task; it must not duplicate task logic.
- Future workflow support stays Python-first and TOML-based, not `opencli` YAML compatibility.

## Architectural Boundaries

- `browser_cli.cli` parses commands and owns help text and exit code behavior.
- `browser_cli.commands.read` owns the user-facing read contract.
- `browser_cli.commands.status` owns lifecycle diagnosis output.
- `browser_cli.commands.reload` owns lifecycle reset orchestration.
- `browser_cli.runtime.read_runner` owns the one-shot read contract and routes it through the daemon-managed browser lifecycle.
- `browser_cli.browser` owns Playwright launch, stealth, HTML capture, and Playwright-specific low-level browser primitives.
- `browser_cli.refs` owns semantic ref models, snapshot generation, registry state, and locator reconstruction.
- `browser_cli.daemon` owns the long-lived daemon, transport, and browser lifecycle.
- `browser_cli.drivers` owns the backend driver interface plus `playwright_driver` and `extension_driver`.
- `browser_cli.extension` owns the extension transport, handshake, heartbeat, and WebSocket session state.
- `browser_cli.actions` owns the daemon-backed action registry and CLI command metadata.
- `browser_cli.agent_scope` owns `X_AGENT_ID` resolution.
- `browser_cli.tabs` owns tab visibility, active-tab tracking, and busy-state conflict rules.
- `browser_cli.profiles` owns browser executable discovery, user data directories, profile names, and lock detection.
- `browser_cli.outputs` owns final rendering for both content-first and JSON-first surfaces.
- `browser_cli.task_runtime` owns the thin Python runtime used by `task.py`.
- `browser_cli.workflow` owns manifest loading, validation, hooks, and workflow execution.

Keep these boundaries intact. Do not push browser internals into the CLI layer or profile logic into random utility modules.

## Product Philosophy

`read` should stay opinionated and small.

If a feature request makes `read` look like a mini scripting language, that feature likely belongs in the future workflow layer instead.

The daemon-backed command surface should stay explicit and help-driven. Avoid hiding operational complexity behind magical behavior, but also do not expose session management or lock protocols to callers. Prefer optimistic behavior with explicit conflict errors.

Prefer `browser-cli status` as the first diagnostic step before ad hoc daemon cleanup or browser restarts. If Browser CLI runtime state is bad, prefer `browser-cli reload` over manual process killing.

Prefer explicit failure over invisible browser-family fallback. A successful run should mean the tool used either the preferred Chrome profile or the documented Browser CLI fallback profile and produced the intended output mode.

Prefer keeping default behavior inside the command contract over adding user-tunable flags. If a behavior is needed for nearly every read, make it the default. If it is rare or site-specific, it likely belongs in the future workflow layer.

Prefer one product control plane and two interchangeable browser backends over two product surfaces. If a change requires exposing driver choice or extension mechanics to normal callers, the layering is probably wrong.

## Third-Party Reuse Rules

This repository may internalize selected implementation from `bridgic-browser`, but not as an opaque copy-paste dump.

Rules:

- Preserve original license requirements.
- Record provenance under `third_party/`.
- Keep adapted code isolated and understandable.
- Do not add a runtime dependency on the `bridgic-browser` package just to save short-term effort.
- Treat `opencli` as an architectural reference, not as a compatibility target.

## Testing Expectations

Prefer four layers:

- unit tests for profile resolution, output selection, and error mapping
- unit tests for semantic ref parsing and deterministic ref generation
- unit tests for action-catalog parity against the adopted `bridgic-browser` command surface
- unit tests for `X_AGENT_ID`, tab ownership, and busy-state conflict rules
- unit tests for task metadata validation, workflow loading, and hook execution
- integration tests against local fixture sites for render, scroll behavior, daemon lifecycle, and every daemon-backed action family
- integration tests for semantic ref recovery and iframe reconstruction
- integration tests for task runtime plus workflow execution against local fixtures
- smoke tests against a small set of real sites for profile reuse and authenticated reads
- parity-focused tests for the shared driver contract and for daemon action behavior across driver domains

Do not make CI depend primarily on unstable real websites.

The local integration fixture should stay comprehensive enough to validate:

- navigation, tabs, and history
- snapshot and rendered HTML capture
- semantic ref recovery after DOM re-render
- explicit stale and ambiguous ref failures
- iframe reconstruction
- ref-based click/fill/select/check/hover/focus/drag/upload flows
- keyboard and mouse flows
- waits, eval, and verification
- console, network, dialog, trace, video, screenshot, and PDF flows
- cookies, localStorage save/load, and `X_AGENT_ID` isolation
- workflow validation and workflow execution
- driver parity for managed profile mode and extension mode on the current public core action set
- granular extension capability reporting, including visible required-capability gaps in `status`
- extension trace and deferred video parity on the same public contract as Playwright mode
- chunked extension artifact transport for screenshot, PDF, trace, and deferred video saves
- safe-point driver rebinding with explicit `state_reset` metadata
- extension workspace-window isolation from normal user tabs

## Documentation Expectations

Before significant scope changes:

- update the active design spec under `docs/superpowers/specs/`
- keep this file aligned with the latest approved architectural direction
- document any new third-party provenance before merging copied or adapted code

## Lint And Guard Discipline

Architecture rules and frozen product contracts are executable, not just descriptive.

- `scripts/lint.sh` owns repository lint execution.
- `scripts/guard.sh` owns architecture, product-contract, and doc-sync guards.
- `scripts/check.sh` runs both lint and guard in the expected order.
- The guard implementations live under `scripts/guards/`.
- After each code change, run lint and guard.
- After each code change, run `scripts/lint.sh` and `scripts/guard.sh`, or run `scripts/check.sh`.
- When diagnosing runtime problems, run `browser-cli status` before making changes.
- When Browser CLI daemon/workspace state needs a reset, use `browser-cli reload`.
- When architecture, package boundaries, or frozen product decisions change, update `AGENTS.md` and the corresponding guard rules in the same change.
- When a new top-level `browser_cli` package, public CLI surface, or major iteration phase is introduced, update both this file and the guard expectations before considering the change complete.

## Naming Note

- Repository name: `browser-cli`
- CLI command name: `browser-cli`
- Python package root: `browser_cli`
