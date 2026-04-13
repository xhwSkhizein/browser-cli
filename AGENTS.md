# AGENTS.md

## Project Mission

Browser CLI is a `CLI-first`, `Agent-first` browser tool for AI agents. The repository has three durable surfaces:

- `browser-cli read` for one-shot rendered HTML or snapshot capture
- daemon-backed browser actions for persistent interactive control
- `task.py + task.meta.json + workflow.toml` for reusable packaged workflows
- Workflow Publish Layer is a persistent local workflow service with a Web UI primary control surface.

The job of this file is not to restate every file in the repo. It should help an agent answer: what is the contract, where is the implementation, and where should a change land first.

## System Snapshot

- Primary interface is CLI.
- Primary implementation language is Python.
- `read` stays intentionally small: one URL positional plus `--snapshot` and `--scroll-bottom`.
- Managed profile mode is the default browser backend.
- Managed profile mode uses Browser CLI's dedicated Chrome data root at `~/.browser-cli/default-profile`.
- Extension mode is the preferred real-Chrome backend when the Browser CLI extension is connected and healthy.
- `browser-cli status` is the first-line lifecycle diagnosis command.
- `browser-cli reload` is the runtime reset command; page reload remains public as `browser-cli page-reload`.
- `runtime-status` includes a daemon-owned `presentation` snapshot; `browser-cli status` and the extension popup must render that shared state rather than inventing their own classifier.
- `v1` targets stable Google Chrome first and should not silently swap browser families.
- `v2` uses one daemon-managed browser instance.
- `v2` command output is JSON-first.
- `v2` uses `X_AGENT_ID` to isolate tab visibility and active-tab state.
- `v2` must not expose session concepts or global `--page` targeting flags.
- Semantic refs should follow bridgic-style reconstruction rather than DOM marker lookup.
- Daemon-side semantic refs remain the only ref system; drivers must not fork product semantics.
- Dual-driver support must preserve one CLI/daemon JSON contract across both `playwright_driver` and `extension_driver`.
- Driver parity is enforced through an explicit driver contract. Do not reintroduce dynamic backend passthrough through `__getattr__` or similar implicit escape hatches.
- Driver rebinding may happen automatically only at safe idle points, and it must be reported as `state_reset` rather than treated as perfectly continuous state.
- Reusable browser logic belongs in `task.py` through `browser_cli.task_runtime`.
- `task.meta.json` stores structured knowledge, not transcripts.
- `workflow.toml` publishes a task; it must not duplicate task logic.
- Do not introduce a public `browser-cli explore` surface or a second browser runtime. Exploration remains an agent activity layered on top of Browser CLI.
- The extension popup is a human-facing runtime observer and light recovery surface. Agent feedback still flows through command responses and `runtime-status`.

## Rapid Code Map

Use this section first. Start from the user question, then jump to the owning implementation.

- CLI shape, command names, help text, and top-level parser wiring:
  `src/browser_cli/cli/main.py`
- Daemon-backed command catalog, arguments, aliases, and request builders:
  `src/browser_cli/actions/cli_specs.py`
- Generic action command execution:
  `src/browser_cli/commands/action.py`
- One-shot read contract and URL normalization:
  `src/browser_cli/commands/read.py`
- One-shot read orchestration and daemon bootstrap path:
  `src/browser_cli/runtime/read_runner.py`
- Runtime diagnosis and user-facing lifecycle guidance:
  `src/browser_cli/commands/status.py`
- Shared daemon runtime presentation classifier:
  `src/browser_cli/daemon/runtime_presentation.py`
- Runtime reset flow:
  `src/browser_cli/commands/reload.py`
- Workflow CLI entrypoints:
  `src/browser_cli/commands/workflow.py`
- Workflow service client, local API, scheduler, persistence, and Web UI:
  `src/browser_cli/workflow/service/*`, `src/browser_cli/workflow/api/*`, `src/browser_cli/workflow/persistence/*`, `src/browser_cli/workflow/scheduler/*`, `src/browser_cli/workflow/web/*`

- Daemon socket startup, shutdown, compatibility checks, and request transport:
  `src/browser_cli/daemon/client.py`, `src/browser_cli/daemon/transport.py`
- Daemon action dispatch and per-command handlers:
  `src/browser_cli/daemon/app.py`
- Shared daemon state:
  `src/browser_cli/daemon/state.py`
- Browser lifecycle, driver selection, safe-point rebinding, read-page flow, and ref-aware command routing:
  `src/browser_cli/daemon/browser_service.py`

