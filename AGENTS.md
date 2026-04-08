# AGENTS.md

## Project Mission

SiteCLI is a `CLI-first`, `Python-first` browser tool for turning websites into reliable command-line readable surfaces first, then durable workflows later.

The repository starts with a narrow `read` command and is intentionally designed to grow into workflow execution and explore-to-workflow tooling without changing the browser core boundary.

## Current Phase

Current phase: design and planning.

Do not start implementing workflow engines, explorers, or generated site adapters before the `v1` read path is specified, planned, and reviewed.

## Frozen Product Decisions

The following decisions are currently fixed unless explicitly revised in a later spec:

- Primary interface is CLI.
- Primary implementation language is Python.
- `v1` only needs a one-shot `read` command.
- Default output is rendered DOM HTML.
- Alternate output is `--snapshot`.
- The only extra `v1` read flag is `--scroll-bottom`.
- The tool must reuse an existing local Chrome profile.
- The normal Chrome instance is expected to be closed before a run.
- `v1` targets stable Google Chrome first and should not silently swap browser families.
- `v1` must support macOS and Linux.
- Future workflow support should use a new Python-first DSL, not `opencli` YAML compatibility.

## Architectural Boundaries

- `app.cli` parses commands and owns help text and exit code behavior.
- `app.commands.read` owns the user-facing read contract.
- `app.runtime.read_runner` owns the one-shot reading lifecycle.
- `app.browser` owns Playwright launch, stealth, HTML capture, and snapshot/ref capture.
- `app.profiles` owns browser executable discovery, user data directories, profile names, and lock detection.
- `app.outputs` owns final body rendering to stdout.
- `app.workflow` is reserved for later phases and should not leak into `v1` command complexity.

Keep these boundaries intact. Do not push browser internals into the CLI layer or profile logic into random utility modules.

## Product Philosophy

`read` should stay opinionated and small.

If a feature request makes `read` look like a mini scripting language, that feature likely belongs in the future workflow layer instead.

Prefer explicit failure over invisible fallback. A successful run should mean the tool truly used the intended profile and produced the intended output mode.

Prefer keeping default behavior inside the command contract over adding user-tunable flags. If a behavior is needed for nearly every read, make it the default. If it is rare or site-specific, it likely belongs in the future workflow layer.

## Third-Party Reuse Rules

This repository may internalize selected implementation from `bridgic-browser`, but not as an opaque copy-paste dump.

Rules:

- Preserve original license requirements.
- Record provenance under `third_party/`.
- Keep adapted code isolated and understandable.
- Do not add a runtime dependency on the `bridgic-browser` package just to save short-term effort.
- Treat `opencli` as an architectural reference, not as a compatibility target.

## Testing Expectations

Prefer three layers:

- unit tests for profile resolution, output selection, and error mapping
- integration tests against local fixture sites for render and scroll behavior
- smoke tests against a small set of real sites for profile reuse and authenticated reads

Do not make CI depend primarily on unstable real websites.

## Documentation Expectations

Before significant scope changes:

- update the active design spec under `docs/superpowers/specs/`
- keep this file aligned with the latest approved architectural direction
- document any new third-party provenance before merging copied or adapted code

## Naming Note

The working repository name is currently `sitecli`. Renaming is allowed later if the project direction stays the same.
