import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspaceTabs} from '../src/background/workspace_tabs.js';
import {createWorkspaceHandlers} from '../src/background/workspace.js';
import {registerDebuggerListeners, releaseTabDebugger} from '../src/debugger.js';

let nextId = 1000;
function setup(t, {windows = [{id:1, type:'normal', focused:true}], failLoad = false, failNetwork = false} = {}) {
  const tabs = new Map([[1, {id:1, windowId:1, url:'https://personal.test', groupId:-1, active:true}]]);
  const groups = new Map();
  function removeEmptyGroups() {
    for (const [id] of groups) if (![...tabs.values()].some(tab => tab.groupId === id)) groups.delete(id);
  }
  const calls = [];
  const removedListeners = [];
  const detachedListeners = [];
  let onEvent;
  const state = {
    workspaceWindowId:null, workspaceGroupId:null, bootstrapTabId:null,
    managedTabIds:new Set(), pageIdByTabId:new Map(), traceSessions:new Map(), videoSessions:new Map(),
  };
  const untrackTab = id => {
    state.managedTabIds.delete(id);
    state.pageIdByTabId.delete(id);
    if (state.bootstrapTabId === id) state.bootstrapTabId = null;
  };
  const windowMap = new Map(windows.map(window => [window.id, window]));
  globalThis.chrome = {
    tabs: {
      async query(query) { return [...tabs.values()].filter(tab => Object.entries(query).every(([key, value]) => tab[key] === value)).map(tab => ({...tab})); },
      async get(id) { if (!tabs.has(id)) throw new Error('No tab'); return {...tabs.get(id)}; },
      async create(args) {
        const id = nextId++;
        const tab = {id, ...args, groupId:-1};
        if (args.active !== false) {
          tab.active = true;
          for (const other of tabs.values()) if (other.windowId === args.windowId) other.active = false;
        }
        tabs.set(id, tab); calls.push(['create', id]); return {...tab};
      },
      async update(id, args) {
        if (args.active) for (const tab of tabs.values()) if (tab.windowId === tabs.get(id).windowId) tab.active = false;
        Object.assign(tabs.get(id), args); calls.push(['update', id, args]); return {...tabs.get(id)};
      },
      async remove(id) {
        assert.ok(tabs.has(id)); tabs.delete(id); calls.push(['remove', id]);
        for (const listener of removedListeners) listener(id);
        untrackTab(id);
        removeEmptyGroups();
      },
      async group({tabIds, groupId}) {
        const id = groupId ?? nextId++;
        if (!groups.has(id)) groups.set(id, {id, windowId:tabs.get(tabIds[0]).windowId});
        for (const tabId of tabIds) tabs.get(tabId).groupId = id;
        removeEmptyGroups();
        calls.push(['group', id, tabIds]); return id;
      },
      async ungroup(ids) {
        for (const id of ids) tabs.get(id).groupId = -1;
        removeEmptyGroups(); calls.push(['ungroup', ids]);
      },
      onRemoved: {addListener(fn) {removedListeners.push(fn);}},
    },
    windows: {
      async get(id) { if (!windowMap.has(id)) throw new Error('No window'); return windowMap.get(id); },
      async getAll() { return [...windowMap.values()]; },
      async getLastFocused() { return [...windowMap.values()].find(window => window.focused) || windows[0]; },
      async create(args) {
        const id = nextId++;
        const tab = await chrome.tabs.create({windowId:id, url:args.url});
        const window = {id, type:'normal', tabs:[tab]}; windowMap.set(id, window);
        calls.push(['window-create', id, args]); return window;
      },
      async remove() { throw new Error('Must never close a user window'); },
    },
    tabGroups: {
      async query(query) { return [...groups.values()].filter(group => Object.entries(query).every(([key, value]) => group[key] === value)).map(group => ({...group})); },
      async get(id) { if (!groups.has(id)) throw new Error('No group'); return {...groups.get(id)}; },
      async update(id, args) { Object.assign(groups.get(id), args); return {...groups.get(id)}; },
    },
    debugger: {
      async attach({tabId}) { calls.push(['attach', tabId]); },
      async detach({tabId}) { calls.push(['detach', tabId]); for (const listener of detachedListeners) listener({tabId}); },
      async sendCommand({tabId}, method) {
        calls.push([method, tabId]);
        if (failNetwork && method === 'Network.enable') throw new Error('Network unavailable');
        return {};
      },
      onDetach: {addListener(fn) {detachedListeners.push(fn);}},
      onEvent: {addListener(fn) {onEvent = fn;}},
    },
  };
  registerDebuggerListeners();
  const manager = createWorkspaceTabs({state, untrackTab, async waitForLoad(id) {
    calls.push(['load', id]); if (failLoad) throw new Error('Navigation failed');
  }});
  const context = {...manager, state, untrackTab, pageIdForTab:id => state.pageIdByTabId.get(id),
    async getManagedTab(id) { assert.ok(state.managedTabIds.has(id)); return chrome.tabs.get(id); }};
  const handlers = createWorkspaceHandlers(context);
  t.after(async () => {
    for (const id of state.managedTabIds) await releaseTabDebugger(id);
    delete globalThis.chrome;
  });
  return {manager, handlers, state, tabs, groups, windowMap, calls, event:(...args) => onEvent(...args)};
}

