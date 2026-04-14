---
name: browser-cli-explore-delivery
description: Compatibility wrapper for the newer Browser CLI delivery skill stack.
---

# Browser CLI Explore Delivery

Compatibility wrapper.

Use `browser-cli-delivery` as the main entrypoint for Browser CLI task delivery.

- `browser-cli-explore` owns Browser CLI exploration and feedback capture into
  `task.meta.json`
- `browser-cli-converge` owns convergence into `task.py`
- `browser-cli-delivery` owns stage transitions, validation rollback, optional
  `automation.toml`, and optional publish

Do not extend this wrapper with new primary workflow logic. Put new delivery
guidance in the three new skills.
