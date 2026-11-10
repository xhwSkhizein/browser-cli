# Playwright keyboard data

`browser-cli-extension/src/key_definitions.js` contains the USKeyboardLayout and macEditingCommands data exported from the uv.lock-pinned Playwright 1.58.0 package (`lib/server/usKeyboardLayout.js` and `lib/server/macEditingCommands.js`). The tables are unchanged; CommonJS wrappers are replaced by ESM exports. Source: https://github.com/microsoft/playwright/tree/v1.58.0/packages/playwright-core/src/server. Licensed under Apache-2.0; LICENSE and NOTICE are retained here.

This is browser-extension data, with no Node or Playwright runtime in the extension. Refresh these two exports from the pinned package when keyboard parity needs updating.
