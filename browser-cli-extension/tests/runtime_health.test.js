import test from 'node:test';
import assert from 'node:assert/strict';
import {createRuntimeRecovery, queryRuntimeTabs} from '../src/runtime_health.js';

function installChrome(t) {
  const stored = {};
  const calls = {queries: [], reloads: 0};
  const noop = () => {};
  globalThis.chrome = {
    tabs: {get: noop, create: noop, update: noop, remove: noop,
      query: async query => { calls.queries.push(query); return []; }},
    windows: {get: noop, create: noop, remove: noop},
    scripting: {executeScript: noop}, debugger: {attach: noop, sendCommand: noop},
    runtime: {reload: () => { calls.reloads += 1; }},
    storage: {local: {
      get: async () => ({...stored}),
      set: async values => Object.assign(stored, values),
    }},
  };
  t.after(() => { delete globalThis.chrome; });
  return {calls, stored};
}

test('live probe actually calls Chrome and keeps diagnostics read only', async t => {
  const {calls} = installChrome(t);
  assert.deepEqual(await queryRuntimeTabs(), []);
  assert.deepEqual(calls.queries, [{windowType: 'normal'}]);
  assert.equal(calls.reloads, 0);
  chrome.tabs.query = async () => { throw new Error('Extension context invalidated'); };
  await assert.rejects(queryRuntimeTabs(), {code: 'EXTENSION_RUNTIME_UNHEALTHY'});
  assert.equal(calls.reloads, 0);
});

test('a missing owned window is binding loss rather than broken Chrome APIs', async t => {
  installChrome(t);
  chrome.tabs.query = async () => { throw new Error('No window with id: 123'); };
  await assert.rejects(queryRuntimeTabs({windowId: 123}), error => !error.code);
});

test('automatic reload is single flight and rate limited across worker reloads', async t => {
  const {calls} = installChrome(t);
  let timestamp = 1_000_000;
  const timers = [];
  const options = {canReload: () => true, now: () => timestamp,
    schedule: fn => { timers.push(fn); }};
  const first = createRuntimeRecovery(options);
  assert.deepEqual(await Promise.all([first.recover(), first.recover()]), [true, true]);
  assert.equal(timers.length, 1);
  timers.shift()();
  assert.equal(calls.reloads, 1);
  const afterReload = createRuntimeRecovery(options);
  assert.equal(await afterReload.recover(), false);
  timestamp += 5 * 60 * 1000;
  assert.equal(await afterReload.recover(), true);
  timers.shift()();
  assert.equal(calls.reloads, 2);
});

test('automatic recovery cannot reload while a command or recording is active', async t => {
  const {calls} = installChrome(t);
  let idle = false;
  const timers = [];
  const recovery = createRuntimeRecovery({canReload: () => idle,
    now: () => 1_000_000, schedule: fn => timers.push(fn)});
  assert.equal(await recovery.recover(), false);
  idle = true;
  assert.equal(await recovery.recover(), true);
  idle = false;
  timers.shift()();
  assert.equal(calls.reloads, 0);
});

test('storage failure does not cause an unlimited reload loop', async t => {
  const {calls} = installChrome(t);
  chrome.storage.local.set = async () => { throw new Error('Storage unavailable'); };
  const recovery = createRuntimeRecovery({canReload: () => true});
  assert.equal(await recovery.recover(), false);
  assert.equal(calls.reloads, 0);
});
