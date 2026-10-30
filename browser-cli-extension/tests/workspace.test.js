import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspaceHandlers} from '../src/background/workspace.js';

test('workspace status detects unusable Chrome APIs even without a workspace', async (t) => {
  globalThis.chrome = {tabs: undefined};
  t.after(() => { delete globalThis.chrome; });
  const handlers = createWorkspaceHandlers({state: {
    workspaceWindowId: null, managedTabIds: new Set(), pageIdByTabId: new Map(),
  }});
  await assert.rejects(handlers['workspace-status'](), (error) => {
    assert.equal(error.code, 'EXTENSION_RUNTIME_UNHEALTHY');
    assert.match(error.message, /tabs.query/);
    return true;
  });
});
