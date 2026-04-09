# Browser CLI Semantic Ref, Task, Workflow, and Skill Implementation Plan

Date: 2026-04-09
Status: Ready for implementation
Related specs:

- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-09-browser-cli-v3a-semantic-ref-resolution-design.md`
- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-09-browser-cli-explore-task-workflow-design.md`
- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-09-browser-cli-backed-explore-delivery-skill-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current
environment. This document is the direct planning fallback and serves the same
purpose: an implementation-ready sequence for the next Browser CLI phases.

## Objective

Deliver the next stack on top of `v2` in the correct dependency order:

1. semantic ref resolution as a stable internal capability
2. a thin Python task runtime built on Browser CLI
3. task artifacts:
   - `task.py`
   - `task.meta.json`
4. workflow publication wrapper:
   - `workflow.toml`
5. a reusable agent skill that standardizes preflight, install gating,
   exploration, convergence, and publication using Browser CLI as the backend

The key architectural rule is:

- Browser CLI remains the browser execution substrate
- tasks remain the single source of execution logic
- workflows package tasks rather than re-implementing them
- the skill teaches agents how to use the system; it does not replace the
  system

## Out of Scope

The following are excluded from this plan:

- a public `browser-cli explore` command family
- a declarative browser-action DSL replacing Python tasks
- a marketplace or registry for published workflows
- direct Playwright as the primary task runtime path
- partial semantic ref support that leaves core ref-based actions split between
  old and new lookup behavior

## Delivery Strategy

Build this work in seven milestones:

1. semantic ref core
2. semantic ref integration into daemon-backed actions
3. task runtime and task artifact scaffolding
4. workflow manifest and workflow runner
5. reusable skill authoring
6. reference tasks and end-to-end examples
7. hardening, docs, and verification

The order matters. Task runtime and workflow publication should not land before
the semantic ref layer is ready because replayability depends on semantic ref
reconstruction.

## Design Constraints To Preserve

Implementation must preserve these approved decisions:

- Browser CLI remains the only browser execution backend.
- Semantic refs should adopt bridgic-style `RefData` and reconstruction rules.
- Browser CLI daemon, `X_AGENT_ID`, tabs, and JSON contracts remain intact.
- `task.py` is free Python in control flow, but browser actions must enter
  through a thin Browser CLI runtime API.
- `task.meta.json` stores structured knowledge, not raw transcripts.
- `workflow.toml` is operational packaging, not task logic duplication.
- The reusable skill must run preflight first and request user approval before
  installation.
- Workflow publication only happens after task stability and user approval.

## Repository Impact

Expected new or expanded package areas:

```text
src/browser_cli/
  refs/
  browser/
  daemon/
  tabs/
  task_runtime/
  workflow/
tests/
  unit/
  integration/
docs/
  superpowers/specs/
  superpowers/plans/
  examples/
```

Expected reusable external artifact areas:

```text
tasks/
  <task-id>/
    task.py
    task.meta.json
    workflow.toml
```

Expected skill output area outside the repo:

- a reusable skill package that documents how any agent should use Browser CLI
  for preflight, exploration, convergence, and publication

## Milestone 1: Semantic Ref Core

### Deliverables

- canonical `RefData` model
- tab-scoped snapshot registry
- snapshot generator upgraded to produce full ref metadata
- resolver module that can reconstruct locators from semantic refs

### Tasks

1. Create `src/browser_cli/refs/` with at least:
   - `models.py`
   - `snapshot_generator.py`
   - `registry.py`
   - `resolver.py`

2. Define the canonical ref record.
   Minimum fields:
   - `ref`
   - `role`
   - `name`
   - `text_content`
   - `nth`
   - `tag`
   - `interactive`
   - `frame_path`
   - `parent_ref`
   - `playwright_ref`
   - `selector_recipe`
   - `snapshot_id`
   - `page_id`
   - `captured_url`
   - `captured_at`

3. Internalize the relevant `bridgic-browser` snapshot and resolver logic into
   the new refs package, preserving provenance and license requirements.