- Driver contract:
  `src/browser_cli/drivers/base.py`
- Playwright adapter layer:
  `src/browser_cli/drivers/playwright_driver.py`
- Extension adapter layer:
  `src/browser_cli/drivers/extension_driver.py`
- Extension-driver action mixins:
  `src/browser_cli/drivers/_extension/*.py`

- Low-level Playwright browser primitives, page state, screenshots, PDF, eval, input, storage, tracing, and video:
  `src/browser_cli/browser/service.py`, `src/browser_cli/browser/session.py`
- Snapshot capture helpers:
  `src/browser_cli/browser/snapshot.py`
- Network capture models/buffering:
  `src/browser_cli/network.py`, `src/browser_cli/browser/network_capture.py`
- Stealth and browser launch behavior:
  `src/browser_cli/browser/stealth.py`

- Semantic ref generation:
  `src/browser_cli/refs/generator.py`
- Semantic ref reconstruction into Playwright locators:
  `src/browser_cli/refs/resolver.py`
- Latest snapshot storage per page:
  `src/browser_cli/refs/registry.py`
- Ref models shared across daemon and drivers:
  `src/browser_cli/refs/models.py`

- Agent-scoped tab ownership, active-tab tracking, and busy-state conflict logic:
  `src/browser_cli/tabs/registry.py`
- `X_AGENT_ID` resolution:
  `src/browser_cli/agent_scope/__init__.py`

- Managed Chrome discovery, profile directory resolution, and lock detection:
  `src/browser_cli/profiles/discovery.py`
- Runtime home, socket paths, artifact paths, and extension socket config:
  `src/browser_cli/constants.py`

- Extension session lifecycle, handshake, heartbeat, and artifact chunk assembly:
  `src/browser_cli/extension/session.py`
- Extension protocol models and required capabilities:
  `src/browser_cli/extension/protocol.py`
- Browser extension entrypoints:
  `browser-cli-extension/src/background.js`, `browser-cli-extension/src/protocol.js`, `browser-cli-extension/src/page_runtime.js`
- Extension popup runtime observer UI and pure view model:
  `browser-cli-extension/popup.html`, `browser-cli-extension/src/popup.js`, `browser-cli-extension/src/popup_view.js`
- Extension background feature implementations:
  `browser-cli-extension/src/background/*.js`

- Task runtime client used by `task.py`:
  `src/browser_cli/task_runtime/client.py`
- High-level Flow helpers used by tasks:
  `src/browser_cli/task_runtime/flow.py`
- Task metadata schemas and validation:
  `src/browser_cli/task_runtime/models.py`
- Workflow manifest loading and validation:
  `src/browser_cli/workflow/loader.py`
- Workflow execution and hook orchestration:
  `src/browser_cli/workflow/runner.py`, `src/browser_cli/workflow/hooks.py`

- User-facing output rendering:
  `src/browser_cli/outputs/render.py`, `src/browser_cli/outputs/json.py`
- Error taxonomy and exit codes:
  `src/browser_cli/errors.py`, `src/browser_cli/error_codes.py`, `src/browser_cli/exit_codes.py`

- Guard scripts that enforce product contracts and package boundaries:
  `scripts/guards/*.py`
- Example tasks and packaged workflows:
  `tasks/*`
- Browser-CLI-specific agent workflow guidance:
  `skills/browser-cli-explore-delivery/SKILL.md`
- Tests for behavior and contracts:
  `tests/unit/*`, `tests/integration/*`

## Common Navigation Paths

- If the user wants a new daemon-backed CLI command:
  update `src/browser_cli/actions/cli_specs.py`, then add the daemon handler in `src/browser_cli/daemon/app.py`, then implement the browser behavior in `src/browser_cli/daemon/browser_service.py` and the relevant driver(s).
- If the user wants to change `read` behavior:
  inspect `src/browser_cli/commands/read.py` and `src/browser_cli/runtime/read_runner.py` first, then `src/browser_cli/daemon/browser_service.py::read_page`.
- If the user reports daemon startup, stale socket, or reload issues:
  inspect `src/browser_cli/daemon/client.py`, `src/browser_cli/daemon/transport.py`, `src/browser_cli/commands/status.py`, and `src/browser_cli/commands/reload.py`.
  If startup fails while waiting for an extension session, inspect `src/browser_cli/daemon/browser_service.py::ensure_started`; extension handshake wait is a best-effort preference signal and must fall back to Playwright instead of aborting daemon startup.
- If the user reports a driver mismatch or extension/Playwright inconsistency:
  start at `src/browser_cli/drivers/base.py`, then compare `playwright_driver.py`, `extension_driver.py`, and `daemon/browser_service.py`.
