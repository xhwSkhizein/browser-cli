# Browser-CLI-Backed Explore Delivery Skill Design

Date: 2026-04-09
Status: Drafted for review
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

This spec defines a reusable skill that any agent can use to turn a user goal
into browser automation deliverables by relying on `browser-cli` as the browser
execution backend.

The skill is intentionally **not** project-specific in scope, even though the
initial design is documented in the `browser-cli` repository.

Its job is to guide an agent through:

1. preflight validation
2. optional installation planning and approval
3. browser-backed exploration using `browser-cli`
4. convergence into:
   - `task.py`
   - `task.meta.json`
5. optional publication into:
   - `workflow.toml`

The skill does not replace `browser-cli`. It standardizes **how agents use**
`browser-cli`.

## Problem Statement

Even with a strong browser backend, agent quality varies widely if every agent:

- invents its own exploration process
- chooses different runtime entrypoints
- stores results in inconsistent formats
- loses failure learnings in chat history
- publishes brittle workflows too early

To make `browser-cli` genuinely reusable by many agents and many users, the
ecosystem needs a stable skill that teaches agents:

- how to detect whether the backend is available
- how to request installation approval when it is not
- how to explore a site with low waste
- how to stop exploring once a deterministic path is found
- how to package results into the approved artifact model

## Goals

- Make the skill reusable across projects and users.
- Require `browser-cli` as the default browser backend.
- Require the Browser CLI Python runtime/client API as the preferred task
  execution interface.
- Detect missing prerequisites before exploration starts.
- Request explicit user approval before performing installation steps.
- End early if installation is required and the user declines.
- Standardize artifact outputs:
  - `task.py`
  - `task.meta.json`
  - optionally `workflow.toml`
- Keep workflow publication gated behind user approval and explicit runtime
  configuration.

## Non-Goals

- The skill does not re-implement browser automation.
- The skill does not replace `browser-cli` CLI or daemon behavior.
- The skill does not require direct Playwright usage as the primary path.
- The skill does not auto-publish workflows without user approval.
- The skill does not treat every successful exploration as ready for workflow
  publication.

## Chosen Direction

The skill should be a reusable agent workflow that treats `browser-cli` as a
required execution substrate and enforces a staged process:

1. `Preflight`
2. `Install Plan Gate`
3. `Explore`
4. `Task Convergence`
5. `Publish Gate`
6. `Workflow Packaging`

This structure makes agent behavior more predictable and keeps task logic,
operational workflow config, and environment setup concerns separate.

## Skill Contract

The skill must teach agents to produce the following outputs.

### Required Deliverables

- `task.py`
- `task.meta.json`

### Optional Deliverable

- `workflow.toml`

The optional deliverable must only be created if:

- the task has reached a stable replayable state
- the user approves moving to publication
- the user provides required workflow runtime information

## Backend Assumption

The skill assumes that browser execution should flow through:

- `browser-cli` CLI and daemon
- future `browser-cli` Python task runtime/client API

The intended hierarchy is:

- exploration time: agent uses `browser-cli`
- task runtime time: `task.py` uses the Browser CLI Python runtime/client API
- publication time: `workflow.toml` wraps the task

The skill should explicitly discourage:

- direct Playwright as the default path
- ad hoc shell pipelines as the primary task implementation strategy
- maintaining a second browser state model outside Browser CLI

## Phase 1: Preflight

Before exploring anything, the skill must check whether the environment is
capable of using `browser-cli`.

### Preflight Checks

The skill should verify:

- `browser-cli` CLI is installed and callable
- `browser_cli` Python runtime/client API is importable, when the task layer
  needs it
- supported Python version is available
- Google Chrome is installed and discoverable
- Playwright dependencies required by Browser CLI are available
- the current environment has a writable workspace for task artifact output

### Preflight Outcomes

Possible outcomes:

- `ready`
- `needs_install`
- `unsupported_environment`

If the environment is unsupported, the skill should stop with a clear
explanation instead of attempting partial exploration.

## Phase 2: Install Plan Gate

If preflight returns `needs_install`, the skill must not silently install
dependencies.

The required behavior is:

1. generate a concrete installation plan
2. show the plan to the user
3. request approval
4. only execute installation if the user approves
5. stop immediately if the user declines

### Install Plan Contents

The plan should specify:

- what is missing
- what commands would be run
- which repository or package source would be used
- any notable system-side effects

This keeps the skill safe and predictable for general reuse.

## Phase 3: Explore

