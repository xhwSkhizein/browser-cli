---
name: browser-cli-delivery
description: Orchestrate Browser CLI exploration, convergence, validation, and optional automation packaging for reusable web tasks.
---

# Browser CLI Delivery

## Overview

Use this as the main entrypoint when the user wants a reusable Browser CLI web
task rather than one-off browsing. The default endpoint is stable
`task.py + task.meta.json`. `automation.toml` generation and publish are
optional user-driven branches.

## When to Use

Use this skill when:

- the user wants a reusable browser task
- the work may require exploration, iteration, and validation
- the final deliverable should match Browser CLI task artifacts

Do not use this skill when:

- one-off browsing is enough
- the task is not Browser CLI based
- the work is already scoped to only one lower-level skill

## Hard Rules

- this is the main user-facing skill
- call `browser-cli-explore` when evidence is missing
- call `browser-cli-converge` when the success path is validated
- treat `browser-cli read` as a one-shot content-first capture, not the default interactive exploration loop
- default completion is `task.py + task.meta.json`
- `automation.toml` and publish are optional and require user choice
- If validation fails because evidence is missing, go back to explore
- do not publish by default

## Phase Order

1. Preflight: confirm Browser CLI, Python environment, login/profile, and site assumptions
2. Explore: call `browser-cli-explore` to choose the smallest reliable Browser CLI signal, validate the task mode, and capture feedback
3. Converge: call `browser-cli-converge` to encode the stable path in `task.py`
4. Validate: run task validation and decide whether to fix code or return to explore
5. Optional automation: ask whether to create `automation.toml`
6. Optional publish: ask whether to run Browser CLI automation publish

## Done Criteria

This skill is complete when:

- `task.py + task.meta.json` are stable
- validation passed
- optional automation work is either completed or intentionally skipped by the user

## Common Mistakes

- skipping metadata capture
- converging before the success path is real
- treating `read` output as the default exploration primitive instead of letting `browser-cli-explore` choose the smallest reliable signal
- generating automation packaging too early
- treating one successful page run as enough evidence