test('uses an existing window and a native group without adopting personal tabs', async t => {
  const {manager, tabs, groups, calls} = setup(t);
  const first = await manager.openTab('https://agent.test');
  const second = await manager.openTab('https://agent.test/two');
  assert.equal(first.windowId, 1);
  assert.equal(first.groupId, second.groupId);
  assert.equal(groups.size, 1);
  assert.equal(groups.get(first.groupId).title, 'Browser CLI');
  assert.equal(groups.get(first.groupId).color, 'green');
  assert.equal(tabs.get(1).groupId, -1);
  assert.equal(tabs.get(1).active, true);
  assert.equal(first.active, false);
  assert.equal(second.active, false);
  assert.equal(calls.some(([action]) => action === 'window-create'), false);
  assert.ok(calls.findIndex(([action]) => action === 'Network.enable') < calls.findIndex(([action, , args]) => action === 'update' && args.url));
  assert.deepEqual(await manager.getWorkspaceWindowState(), {window_id:1, tab_count:2, managed_tab_count:2, binding_state:'tracked'});
  await manager.closeWorkspaceTabs();
  assert.deepEqual([...tabs.keys()], [1]);
});

test('one-shot reads and rebuild placeholders never attach debugger', async t => {
  const {manager, handlers, state, calls} = setup(t);
  const tab = await manager.openTab('https://read.test', {observeNetwork:false});
  await manager.closeWorkspaceTabs();
  await handlers['workspace-rebuild-binding']({}, {requestId:'rebuild'});
  const placeholder = state.bootstrapTabId;
  const opened = await handlers['open-tab']({url:'https://read.test/next', observe_network:false, page_id:'read'});
  assert.equal(opened.tab_id, placeholder);
  assert.notEqual(opened.tab_id, tab.id);
  assert.equal(state.bootstrapTabId, null);
  assert.equal(calls.some(([action]) => action === 'attach'), false);
  assert.equal((await chrome.tabs.get(1)).active, true);
});

test('rebuild and close preserve personal tabs even if moved into the agent group', async t => {
  const {manager, handlers, tabs, groups} = setup(t);
  const agent = await manager.openTab('https://agent.test');
  tabs.get(1).groupId = agent.groupId;
  await handlers['workspace-rebuild-binding']({}, {requestId:'rebuild'});
  assert.equal(tabs.get(1).url, 'https://personal.test');
  assert.equal(groups.size, 1);
  assert.equal(tabs.get(1).groupId, agent.groupId);
  assert.equal((await manager.managedTabs())[0].groupId, agent.groupId);
  assert.deepEqual((await handlers['list-tabs']()).tabs.map(tab => tab.tab_id), (await manager.managedTabs()).map(tab => tab.id));
  await handlers['workspace-close']({}, {requestId:'close'});
  assert.deepEqual([...tabs.keys()], [1]);
});

