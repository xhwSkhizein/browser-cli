---
name: browser-cli-explore-delivery
description: Use when an agent needs to explore a website with browser-cli and converge the result into reusable task.py, task.meta.json, and optionally workflow.toml artifacts.
---

# Browser CLI Explore Delivery

## Overview

Use this skill when browser automation work should end as reusable delivery
artifacts instead of staying in chat history. The browser backend must be
`browser-cli`; task logic must converge into `task.py`, metadata into
`task.meta.json`, and workflow publication must stay separate from task logic.

## When to Use

Use this skill when:

- the goal is to explore a site and turn the successful path into a reusable task
- the work should use `browser-cli` rather than direct Playwright
- the output should become `task.py` plus `task.meta.json`
- a stable task may later be published as `workflow.toml`

Do not use this skill when:

- the user only wants one-off browsing with no reusable artifact
- the task is purely API/data work with no browser dependency
- the environment is not allowed to install or use `browser-cli`

## Phase Order

Always follow this order:

1. Preflight
2. Install plan gate
3. Explore with `browser-cli`
4. Converge to `task.py`
5. Distill `task.meta.json`
6. Optional publish gate
7. Publish `workflow.toml`

Never skip from exploration straight to `workflow.toml`.

## 1. Preflight

Check these items before exploring:

- `browser-cli` command is available
- `browser_cli` Python package is importable
- Python version is compatible
- Chrome is installed
- Playwright dependencies are usable

If all checks pass, continue.

If anything is missing:

- produce a short installation plan
- ask the user for approval before executing it
- if the user declines, stop

Do not silently install `browser-cli` or browser dependencies.

## 2. Browser CLI Rules

These rules are strict:

- use `browser-cli` as the only browser execution backend
- prefer semantic refs and snapshots over brittle selectors
- do not switch to direct Playwright as the main path
- do not invent a second runtime when `browser-cli` already exposes the action
- keep exploration token usage low by using targeted checks and small snapshots

Exploration can use raw CLI actions such as:

- `browser-cli open`
- `browser-cli snapshot`
- `browser-cli click`
- `browser-cli fill`
- `browser-cli eval`
- `browser-cli wait`
- `browser-cli html`

For reusable tasks, prefer the Python runtime API:

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    flow.open(inputs["url"])
    snapshot = flow.snapshot()
    ref = snapshot.find_ref(role="button", name="Reveal Message")
    flow.click(ref)
    flow.wait_text("Revealed", timeout=5)
    return {"html": flow.html()}
```

## 3. Explore

Explore is an agent activity, not a `browser-cli` subcommand.

During exploration:

- state the goal clearly
- capture only the observations needed to move forward
- validate each critical step before assuming success
- reuse semantic refs where possible
- refresh snapshots when semantics change
- stop exploring once the path is deterministic

Prefer:

- small snapshots
- explicit waits
- local verification after each important action

Avoid:

- repeated full-page snapshots with no hypothesis
- relying on transient DOM attributes
- leaving key waits or assertions implicit

## 4. Converge To `task.py`

`task.py` is the single source of execution logic.

Requirements:

- use free Python for control flow
- route browser actions through `browser_cli.task_runtime`
- support structured external inputs
- include only the stable success path and bounded recovery logic

Allowed:

- helper functions
- retries
- bounded loops
- assertions

Not allowed as the primary path:

- direct Playwright
- raw daemon protocol handling
- copying workflow configuration into Python

## 5. Distill `task.meta.json`

`task.meta.json` must contain distilled knowledge, not transcripts.

Keep these sections:

- `task`
- `environment`
- `success_path`
- `recovery_hints`
- `failures`
- `knowledge`

Only preserve failures that teach something reusable, such as:

- a stale-ref recovery pattern
- a lazy-load wait point
- a login assumption
- an anti-bot workaround

Do not dump raw logs or full chat history into metadata.

## 6. Publish Gate

Do not publish a workflow automatically.

Only move to `workflow.toml` when both are true:

- the task is already stable
- the user approves publication

Before publishing, collect:

- when it should run
- where outputs should go
- what hooks or notifications should run

If the user has not approved publication, stop after `task.py` and
`task.meta.json`.

## 7. Publish `workflow.toml`

`workflow.toml` is the user-facing wrapper around the task.

Rules:

- workflow config packages the task
- workflow config does not re-implement browser logic
- scheduling, outputs, runtime policy, and hooks live in TOML
- task behavior stays in `task.py`

Use `browser-cli workflow validate` and `browser-cli workflow run` to validate
and execute published workflows.

## Done Criteria

Stop only when one of these states is true:

- preflight failed and the user declined installation
- a stable `task.py` plus `task.meta.json` has been produced
- the user approved publication and a working `workflow.toml` has also been produced

## Common Mistakes

- Installing `browser-cli` without approval
- Exploring with direct Playwright even though `browser-cli` is available
- Leaving the successful path only in chat instead of `task.py`
- Treating `task.meta.json` as a debug dump
- Publishing `workflow.toml` before the task is stable