Explore begins only after preflight is successful.

### Definition

Explore is an agent activity, not a Browser CLI subcommand.

The input is a user goal.

The process is:

- open pages
- inspect snapshots and page state
- try candidate actions
- validate success conditions
- discard dead ends
- collect only durable learnings
- converge on a deterministic execution path

### Explore Method

The skill should instruct agents to prefer:

- Browser CLI primitives
- semantic refs when available
- explicit waits and verification
- bounded retries
- local artifacts over conversational memory

The skill should instruct agents to avoid:

- free-form repeated re-exploration without convergence
- hidden assumptions with no verification step
- large repeated snapshots when smaller targeted checks would suffice
- overfitting to one transient page rendering when stability is uncertain

### Low-Token Guidance

The skill should explicitly recommend:

- use snapshot once, then operate by ref where possible
- use targeted `eval` or verification calls instead of repeated large snapshots
- store durable learnings in `task.meta.json`
- stop exploring when the path is sufficiently stable instead of optimizing
  forever

## Phase 4: Task Convergence

The default goal of the skill is to converge exploration into a task artifact.

### `task.py`

The skill must require that:

- the task is executable Python
- browser actions go through the Browser CLI Python runtime/client API
- control flow may be free Python
- the success path is clear and replayable
- waits, assertions, and key validations are explicit

### `task.meta.json`

The skill must require that metadata capture:

- the goal
- the environment assumptions
- the validated success path
- key refs or semantic anchors
- recovery hints
- failures with reusable value
- durable site knowledge

### Completion Standard

The skill should define exploration as complete only when:

- the task can run without depending on the conversation history
- critical waits and validations are encoded
- known fragile points are documented
- the metadata is useful to a future agent continuing the work

## Phase 5: Publish Gate

The skill must not automatically generate `workflow.toml` after every successful
task.

Workflow publication is a second gate.

It is only allowed when:

- the task is stable enough to reuse
- the user wants a user-facing deliverable
- the user approves publication

### Required User Inputs Before Workflow Publication

The skill must explicitly collect or confirm:

- when the workflow should run
- where outputs should go
- whether post-run hooks or notifications are required
- any retry or timeout expectations that matter at the workflow level

If these are not available, the skill should stop at `task.py + task.meta.json`.

## Phase 6: Workflow Packaging

If the publish gate is satisfied, the skill may generate `workflow.toml`.

### Workflow Role

The skill must treat the workflow as:

- a published wrapper around the task
- user-facing operational configuration
- not a second implementation of browser logic

### Workflow Contents

The skill should instruct agents to encode:

- task path
- task metadata path
- inputs and defaults
- scheduling
- outputs
- runtime policy
- hooks

The skill must explicitly avoid duplicating browser interaction steps inside the
workflow config.

## Artifact Standards

### Directory Layout

The skill should recommend a consistent layout such as:

```text
<task-dir>/
  task.py
  task.meta.json
  workflow.toml
  artifacts/
```

### Naming

The skill should encourage:

- stable task ids
- descriptive task names
- artifact names that do not rely on chat-specific context

## Failure Policy

The skill should teach agents to distinguish:

- environment failure
- installation-blocked failure
- exploration failure
- unstable-task failure
- publication-blocked failure

This distinction is important because the correct next step differs:

- environment failure may require installation or system changes
- exploration failure may require more probing
- unstable-task failure means do not publish yet
- publication-blocked failure means wait for user input

## Agent Behavior Rules

The skill should enforce the following behavior rules.

### Required

- use `browser-cli` as the browser backend
- run preflight before exploration
- ask for approval before installation
- stop if installation is required and declined
- converge into `task.py + task.meta.json`
- ask for user approval before publishing `workflow.toml`

### Discouraged

- direct Playwright as the first implementation choice
- publishing workflows from one lucky run
- stuffing raw transcripts into metadata
- coupling task execution logic to one specific chat session

## Testing Expectations

The skill should instruct agents to verify:

- environment readiness
- deterministic task replay
- metadata completeness
- workflow wrapper correctness if publication occurs

The skill should also encourage local fixture-driven validation where possible,
not only live-site optimism.

## Acceptance Criteria

The skill design is successful when an agent using it will:

- detect whether Browser CLI is available
- request approval before installing missing prerequisites
- stop if installation is declined
- use Browser CLI to explore a user task
- converge the task into `task.py + task.meta.json`
- only move to `workflow.toml` when the task is stable and the user approves
- preserve reusable task knowledge instead of losing it in chat history