test('moved agent tabs remain owned; a moved group is followed for new tabs', async t => {
  const {manager, tabs, groups, state, windowMap} = setup(t);
  const first = await manager.openTab('https://agent.test');
  windowMap.set(2, {id:2, type:'normal'});
  groups.get(first.groupId).windowId = 2;
  tabs.get(first.id).windowId = 2;
  const second = await manager.openTab('https://agent.test/two');
  assert.equal(second.windowId, 2);
  // Moving one tab out of the group doesn't make it disappear from cleanup.
  tabs.get(first.id).groupId = -1;
  tabs.get(first.id).windowId = 1;
  assert.equal((await manager.managedTabs()).length, 2);
  assert.equal(state.managedTabIds.has(first.id), true);
  await manager.closeWorkspaceTabs();
  assert.deepEqual([...tabs.keys()], [1]);
});

test('creates a fallback window only when no normal non-incognito window exists', async t => {
  const {manager, calls, tabs} = setup(t, {windows:[{id:9, type:'normal', incognito:true}]});
  const tab = await manager.openTab('https://agent.test', {observeNetwork:false});
  assert.notEqual(tab.windowId, 9);
  assert.equal(calls.filter(([action]) => action === 'window-create').length, 1);
  assert.equal(calls.find(([action]) => action === 'window-create')[2].focused, false);
  assert.equal(calls.filter(([action]) => action === 'create').length, 1);
  assert.equal(tabs.has(1), true);
});

test('failed navigation and failed network setup remove the owned debugging tab', async t => {
  for (const failure of [{failLoad:true}, {failNetwork:true}]) {
    await t.test(JSON.stringify(failure), async t => {
      const {manager, state, tabs, calls} = setup(t, failure);
      await assert.rejects(manager.openTab('https://broken.test'), /Navigation failed|Network unavailable/);
      assert.deepEqual([...tabs.keys()], [1]);
      assert.equal(state.managedTabIds.size, 0);
      assert.equal(calls.filter(([action]) => action === 'remove').length, 1);
      assert.equal(calls.filter(([action]) => action === 'ungroup').length, 1);
    });
  }
});

test('concurrent opens create one group and keep their ownership separate', async t => {
  const {manager, state, groups} = setup(t);
  const tabs = await Promise.all([manager.openTab('https://one.test'), manager.openTab('https://two.test')]);
  assert.equal(groups.size, 1);
  assert.equal(state.managedTabIds.size, 2);
  assert.notEqual(tabs[0].id, tabs[1].id);
});

test('adding a background tab preserves the user-collapsed group and active page', async t => {
  const {manager, groups, tabs} = setup(t);
  const first = await manager.openTab('https://agent.test');
  groups.get(first.groupId).collapsed = true;
  const next = await manager.openTab('https://agent.test/two');
  assert.equal(groups.get(first.groupId).collapsed, true);
  assert.equal(next.groupId, first.groupId);
  assert.equal(tabs.get(1).active, true);
});

test('worker reload reuses the surviving workspace group without adopting its tabs', async t => {
  const {manager, state, groups, tabs} = setup(t);
  const first = await manager.openTab('https://agent.test', {observeNetwork:false});
  // Chrome keeps the native groups when the extension loses its in-memory state.
  state.workspaceWindowId = null;
  state.workspaceGroupId = null;
  state.bootstrapTabId = null;
  state.managedTabIds.clear();
  state.pageIdByTabId.clear();
  const restored = await manager.openTab('https://agent.test/after-reload', {observeNetwork:false});
  assert.equal(groups.size, 1);
  assert.equal(restored.groupId, first.groupId);
  assert.equal(tabs.get(1).active, true);
  assert.deepEqual([...state.managedTabIds], [restored.id]);
});

