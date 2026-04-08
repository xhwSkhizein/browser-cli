# Provenance

This repository does not depend on the published `bridgic-browser` package at runtime.

Selected implementation ideas and limited adapted source were taken from the local upstream checkout:

- Source repository: `/Users/hongv/workspace/m-projects/bridgic-browser`
- Source commit: `6e60b22e480865616f048891b566049c586a4d52`

Current adapted areas:

- `browser_cli.browser.stealth.STEALTH_INIT_SCRIPT`
  - adapted from `bridgic/browser/session/_stealth.py`
  - purpose: minimal anti-detection init script for `v1`

No daemon transport, CLI catalog, or broad browser tool surface was copied into this repository.

