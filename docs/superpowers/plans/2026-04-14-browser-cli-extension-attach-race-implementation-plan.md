# Browser CLI Extension Attach Race Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent extension-mode `open-tab` from failing with `Tab <id> is not debuggable: unknown` when Chrome has created the tab but has not populated a debuggable URL yet.

**Architecture:** Keep the existing extension-mode workflow and network-capture timing, but harden `ensureAttached()` so it waits briefly for a debuggable URL and retries one transient attach failure before surfacing an error. Cover the behavior with Node-based extension unit tests and keep repository lint wired to run all extension tests.

**Tech Stack:** Browser extension JavaScript, Node `node:test`, repository shell lint/test/guard scripts

---

### Task 1: Harden Extension Attach Timing

**Files:**
- Modify: `browser-cli-extension/src/debugger.js`

- [ ] Add a short polling helper that waits for `chrome.tabs.get(tabId).url` to become `about:blank`, `http(s)`, or `file`.
- [ ] Update `ensureAttached()` to use the helper before `chrome.debugger.attach()`.
- [ ] Retry one transient attach failure after a short delay without changing the public error wording for truly non-debuggable tabs.

### Task 2: Add Regression Tests

**Files:**
- Create: `browser-cli-extension/tests/debugger.test.js`
- Modify: `scripts/lint.sh`

- [ ] Add a Node test that proves `ensureAttached()` waits through an empty tab URL and then attaches once the URL becomes `about:blank`.
- [ ] Add a Node test that proves `ensureAttached()` retries a transient attach failure and succeeds on the second attempt.
- [ ] Add a Node test that proves truly non-debuggable URLs still fail with a clear message.
- [ ] Update lint to run all extension `*.test.js` files, not just the popup test.

### Task 3: Capture Durable Repo Guidance

**Files:**
- Modify: `AGENTS.md`

- [ ] Add a concise failure-driven note pointing future agents to the extension `openTab` and `ensureAttached` path when they see `Tab <id> is not debuggable: unknown`.

### Task 4: Validate

**Files:**
- Modify: none

- [ ] Run `node --test browser-cli-extension/tests/*.test.js`.
- [ ] Run `scripts/lint.sh`.
- [ ] Run `scripts/test.sh`.
- [ ] Run `scripts/guard.sh`.