4. Add a structured snapshot result type that contains:
   - tree text
   - full ref registry
   - snapshot metadata

5. Replace the current lightweight `last_snapshot_refs` tab state with a richer
   tab-scoped snapshot registry.

6. Add unit tests for deterministic ref generation, frame path handling, nth
   behavior, and parse/normalization.

### Acceptance Criteria

- The daemon can store and retrieve full semantic ref metadata per tab.
- Snapshot generation produces enough metadata for semantic reconstruction.
- Ref generation and parsing are covered by unit tests.

## Milestone 2: Semantic Ref Integration Into Actions

### Deliverables

- ref-based actions resolve through the new resolver
- stale and ambiguous refs surface explicit error codes
- direct DOM attribute lookup is no longer the sole source of truth

### Tasks

1. Replace `service.py` direct `data-browser-cli-ref` lookup with a shared
   resolver path.

2. Migrate these actions first:
   - `click`
   - `fill`
   - `select`
   - `eval-on`
   - `verify-state`
   - `verify-value`

3. Migrate the remaining ref-based actions:
   - `double-click`
   - `hover`
   - `focus`
   - `options`
   - `check`
   - `uncheck`
   - `scroll-to`
   - `drag`
   - `upload`

4. Preserve JSON action response shape for callers.

5. Add or standardize resolver-related error codes:
   - `REF_NOT_FOUND`
   - `STALE_REF`
   - `AMBIGUOUS_REF`
   - `NO_SNAPSHOT_CONTEXT`

6. Expand integration tests to verify:
   - semantic reconstruction after re-render
   - stale-ref failure on changed semantics
   - iframe resolution
   - generic/text/noise-role recovery paths

### Acceptance Criteria

- All ref-based actions use the semantic resolver.
- Browser CLI no longer depends on DOM markers as the only correct lookup path.
- Resolver failures are explicit and test-covered.

## Milestone 3: Task Runtime And Artifact Scaffolding

### Deliverables

- thin Python Browser CLI task runtime
- canonical task entrypoint convention
- task artifact scaffolds
- `task.meta.json` schema and validation

### Tasks

1. Create `src/browser_cli/task_runtime/` with at least:
   - `client.py`
   - `flow.py`
   - `models.py`
   - `errors.py`

2. Make the runtime call Browser CLI daemon actions through the existing JSON
   contract instead of direct Playwright APIs.

3. Define the canonical task entrypoint contract.
   Recommended shape:
   - `run(flow, inputs) -> dict`

4. Provide a mixed input model:
   - script defaults allowed
   - external overrides supported structurally

5. Add task helper methods that reduce repeated agent boilerplate, such as:
   - snapshot capture
   - semantic ref operation wrappers
   - explicit wait helpers
   - retry helpers
   - artifact writing helpers

6. Define a schema or validation contract for `task.meta.json`.

7. Add example task directory scaffolds under `docs/examples/` or `tasks/_templates/`.

### Acceptance Criteria

- A sample `task.py` can run without shelling out to raw `browser-cli` commands.
- The task runtime is a thin wrapper, not a second browser engine.
- `task.meta.json` can be validated for required sections and field shapes.

## Milestone 4: Workflow Manifest And Runner

### Deliverables

- `workflow.toml` format
- TOML loader and validation
- workflow runner that wraps task execution
- output routing and hook execution

### Tasks

1. Create `src/browser_cli/workflow/` with at least:
   - `models.py`
   - `loader.py`
   - `runner.py`
   - `hooks.py`

2. Define and validate the manifest sections:
   - `[workflow]`
   - `[task]`
   - `[inputs]`
   - `[schedule]`
   - `[outputs]`
   - `[hooks]`
   - `[runtime]`

3. Implement task resolution from workflow config:
   - task path
   - metadata path
   - entrypoint

4. Implement input merging:
   - workflow defaults
   - runtime overrides

5. Implement output routing and hook handling.

6. Keep workflow runner intentionally thin:
   - it executes tasks
   - it does not re-encode browser logic

7. Add unit tests for TOML parsing, input merge behavior, and hook invocation.

