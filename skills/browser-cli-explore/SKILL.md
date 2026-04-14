---
name: browser-cli-explore
description: Explore real websites with Browser CLI, validate task mode, and distill durable feedback into task metadata.
---

# Browser CLI Explore

## Overview

Use `browser-cli` to explore a site, test candidate paths, and distill only the
durable findings needed to build a reusable task. The primary output of this
skill is structured knowledge in `task.meta.json`, not final task code.

## When to Use

Use this skill when:

- a web task still needs exploration or validation
- the page depends on real browser state, cookies, login, or rendering
- the next useful artifact is better task metadata, not yet final `task.py`

Do not use this skill when:

- the success path is already validated end to end
- the work is only task-code refactoring with no evidence gap
- the task is pure API work with no Browser CLI dependency

## Hard Rules

- browser-cli is the primary browser execution path
- choose the task mode before broad exploration
- capture only observations that change the next decision
- update `task.meta.json` as a rolling feedback sink
- treat these metadata sections as required destinations for durable knowledge:
  `environment`, `success_path`, `recovery_hints`, `failures`, `knowledge`
- stop once the evidence is strong enough for deterministic implementation
- Do not record raw logs, chat transcripts, or exploratory dead ends in metadata
- Do not turn one lucky run into stable knowledge without a verification step

## Phase Order

1. Confirm the site-specific preflight assumptions:
   login state, cookies, locale, browser profile, writable artifacts, Python env
2. Choose the task mode:
   `ref-driven`, `content-first`, `lazy-scroll`, `login-state-first`, or
   `browser-state/network-assisted`
3. Explore with the smallest reliable Browser CLI signal
4. Capture durable findings into `task.meta.json`
5. Stop when the success path, waits, refs, and failure lessons are clear enough
   for `task.py`

## Metadata Capture Rules

- `environment`: site, entry URL, login requirements, profile assumptions,
  browser assumptions
- `success_path`: validated steps, key refs, assertions, artifacts
- `recovery_hints`: retryable steps, alternate paths, stale-ref strategy, wait
  points, anti-bot recovery
- `failures`: repeatable failure modes and the lesson each one teaches
- `knowledge`: stable selectors/roles, semantic-ref notes, pagination,
  lazy-load, anti-bot, and output interpretation rules

## Done Criteria

This skill is complete when:

- the task mode is known
- the stable path is understood
- the fragile points are documented
- `task.meta.json` contains enough evidence for `browser-cli-converge`

## Common Mistakes

- exploring with direct Playwright instead of Browser CLI
- jumping straight from browsing to `task.py`
- keeping the useful lessons only in chat
- recording logs instead of reusable metadata