- If the user reports broken refs, stale snapshots, or element targeting failures:
  start at `src/browser_cli/refs/registry.py`, `src/browser_cli/refs/generator.py`, `src/browser_cli/refs/resolver.py`, and the snapshot-related methods in `src/browser_cli/daemon/browser_service.py`.
- If the user reports busy-tab or tab-visibility conflicts:
  start at `src/browser_cli/tabs/registry.py` and the tab-related handlers in `src/browser_cli/daemon/app.py`.
- If the user wants task/workflow behavior changed:
  inspect `src/browser_cli/task_runtime/*` and `src/browser_cli/workflow/*`, then validate against example tasks under `tasks/`.
- If the user reports recurring-run, workflow history, local Web UI, or workflow-service state issues:
  start at `src/browser_cli/workflow/service/*`, `src/browser_cli/workflow/persistence/*`, `src/browser_cli/workflow/scheduler/*`, and `src/browser_cli/workflow/api/*`.
- If the user mentions extension capability gaps, artifacts, or real Chrome behavior:
  inspect both `src/browser_cli/extension/*` and `browser-cli-extension/src/*`; many bugs live in protocol drift between Python and extension JS.
- If the user reports popup/runtime observer drift:
  start at `src/browser_cli/daemon/runtime_presentation.py`, then `src/browser_cli/extension/session.py`, then `browser-cli-extension/src/background.js`, `browser-cli-extension/src/popup_view.js`, and `browser-cli-extension/src/popup.js`.
- If a change touches architecture or public product contracts:
  inspect `scripts/guards/architecture.py`, `scripts/guards/product_contracts.py`, and `scripts/guards/docs_sync.py` before making the change final.

## Architectural Boundaries

- `browser_cli.actions` owns daemon-backed CLI action metadata. Add or rename public action commands here before touching parser glue elsewhere.
- `browser_cli.agent_scope` owns `X_AGENT_ID` resolution and defaults.
- `browser_cli.browser` owns low-level Playwright browser primitives, launch behavior, snapshot input capture, storage, trace/video plumbing, and network capture helpers.
- `browser_cli.cli` parses top-level commands and owns help text and exit code behavior.
- `browser_cli.commands` owns user-facing command handlers for `read`, `status`, `reload`, workflow subcommands, and the generic action runner.
- `browser_cli.daemon` owns the long-lived daemon, socket transport, request/response protocol, browser lifecycle, runtime status, and command dispatch.
- `browser_cli.drivers` owns the explicit backend contract plus `playwright_driver` and `extension_driver`. Drivers consume daemon-built locator specs, not raw refs.
- `browser_cli.extension` owns the extension transport, handshake, heartbeat, required-capability checks, and artifact assembly from WebSocket chunks.
- `browser_cli.daemon.runtime_presentation` owns the shared runtime classification used by `browser-cli status` and the extension popup.
- `browser_cli.outputs` owns final rendering for content-first and JSON-first surfaces.
- `browser_cli.profiles` owns Chrome executable discovery, managed profile directories, profile naming, and lock detection.
- `browser_cli.refs` owns semantic ref models, snapshot generation, latest-snapshot registry state, and locator reconstruction.
- `browser_cli.runtime` owns the one-shot read orchestration layer. `browser_cli.runtime.read_runner` owns the one-shot read contract and routes it through the daemon-managed browser lifecycle.
- `browser_cli.tabs` owns agent-visible tab state, active-tab tracking, and busy-state conflict rules.
- `browser_cli.task_runtime` owns the thin Python runtime used by `task.py`.
- `browser_cli.workflow` owns workflow manifest loading, import/export, persistent workflow-service state, scheduler logic, local API/Web UI, hooks, and workflow execution.

Keep these boundaries intact. Do not push browser internals into CLI handlers, do not move semantic-ref logic into drivers, and do not bypass the daemon for public interactive commands.

## Implementation Conventions