### Acceptance Criteria

- A workflow can execute a task with externalized operational configuration.
- Workflow execution does not duplicate task logic.
- TOML validation catches missing core fields.

## Milestone 5: Reusable Skill Authoring

### Deliverables

- reusable skill package or skill files
- preflight behavior
- install approval gate
- explore-to-task convergence guidance
- publish gate behavior

### Tasks

1. Author the reusable skill outside or alongside repo docs in the target skill
   location expected by the agent environment.

2. Encode the required phase order:
   - preflight
   - install plan gate
   - explore
   - task convergence
   - publish gate
   - workflow packaging

3. Encode hard requirements:
   - use Browser CLI as backend
   - ask for approval before installation
   - stop if installation is declined
   - stop at task artifacts if workflow publication is not yet approved

4. Add guidance for low-token exploration:
   - prefer semantic refs
   - use targeted checks over repeated large snapshots
   - store durable learnings in metadata rather than chat

5. Add explicit publication requirements:
   - schedule
   - outputs
   - notifications or hooks

6. Add self-check examples for the skill if the skill system supports them.

### Acceptance Criteria

- Any agent following the skill will use Browser CLI consistently.
- The skill handles missing-environment cases safely.
- The skill distinguishes task convergence from workflow publication.

## Milestone 6: Reference Tasks And End-To-End Examples

### Deliverables

- one or two reference tasks
- one published workflow example
- end-to-end validation using local fixtures

### Tasks

1. Create at least one reference task from the existing local fixture site.
   Candidate examples:
   - open -> snapshot -> fill/select/check -> verify -> export
   - lazy-load page capture with scroll-until-stable helper

2. Create a corresponding `task.meta.json` for each example.

3. Create at least one `workflow.toml` that wraps a reference task.

4. Add example docs showing:
   - direct task execution
   - workflow execution
   - expected artifacts

5. Add integration coverage that runs:
   - workflow runner
   - task runtime
   - Browser CLI daemon
   - local fixture page

### Acceptance Criteria

- The repository contains a concrete end-to-end example.
- The full path from task to workflow is testable locally.

## Milestone 7: Hardening, Docs, And Verification

### Deliverables

- updated README and AGENTS guidance
- explicit migration notes from `v2`
- final verification matrix

### Tasks

1. Update repo docs to explain:
   - semantic refs
   - task runtime usage
   - task artifact layout
   - workflow publication model

2. Update smoke checklist to cover:
   - semantic ref recovery
   - task execution
   - workflow execution

3. Ensure tests cover:
   - semantic ref core
   - action integration
   - task runtime
   - workflow wrapper
   - representative end-to-end examples

4. Confirm that the reusable skill instructions match the implemented runtime
   and artifact model.

### Acceptance Criteria

- Docs and tests reflect the final system shape.
- The task and workflow model is understandable without relying on prior chat
  history.

## Recommended Implementation Slices

To keep momentum while reducing risk, implement in these slices:

1. `RefData + snapshot registry`
2. `Resolver + first migrated action family`
3. `All ref-based action migration`
4. `Task runtime client + flow`
5. `task.meta.json` schema + examples
6. `workflow.toml` loader + runner
7. `Reusable skill authoring`
8. `Reference task + end-to-end test`
9. `Docs hardening`

Each slice should end with passing tests before moving on.

## Risks To Watch

- partial semantic-ref migration that leaves mixed resolution behavior
- task runtime growing into a second browser engine
- workflow wrapper duplicating task logic
- skill instructions drifting from runtime reality
- metadata becoming a raw log dump instead of structured knowledge

## Final Acceptance Criteria

This plan is complete only when all of the following are true:

- semantic refs are the canonical Browser CLI ref model
- ref-based actions reconstruct locators semantically
- tasks run through a thin Browser CLI runtime API
- tasks produce structured metadata sidecars
- workflows package tasks rather than re-implementing them
- a reusable skill exists to guide agents through preflight, exploration,
  convergence, and publication
- end-to-end local tests prove the full path works without relying on live-site
  luck
