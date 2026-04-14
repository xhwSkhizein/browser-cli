---
name: browser-cli-converge
description: Turn validated Browser CLI exploration into stable task.py execution logic and task validation.
---

# Browser CLI Converge

## Overview

Use this skill after exploration has already validated the success path.
Its job is to encode that evidence into stable `task.py` logic and keep the
implementation aligned with `task.meta.json`.

## When to Use

Use this skill when:

- the success path is already validated
- the task now needs executable Browser CLI task code
- waits, assertions, and artifacts are known well enough to encode

Do not use this skill when:

- the site still has unresolved evidence gaps
- the task mode is still unclear
- validation failures show the metadata is incomplete

## Hard Rules

- task.py is the single source of execution logic
- browser interactions must go through `browser_cli.task_runtime.Flow`
- task code must stay aligned with task.meta.json
- keep exploration-only retries, branches, and debug logic out of the final task
- validate with `browser-cli task validate`
- use `browser-cli task run` when runtime proof is needed
- if validation exposes an evidence gap, go back to `browser-cli-explore`

## Phase Order

1. Read the validated `task.meta.json`
2. Encode the stable success path in `task.py`
3. Add explicit waits, assertions, and artifact writes
4. Verify metadata-code alignment
5. Run `browser-cli task validate`
6. Run `browser-cli task run` if the task shape requires live proof
7. If evidence is missing, return to exploration instead of guessing

## Done Criteria

This skill is complete when:

- `task.py` replays the validated path
- waits and assertions are explicit
- the code and metadata describe the same workflow
- task validation passes

## Common Mistakes

- bypassing the task runtime with direct Playwright
- encoding guesses instead of validated waits or refs
- letting metadata and code drift apart
- patching around a missing exploration lesson instead of going back
