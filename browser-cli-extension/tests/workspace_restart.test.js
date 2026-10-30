import test from 'node:test';
import assert from 'node:assert/strict';

let workerSequence = 0;

function installBrowser(t) {
  const stored = {};
  const windows = new Map();
  const tabs = new Map();
  const targets = new Map();
  const sockets = [];
  let nextWindow = 10;
  let nextTab = 100;
  let nextTarget = 1;
  let createdWindows = 0;
  let listeners;
  const noop = () => {};
  const clone = value => JSON.parse(JSON.stringify(value));
  const addTab = (windowId, url = 'about:blank') => {
    const tab = {id: nextTab++, windowId, url, title: '', active: true, status: 'complete'};
    tabs.set(tab.id, tab);
    targets.set(tab.id, `target-${nextTarget++}`);
    return tab;
  };
  const event = name => ({addListener(fn) { (listeners[name] ||= []).push(fn); }});

  const originalTimeout = globalThis.setTimeout;
  t.mock.method(globalThis, 'setTimeout', (fn, delay, ...args) => delay === 100
    ? 0 : originalTimeout(fn, delay, ...args));
  t.mock.method(globalThis, 'fetch', async () => ({status: 426, ok: false}));
  t.mock.method(globalThis, 'setInterval', () => 1);
  t.mock.method(globalThis, 'clearInterval', noop);
  globalThis.WebSocket = class {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 1;
    sent = [];
    constructor() { sockets.push(this); }
    send(data) { this.sent.push(JSON.parse(data)); }
    close() { this.readyState = 3; this.onclose?.(); }
  };
  t.after(() => { delete globalThis.chrome; delete globalThis.WebSocket; });

  async function boot({targetsError} = {}) {
    for (const socket of sockets) socket.readyState = 3;
    listeners = {};
    globalThis.chrome = {
      runtime: {
        id: 'workspace-restart-test',
        onInstalled: event('installed'), onStartup: event('startup'), onMessage: event('message'),
        getPlatformInfo: async () => ({os: 'mac'}), getManifest: () => ({version: 'test'}),
        reload: noop,
      },
      storage: {local: {
        get: async () => clone(stored),
        set: async values => Object.assign(stored, clone(values)),
      }},
      alarms: {create: noop, onAlarm: event('alarm')},
      tabs: {
        onRemoved: event('tabRemoved'),
        query: async ({windowId} = {}) => {
          if (windowId !== undefined && !windows.has(windowId)) {
            throw new Error(`No window with id: ${windowId}`);
          }
          return [...tabs.values()].filter(tab => windowId === undefined || tab.windowId === windowId);
        },
        get: async id => {
          if (!tabs.has(id)) throw new Error(`No tab with id: ${id}`);
          return tabs.get(id);
        },
        create: async ({windowId, url}) => addTab(windowId, url),
        update: async (id, values) => Object.assign(tabs.get(id), values),
        remove: async id => {
          tabs.delete(id);
          targets.delete(id);
          for (const fn of listeners.tabRemoved || []) await fn(id);
        },
      },
      windows: {
        onRemoved: event('windowRemoved'),
        get: async id => {
          if (!windows.has(id)) throw new Error(`No window with id: ${id}`);
          return {id};
        },
        create: async ({url}) => {
          const id = nextWindow++;
          windows.set(id, {id});
          createdWindows++;
          return {id, tabs: [addTab(id, url)]};
        },
        remove: async id => {
          for (const tab of [...tabs.values()]) {
            if (tab.windowId === id) await chrome.tabs.remove(tab.id);
          }
          windows.delete(id);
          for (const fn of listeners.windowRemoved || []) await fn(id);
        },
      },
      scripting: {executeScript: noop},
      debugger: {
        attach: async () => {}, sendCommand: async () => ({}),
        getTargets: async () => {
          if (targetsError) throw targetsError;
          return [...targets].map(([tabId, id]) => ({tabId, id, type: 'page'}));
        },
        onEvent: event('debuggerEvent'), onDetach: event('debuggerDetach'),
      },
    };
    const previousSockets = sockets.length;
    await import(`../src/background.js?workspace-worker=${++workerSequence}`);
    await new Promise(resolve => setImmediate(resolve));
    if (sockets.length === previousSockets) return null;
    const socket = sockets.at(-1);
    await socket.onopen();
    return {
      hello: socket.sent.find(message => message.type === 'hello'),
      async request(action, payload = {}) {
        const id = `request-${socket.sent.length}`;
        await socket.onmessage({data: JSON.stringify({type: 'request', id, action, payload})});
        const response = socket.sent.find(message => message.id === id);
        assert.equal(response?.ok, true, JSON.stringify(response));
        return response.data;
      },
    };
  }

  return {boot, stored, windows, tabs, targets, addTab, get createdWindows() { return createdWindows; }};
}