test('legacy duplicate groups merge their pages without granting agent ownership', async t => {
  const {manager, state, groups, tabs} = setup(t);
  for (const id of [20, 30, 40]) {
    groups.set(id, {id, windowId:1, title:'Browser CLI', color:'green', collapsed:true});
    tabs.set(id, {id, windowId:1, groupId:id, url:`https://preserve.test/${id}`, active:false});
  }
  groups.set(50, {id:50, windowId:1, title:'Browser CLI notes', color:'green'});
  tabs.set(50, {id:50, windowId:1, groupId:50, url:'https://notes.test'});
  const opened = await manager.openTab('https://agent.test', {observeNetwork:false});
  assert.equal(groups.size, 2);
  assert.equal(groups.get(opened.groupId).collapsed, true);
  for (const id of [20, 30, 40]) {
    assert.equal(tabs.get(id).url, `https://preserve.test/${id}`);
    assert.equal(tabs.get(id).groupId, opened.groupId);
    assert.equal(state.managedTabIds.has(id), false);
  }
  assert.equal(tabs.get(50).groupId, 50);
  await manager.closeWorkspaceTabs();
  assert.deepEqual([...tabs.keys()], [1, 20, 30, 40, 50]);
});

test('an existing workspace group is reused even when another window is focused', async t => {
  const {manager, groups, tabs, windowMap, calls} = setup(t);
  windowMap.set(2, {id:2, type:'normal'});
  groups.set(20, {id:20, windowId:2, title:'Browser CLI', color:'green'});
  tabs.set(20, {id:20, windowId:2, groupId:20, url:'https://preserve.test'});
  const opened = await manager.openTab('https://agent.test', {observeNetwork:false});
  assert.equal(opened.windowId, 2);
  assert.equal(opened.groupId, 20);
  assert.equal(groups.size, 1);
  assert.equal(calls.some(([name]) => name === 'window-create'), false);
  assert.equal(tabs.get(1).active, true);
});

test('recovery leaves shared groups and pages in other windows in place', async t => {
  const {manager, groups, tabs, windowMap, state} = setup(t);
  windowMap.set(2, {id:2, type:'normal'});
  for (const [id, windowId, shared] of [[20, 1, true], [30, 1, false], [40, 2, false]]) {
    groups.set(id, {id, windowId, shared, title:'Browser CLI', color:'green'});
    tabs.set(id, {id, windowId, groupId:id, url:`https://preserve.test/${id}`});
  }
  const opened = await manager.openTab('https://agent.test', {observeNetwork:false});
  assert.equal(opened.groupId, 30);
  assert.equal(groups.size, 3);
  assert.equal(tabs.get(20).groupId, 20);
  assert.equal(tabs.get(40).windowId, 2);
  assert.equal(tabs.get(40).groupId, 40);
  assert.deepEqual([...state.managedTabIds], [opened.id]);
});

test('owned tabs leave their group before close, including read and rebuild cleanup', async t => {
  const {manager, handlers, calls, state} = setup(t);
  const opened = await handlers['open-tab']({url:'https://read.test', observe_network:false, page_id:'read'});
  await handlers['close-tab']({tab_id:opened.tab_id}, {requestId:'close'});
  await handlers['workspace-rebuild-binding']({}, {requestId:'rebuild'});
  const placeholder = state.bootstrapTabId;
  await manager.closeWorkspaceTabs();
  for (const id of [opened.tab_id, placeholder]) {
    const ungroup = calls.findIndex(([action, ids]) => action === 'ungroup' && ids.includes(id));
    const remove = calls.findIndex(([action, tabId]) => action === 'remove' && tabId === id);
    assert.ok(ungroup >= 0 && ungroup < remove);
  }
  assert.equal(calls.some(([action]) => action === 'attach'), false);
});

test('bootstrap reuse handles pending blank URL and protects a pending user navigation', async t => {
  const {manager, tabs} = setup(t);
  const blank = await manager.openTab('about:blank', {observeNetwork:false, bootstrap:true});
  Object.assign(tabs.get(blank.id), {url:'', pendingUrl:'about:blank'});
  const reused = await manager.openTab('https://agent.test', {observeNetwork:false});
  assert.equal(reused.id, blank.id);
  await manager.closeWorkspaceTabs();
  const next = await manager.openTab('about:blank', {observeNetwork:false, bootstrap:true});
  tabs.get(next.id).pendingUrl = 'https://personal-pending.test';
  const fresh = await manager.openTab('https://agent.test', {observeNetwork:false});
  assert.notEqual(fresh.id, next.id);
  assert.equal(tabs.get(next.id).pendingUrl, 'https://personal-pending.test');
});
