import test from 'node:test';
import assert from 'node:assert/strict';

test('startup and install events share a single connection attempt', async (t) => {
  const installed = [];
  const startup = [];
  let releaseConfig;
  const config = new Promise(resolve => { releaseConfig = resolve; });
  const event = {addListener() {}};
  t.mock.method(globalThis, 'fetch', async () => ({status: 426, ok: false}));
  globalThis.chrome = {
    runtime: {onInstalled: {addListener: fn => installed.push(fn)},
      onStartup: {addListener: fn => startup.push(fn)}, onMessage: event},
    storage: {local: {get: () => config}},
    alarms: {create() {}, onAlarm: event},
    tabs: {onRemoved: event}, windows: {onRemoved: event},
    debugger: {onEvent: event, onDetach: event},
  };
  const sockets = [];
  globalThis.WebSocket = class {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 0;
    constructor() { sockets.push(this); }
  };
  t.after(() => { delete globalThis.chrome; delete globalThis.WebSocket; });
  await import(`../src/background.js?connection-test=${Date.now()}`);
  installed[0]();
  startup[0]();
  releaseConfig({});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(sockets.length, 1);
});

test('unusable APIs reject an action before mutation and obsolete sockets cannot respond', async t => {
  const messages = [];
  const sockets = [];
  const intervals = [];
  const clearedIntervals = [];
  let mutations = 0;
  const event = {addListener() {}};
  const noop = () => {};
  const originalTimeout = globalThis.setTimeout;
  t.mock.method(globalThis, 'setTimeout', (fn, delay, ...args) => delay === 100
    ? 0 : originalTimeout(fn, delay, ...args));
  t.mock.method(globalThis, 'setInterval', fn => { intervals.push(fn); return intervals.length; });
  t.mock.method(globalThis, 'clearInterval', id => clearedIntervals.push(id));
  t.mock.method(globalThis, 'fetch', async () => ({status: 426, ok: false}));
  globalThis.chrome = {
    runtime: {onInstalled: event, onStartup: event,
      onMessage: {addListener: fn => messages.push(fn)},
      getPlatformInfo: async () => ({os: 'mac'}), getManifest: () => ({version: 'test'}),
      reload: noop},
    storage: {local: {get: async () => ({}), set: async () => {}}},
    alarms: {create: noop, onAlarm: event},
    tabs: {query: async () => [], get: noop, create: noop, update: noop, remove: noop,
      onRemoved: event},
    windows: {get: noop, create: () => { mutations += 1; }, remove: noop, onRemoved: event},
    scripting: {executeScript: noop},
    debugger: {attach: noop, sendCommand: noop, onEvent: event, onDetach: event},
  };
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
  await import(`../src/background.js?request-test=${Date.now()}`);
  await new Promise(resolve => setImmediate(resolve));
  const old = sockets[0];
  await old.onopen();
  const staleClose = old.onclose;
  chrome.tabs.query = undefined;
  const request = {data: JSON.stringify({type: 'request', id: 'one', action: 'open-tab'})};
  await old.onmessage(request);
  assert.equal(old.sent.at(-1).error_code, 'EXTENSION_RUNTIME_UNHEALTHY');
  assert.equal(mutations, 0);
  chrome.tabs.query = async () => { throw new Error('Extension context invalidated'); };
  await old.onmessage(request);
  assert.equal(old.sent.at(-1).error_code, 'EXTENSION_RUNTIME_UNHEALTHY');
  assert.equal(mutations, 0);
  await new Promise(resolve => messages[0]({type: 'reconnect-now'}, {}, resolve));
  const current = sockets.at(-1);
  assert.notEqual(current, old);
  await current.onopen();
  const currentSent = current.sent.length;
  const clearedCount = clearedIntervals.length;
  await old.onmessage(request);
  staleClose();
  await intervals[0]();
  assert.equal(clearedIntervals.length, clearedCount);
  assert.equal(current.sent.length, currentSent);
  assert.equal(current.readyState, WebSocket.OPEN);
  assert.equal(mutations, 0);
});
