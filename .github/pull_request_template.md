## Description

<!-- Briefly describe your changes and link to any related issues. -->

Related issue:

## Type of Change

- [ ] 🐛 Bug fix
- [ ] ✨ New feature
- [ ] 📝 Documentation
- [ ] ♻️ Refactor
- [ ] 🔧 CI / build / tooling
- [ ] 🧪 Test coverage

## Checklist

- [ ] I ran the relevant checks (`ruff`, `mypy`, `pytest`, architecture guard)
- [ ] I updated tests or docs if needed
- [ ] My changes follow the architectural boundaries (see `AGENTS.md`)

## Architectural Boundaries

If your change crosses module boundaries, confirm it aligns with `AGENTS.md`:

- [ ] `browser_cli.actions` owns daemon-backed CLI action metadata
- [ ] `browser_cli.daemon` owns the long-lived daemon and command dispatch
- [ ] `browser_cli.drivers` owns the explicit backend contract
- [ ] `browser_cli.browser` owns low-level Playwright primitives
- [ ] `browser_cli.refs` owns semantic ref models and generation

## Screenshots / Output

<!-- If applicable, paste CLI output or test results here. -->