- Top-level parser registration lives in `src/browser_cli/cli/main.py`. Only `read`, `workflow`, `status`, and lifecycle `reload` are hand-wired there; the rest come from `get_action_specs()`.
- `browser-cli workflow` now contains both one-shot manifest helpers (`run`, `validate`) and workflow-service helpers (`ui`, `service-status`, `service-stop`, `import`, `export`). The Web UI remains the primary management surface.
- Public daemon-backed actions should be added through `ActionSpec`, not by manually bolting ad hoc parsers into `main.py`.
- The lifecycle command `browser-cli reload` and the page action `browser-cli page-reload` are intentionally different surfaces. Do not collapse them.
- Public daemon commands return JSON payloads. Preserve `ok/data/meta` shape and machine-readable error codes.
- `runtime-status` is the agent/runtime truth surface; popup code may read and render it, but must not redefine runtime state semantics.
- Tab targeting is agent-scoped. Do not add public `--page`, `--page-id`, session IDs, or similar cross-agent escape hatches.
- Drivers must accept daemon-built `LocatorSpec`, not raw `ref` strings.
- Drivers must expose snapshot input, not final snapshot rendering. Final semantic snapshot generation stays daemon-owned.
- Extension and Playwright backends must stay behaviorally aligned on the same public contract even if their internal mechanics differ.
- Popup daemon status reads and workspace rebuild requests flow through the extension listener HTTP surface in `src/browser_cli/extension/session.py`; keep popup UI logic out of that state interpretation path.
- The extension listener is implemented on the WebSocket listener stack, which only accepts body-less `GET` HTTP requests before upgrade. If popup control endpoints need to mutate runtime state, keep them narrow and route them through dedicated `GET` paths instead of adding a parallel HTTP server.
- Prefer `browser-cli status` before manual daemon cleanup. Prefer `browser-cli reload` over ad hoc process killing when runtime state is bad.
- `task.py` contains reusable automation logic. `workflow.toml` packages and configures that logic; it should not become a second implementation surface.
- Runtime workflow state belongs to the workflow service persistence layer, not `workflow.toml`. `workflow.toml` remains import/export and reviewable packaging.
- When adapting third-party logic from `third_party/bridgic-browser`, keep provenance clear and the adapted code understandable. Do not add a runtime dependency on the external package just to shortcut implementation.

## Testing And Validation

- Unit tests live under `tests/unit/`; integration coverage lives under `tests/integration/`.
- Contract-sensitive areas include CLI parser shape, action catalog parity, daemon lifecycle, semantic refs, driver parity, workflow validation, and `X_AGENT_ID` tab isolation.
- The repository target is Python 3.10+. Keep runtime code and tests on Python 3.10-compatible syntax and stdlib APIs; local 3.12-only constructs can pass ad hoc checks and still fail CI collection, lint, or guards.
- `scripts/guards/python_compatibility.py` owns the static Python 3.10 compatibility check; keep new syntax and stdlib-API regression rules there so local 3.12 development fails before CI does.
- Tests and workflow fixtures must resolve repo assets relative to the checked-out repository, not a developer-specific absolute workspace path; CI runners will fail on hard-coded local paths first in workflow/task fixture coverage.
- `scripts/lint.sh` owns repository lint execution.
- `scripts/guard.sh` owns architecture, product-contract, and doc-sync guards.
- `scripts/check.sh` runs both lint and guard in the expected order.
- The guard implementations live under `scripts/guards/`.
- After each code change, run lint and guard.
- After each code change, run `scripts/lint.sh` and `scripts/guard.sh`, or run `scripts/check.sh`.
- When architecture, package boundaries, or frozen product decisions change, update `AGENTS.md` and the corresponding guard rules in the same change.
- When a new top-level `browser_cli` package, public CLI surface, or major runtime contract is introduced, update both this file and the guard expectations before considering the change complete.

## Updating This File

`AGENTS.md` is part of the implementation surface. Update it when a task changes how an agent should navigate, reason about, or safely modify the repo.

Always update this file when:

- the public CLI surface changes
- a package boundary or ownership rule changes
- daemon/driver/ref/tab/workflow contracts change
- a new recurring debugging path becomes obvious
- a previously documented rule becomes stale

Do not dump changelog noise here. Keep only durable, reusable knowledge that should help the next agent move faster.

## Failure-Driven Knowledge Capture

Agents should learn from failures and write back only the parts that will matter again.

- If a task uncovers a recurring failure mode, add the lesson next to the owning subsystem above instead of writing a generic journal entry.
- Record stable knowledge, not transient machine state. Good additions include invariants, protocol mismatches, common root causes, and the safest inspection path.
- Use the smallest durable form possible:
  `symptom -> root cause -> where to inspect -> safe fix`
- Prefer code-anchored statements over anecdotes. A future agent should be able to jump from the note to the owning file immediately.
- If the failure was caused by stale documentation, replace the stale rule instead of appending a contradictory note.
- If the lesson is only useful for the current branch, log, or local environment, do not add it here.
- When a bug fix changes behavior, add the reusable takeaway in the same change so the next task benefits immediately.