test('a fresh worker restores the original workspace and page IDs before its handshake', async t => {
  const browser = installBrowser(t);
  const first = await browser.boot();
  const opened = await first.request('open-tab', {url: 'https://example.test/', page_id: 'page_42'});
  const before = await first.request('workspace-status');
  const restarted = await browser.boot();
  const after = await restarted.request('workspace-status');
  assert.equal(after.binding_state, 'tracked');
  assert.equal(after.window_id, before.window_id);
  assert.equal(restarted.hello.workspace_window_state.window_id, before.window_id);
  assert.equal(restarted.hello.workspace_window_state.binding_state, 'tracked');
  assert.equal(browser.createdWindows, 1);
  assert.deepEqual((await restarted.request('list-tabs')).tabs.map(tab => [tab.tab_id, tab.page_id]),
    [[opened.tab_id, 'page_42']]);
});

test('restoration prunes closed and moved tabs without adopting user-added tabs', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  const first = await worker.request('open-tab', {page_id: 'page_1'});
  const moved = await worker.request('open-tab', {page_id: 'page_2'});
  const closed = await worker.request('open-tab', {page_id: 'page_3'});
  const before = await worker.request('workspace-status');
  browser.tabs.get(moved.tab_id).windowId = 999;
  browser.tabs.delete(closed.tab_id);
  browser.targets.delete(closed.tab_id);
  browser.addTab(before.window_id, 'https://user.example/');

  const restarted = await browser.boot();
  const after = await restarted.request('workspace-status');
  assert.equal(after.binding_state, 'tracked');
  assert.equal(after.tab_count, 2);
  assert.equal(after.managed_tab_count, 1);
  assert.deepEqual((await restarted.request('list-tabs')).tabs.map(tab => tab.tab_id), [first.tab_id]);
  const again = await browser.boot();
  assert.equal((await again.request('list-tabs')).tabs.length, 1);
  assert.equal(browser.createdWindows, 1);
});

test('recycled Chrome tab and window numbers cannot restore ownership of another page', async t => {
  const browser = installBrowser(t);
  const first = await browser.boot();
  const opened = await first.request('open-tab', {page_id: 'page_private'});
  browser.targets.set(opened.tab_id, 'a-different-browser-target');
  const restarted = await browser.boot();
  assert.equal((await restarted.request('workspace-status')).binding_state, 'absent');
  assert.deepEqual((await restarted.request('list-tabs')).tabs, []);
  assert.equal(browser.createdWindows, 1);
});

test('a missing saved window is forgotten without closing or adopting unrelated windows', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  await worker.request('open-tab', {page_id: 'page_missing'});
  const before = await worker.request('workspace-status');
  browser.windows.delete(before.window_id);
  browser.windows.set(777, {id: 777});
  const userTab = browser.addTab(777, 'https://user.example/');
  const restarted = await browser.boot();
  assert.equal((await restarted.request('workspace-status')).binding_state, 'absent');
  assert.deepEqual((await restarted.request('list-tabs')).tabs, []);
  assert.equal(browser.stored.browserCliWorkspaceBinding, null);
  assert.ok(browser.tabs.has(userTab.id));
  assert.ok(browser.windows.has(777));
  assert.equal(browser.createdWindows, 1);
});

