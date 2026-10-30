import {ExtensionRuntimeError, queryRuntimeTabs} from '../runtime_health.js';

const STORAGE_KEY = 'browserCliWorkspaceBinding';
const STORAGE_VERSION = 1;

async function liveTargetIds() {
  let timeoutId;
  try {
    if (typeof chrome.debugger?.getTargets !== 'function') {
      throw new Error('debugger.getTargets is unavailable');
    }
    const targets = await Promise.race([
      chrome.debugger.getTargets(),
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error('debugger.getTargets timed out')), 1500);
      }),
    ]);
    if (!Array.isArray(targets)) throw new Error('debugger.getTargets returned an invalid result');
    return new Map(targets.filter(target => target.type === 'page'
      && Number.isInteger(target.tabId) && typeof target.id === 'string')
      .map(target => [target.tabId, target.id]));
  } catch (error) {
    throw new ExtensionRuntimeError(String(error?.message || error));
  } finally {
    clearTimeout(timeoutId);
  }
}

// Local storage survives extension reloads; a Chrome target ID prevents recycled
// numeric tab/window IDs from granting ownership of an unrelated browser page.
export function createWorkspaceBinding(state) {
  let restored = false;
  let restoring;
  let writing = Promise.resolve();

  function enqueueWrite(operation) {
    writing = writing.catch(() => {}).then(operation);
    return writing;
  }

  function save() {
    const windowId = state.workspaceWindowId;
    const tabs = [...state.managedTabIds].map(tabId => ({
      tab_id: tabId,
      page_id: state.pageIdByTabId.get(tabId) || null,
    }));
    // Capture state now and serialize writes, including removal events. A late
    // write from an older mutation must never resurrect a closed binding.
    return enqueueWrite(async () => {
      let binding = null;
      if (windowId !== null) {
        const targets = await liveTargetIds();
        binding = {
          version: STORAGE_VERSION,
          window_id: windowId,
          tabs: tabs.filter(tab => targets.has(tab.tab_id))
            .map(tab => ({...tab, target_id: targets.get(tab.tab_id)})),
        };
      }
      await chrome.storage.local.set({[STORAGE_KEY]: binding});
    });
  }

  async function restoreSavedBinding() {
    const stored = await chrome.storage.local.get(STORAGE_KEY);
    const binding = stored[STORAGE_KEY];
    if (!binding || binding.version !== STORAGE_VERSION
      || !Number.isInteger(binding.window_id) || binding.window_id < 0
      || !Array.isArray(binding.tabs)) return;

    let tabs;
    try {
      tabs = await queryRuntimeTabs({windowId: binding.window_id});
    } catch (error) {
      if (!/No window with id/i.test(String(error?.message))) throw error;
      await enqueueWrite(() => chrome.storage.local.set({[STORAGE_KEY]: null}));
      return;
    }
    const targets = await liveTargetIds();
    const liveTabs = new Set(tabs.map(tab => tab.id));
    const owned = binding.tabs.filter(tab => tab && Number.isInteger(tab.tab_id)
      && liveTabs.has(tab.tab_id) && typeof tab.target_id === 'string'
      && targets.get(tab.tab_id) === tab.target_id);
    const pruned = owned.length ? {
      version: STORAGE_VERSION,
      window_id: binding.window_id,
      tabs: owned.map(tab => ({
        tab_id: tab.tab_id, target_id: tab.target_id,
        page_id: typeof tab.page_id === 'string' ? tab.page_id : null,
      })),
    } : null;
    // Commit the validated snapshot before exposing ownership to requests. An
    // interrupted or failed restore must leave memory and trusted storage intact.
    await enqueueWrite(() => chrome.storage.local.set({[STORAGE_KEY]: pruned}));
    if (owned.length) {
      state.workspaceWindowId = binding.window_id;
      state.managedTabIds = new Set(owned.map(tab => tab.tab_id));
      state.pageIdByTabId = new Map(owned.filter(tab => typeof tab.page_id === 'string' && tab.page_id)
        .map(tab => [tab.tab_id, tab.page_id]));
    }
  }

  return {
    save,
    flush: () => writing,
    restore() {
      if (restored) return Promise.resolve();
      if (!restoring) {
        restoring = restoreSavedBinding().then(() => { restored = true; })
          .finally(() => { restoring = undefined; });
      }
      return restoring;
    },
  };
}
