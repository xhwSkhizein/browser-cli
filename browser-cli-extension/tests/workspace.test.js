import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspaceHandlers} from '../src/background/workspace.js';
import {createWorkspaceTabs} from '../src/background/workspace_tabs.js';

test('workspace status detects unusable Chrome APIs even without a workspace', async (t) => {
  globalThis.chrome = {tabs: undefined};
  t.after(() => { delete globalThis.chrome; });
  const manager = createWorkspaceTabs({workspaceBinding: {async restore() {}}, state: {
    workspaceWindowId: null, managedTabIds: new Set(), pageIdByTabId: new Map(),
  }});
  const handlers = createWorkspaceHandlers(manager);
  await assert.rejects(handlers['workspace-status'](), (error) => {
    assert.equal(error.code, 'EXTENSION_RUNTIME_UNHEALTHY');
    assert.match(error.message, /tabs.query/);
    return true;
  });
});

test('confirmed page closure survives a workspace persistence failure', async t => {
  const live = new Set([5]);
  const state = {managedTabIds: new Set([5]), pageIdByTabId: new Map([[5, 'owned']]),
    videoSessions: new Map(), runtimeState: {}};
  globalThis.chrome = {tabs: {get: async id => ({id}), remove: async id => { live.delete(id); }}};
  t.after(() => { delete globalThis.chrome; });
  const context = {state,
    getManagedTab: async id => ({id, url: 'http://fixture/', title: 'fixture'}),
    pageIdForTab: id => state.pageIdByTabId.get(id),
    untrackTab: async id => {
      state.managedTabIds.delete(id);
      state.pageIdByTabId.delete(id);
      throw new Error('storage persistence failed');
    }};
  const handlers = createWorkspaceHandlers({...context, ...createWorkspaceTabs(context)});
  const result = await handlers['close-tab']({tab_id: 5}, {requestId: 'close-owned'});
  assert.equal(live.has(5), false);
  assert.equal(state.managedTabIds.has(5), false);
  assert.equal(result.page_id, 'owned');
  assert.deepEqual(result.artifacts, []);
  assert.match(state.runtimeState.lastError, /storage persistence failed/);
});

test('failed browser removal remains an error and does not untrack the page', async t => {
  let untracked = false;
  globalThis.chrome = {tabs: {get: async id => ({id}), remove: async () => { throw new Error('browser removal failed'); }}};
  t.after(() => { delete globalThis.chrome; });
  const context = {state: {managedTabIds: new Set([5]), videoSessions: new Map(), runtimeState: {}},
    getManagedTab: async id => ({id}), pageIdForTab: () => 'owned',
    untrackTab: async () => { untracked = true; }};
  const handlers = createWorkspaceHandlers({...context, ...createWorkspaceTabs(context)});
  await assert.rejects(handlers['close-tab']({tab_id: 5}, {requestId: 'close-owned'}),
    /browser removal failed/);
  assert.equal(untracked, false);
});