test('closing a tab is durable before the action acknowledges success', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  const first = await worker.request('open-tab', {page_id: 'page_kept'});
  const closed = await worker.request('open-tab', {page_id: 'page_closed'});
  await worker.request('close-tab', {tab_id: closed.tab_id});
  const restarted = await browser.boot();
  assert.deepEqual((await restarted.request('list-tabs')).tabs.map(tab => tab.tab_id), [first.tab_id]);
});

test('an explicit workspace close stays closed after a worker restart', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  await worker.request('open-tab', {page_id: 'page_closed'});
  await worker.request('workspace-close');
  const restarted = await browser.boot();
  assert.equal((await restarted.request('workspace-status')).binding_state, 'absent');
  assert.equal(browser.windows.size, 0);
  assert.equal(browser.createdWindows, 1);
});

test('manual rebuild persists only its replacement workspace', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  await worker.request('open-tab', {page_id: 'page_old'});
  const rebuilt = await worker.request('workspace-rebuild-binding');
  const restarted = await browser.boot();
  const restored = await restarted.request('workspace-status');
  assert.equal(restored.window_id, rebuilt.window_id);
  assert.equal(restored.binding_state, 'tracked');
  assert.equal(browser.createdWindows, 2);
  assert.equal(browser.windows.size, 1);
  assert.deepEqual((await restarted.request('list-tabs')).tabs.map(tab => tab.page_id), [null]);
});

test('a transient Chrome API failure preserves the binding for a later successful restart', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  const opened = await worker.request('open-tab', {page_id: 'page_retained'});
  const before = JSON.stringify(browser.stored.browserCliWorkspaceBinding);
  assert.equal(await browser.boot({targetsError: new Error('Extension context invalidated')}), null);
  assert.equal(JSON.stringify(browser.stored.browserCliWorkspaceBinding), before);
  const restarted = await browser.boot();
  assert.deepEqual((await restarted.request('list-tabs')).tabs.map(tab => tab.tab_id), [opened.tab_id]);
});

test('failed persistence during restoration never publishes partial ownership', async t => {
  const browser = installBrowser(t);
  const worker = await browser.boot();
  const opened = await worker.request('open-tab', {page_id: 'page_retained'});
  const state = {workspaceWindowId: null, managedTabIds: new Set(), pageIdByTabId: new Map()};
  const {createWorkspaceBinding} = await import('../src/background/workspace_binding.js');
  const binding = createWorkspaceBinding(state);
  const original = chrome.storage.local.set;
  let fail = true;
  t.mock.method(chrome.storage.local, 'set', async values => {
    if (fail) throw new Error('Storage unavailable');
    await original(values);
  });
  await assert.rejects(binding.restore(), /Storage unavailable/);
  assert.equal(state.workspaceWindowId, null);
  assert.equal(state.managedTabIds.size, 0);
  fail = false;
  browser.targets.set(opened.tab_id, 'a-different-browser-target');
  await binding.restore();
  assert.equal(state.workspaceWindowId, null);
  assert.equal(state.managedTabIds.size, 0);
  assert.equal(browser.stored.browserCliWorkspaceBinding, null);
});

test('serialized storage writes cannot resurrect a workspace cleared during an earlier write', async t => {
  const browser = installBrowser(t);
  await browser.boot();
  const tab = browser.addTab(10);
  const state = {workspaceWindowId: 10, managedTabIds: new Set([tab.id]), pageIdByTabId: new Map()};
  const {createWorkspaceBinding} = await import('../src/background/workspace_binding.js');
  const binding = createWorkspaceBinding(state);
  let release;
  let started = 0;
  const blocked = new Promise(resolve => { release = resolve; });
  const original = chrome.storage.local.set;
  t.mock.method(chrome.storage.local, 'set', async values => {
    started++;
    if (started === 1) await blocked;
    await original(values);
  });
  const earlier = binding.save();
  await new Promise(resolve => setImmediate(resolve));
  state.workspaceWindowId = null;
  state.managedTabIds.clear();
  const later = binding.save();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(started, 1);
  release();
  await Promise.all([earlier, later]);
  assert.equal(browser.stored.browserCliWorkspaceBinding, null);
});
