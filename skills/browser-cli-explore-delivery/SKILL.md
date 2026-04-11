---
name: browser-cli-explore-delivery
description: Use when website work must end as reusable browser-cli task artifacts rather than one-off chat notes, especially when success depends on validating runtime assumptions and choosing the right exploration mode.
---

# Browser CLI Explore Delivery

## Overview

Use `browser-cli` as the browser backend and converge successful work into
`task.py` plus `task.meta.json`. Keep workflow publication separate from task
logic.

## When to Use

Use this skill when:

- the browser path should become a reusable task
- the site depends on real browser execution, cookies, login context, or page state
- the output should end as `task.py` plus `task.meta.json`

Do not use this skill when:

- one-off browsing is enough
- the task is pure API/data work with no browser dependency
- `browser-cli` cannot be installed or used

## Phase Order

Always follow this order:

1. Preflight
2. Choose task mode
3. Explore with `browser-cli`
4. Converge to `task.py`
5. Distill `task.meta.json`
6. Optional publish gate
7. Publish `workflow.toml`

Never skip from exploration straight to `workflow.toml`.

## Quick Decisions

- Need dependency, runtime, profile, or artifact checks first: read
  [`references/preflight-and-runtime.md`](references/preflight-and-runtime.md)
- Need to decide whether the task is content-first, browser-state-first, login-state-first,
  or scroll-first: read
  [`references/task-modes.md`](references/task-modes.md)
- Need to decide which inputs users should actually see: read
  [`references/task-input-design.md`](references/task-input-design.md)
- If the task depends on response bodies, first verify whether the current
  runtime exposes them inline or materializes them as artifacts before choosing
  a fallback path.
- If the task depends on another runtime feature that `browser-cli` still does
  not expose, stop early and confirm instead of retrying blindly.

## 1. Preflight

- confirm `browser-cli`, `browser_cli`, Python, browser, and task-specific Python deps
- confirm the task will run in the same Python environment you just validated
- confirm profile assumptions such as login state, cookies, locale, and writable artifacts
- if the advertised CLI surface and the live daemon disagree, do one
  `browser-cli reload` before declaring a capability gap
- if anything is missing, produce a short install/fix plan and ask before changing the environment

Do not silently install `browser-cli`, browser dependencies, or Python packages.

## 2. Browser CLI Rules

- `browser-cli` is the only browser execution backend
- do not switch to direct Playwright as the main path
- use the smallest reliable signal for the current task mode
- prefer direct response-body capture when the current runtime already exposes
  it reliably; do not keep older fallback paths as the default
- stop once the successful path is deterministic
- stop once you hit a real capability gap; do not hide it behind retries
- a single runtime reset is allowed when a command is documented by the current
  CLI but rejected by the live daemon or backend

## 3. Explore

- capture only observations that change the next decision
- verify each critical step locally before assuming success
- refresh snapshots only when semantics changed
- keep exploration token usage low with targeted checks

## 4. Converge to `task.py`

- `task.py` is the single source of execution logic
- route browser actions through `browser_cli.task_runtime`
- helper functions, bounded retries, loops, and assertions are allowed
- direct Playwright and raw daemon handling are not the primary path
- keep exploration-only waits and retry knobs as internal defaults unless users benefit from controlling them

## 5. Distill `task.meta.json`

- keep: `task`, `environment`, `success_path`, `recovery_hints`, `failures`, `knowledge`
- record reusable environment assumptions, recovery patterns, and mode-specific lessons
- preserve failures that teach something reusable
- do not dump raw logs or chat transcripts

## 6. Publish Gate

Move to `workflow.toml` only when both are true:

- the task is already stable
- the user approved publication

If not, stop after `task.py` and `task.meta.json`.

## 7. Publish `workflow.toml`

`workflow.toml` wraps the task. It does not re-implement browser logic.

Use `browser-cli workflow validate` and `browser-cli workflow run` for published workflows.

## Done Criteria

Stop only when one of these states is true:

- preflight failed and the user declined installation
- a stable `task.py` plus `task.meta.json` has been produced
- the user approved publication and a working `workflow.toml` has also been produced

## Common Mistakes

- validating `browser-cli` in one Python environment and executing the task in another
- choosing the wrong task mode and exploring the page with the wrong signal first
- exposing exploration-only knobs as user-facing inputs
- assuming network capture never includes response bodies without checking the
  current runtime or artifact outputs
- treating a stale daemon/runtime mismatch as a permanent missing feature before
  trying one `browser-cli reload`
- retrying around a missing capability instead of stopping to confirm
- leaving the successful path only in chat instead of `task.py`
