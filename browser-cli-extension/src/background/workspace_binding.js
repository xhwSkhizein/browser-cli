import {ExtensionRuntimeError, queryRuntimeTabs} from '../runtime_health.js';

const STORAGE_KEY = 'browserCliWorkspaceBinding';
const STORAGE_VERSION = 2;

/** Resolve live debugger identities so recycled numeric tab IDs gain no ownership. */
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
/** Persist and restore verified tab ownership across shared browser windows. */
export function createWorkspaceBinding(state) {
  let restored = false;
  let restoring;
  let writing = Promise.resolve();

  /** Serialize mutations so a delayed write cannot resurrect removed ownership. */
  function enqueueWrite(operation) {
    writing = writing.catch(() => {}).then(operation);
    return writing;
  }

  /** Snapshot current ownership now, then persist it with live target identities. */
  function save() {
    const windowId = state.workspaceWindowId;
    const groupId = state.workspaceGroupId ?? null;
    const bootstrapTabId = state.bootstrapTabId ?? null;
    const tabs = [...state.managedTabIds].map(tabId => ({
      tab_id: tabId,
      page_id: state.pageIdByTabId.get(tabId) || null,
    }));
    // Capture state now and serialize writes, including removal events. A late
    // write from an older mutation must never resurrect a closed binding.
    return enqueueWrite(async () => {
      let binding = null;
      if (tabs.length) {
        const targets = await liveTargetIds();
        const liveTabs = new Map((await queryRuntimeTabs()).map(tab => [tab.id, tab]));
        binding = {
          version: STORAGE_VERSION,
          window_id: windowId,
          group_id: groupId,
          bootstrap_tab_id: bootstrapTabId,
          tabs: tabs.filter(tab => targets.has(tab.tab_id) && liveTabs.has(tab.tab_id))
            .map(tab => ({...tab, target_id: targets.get(tab.tab_id),
              window_id: liveTabs.get(tab.tab_id).windowId})),
        };
        if (!binding.tabs.length) binding = null;
      }
      await chrome.storage.local.set({[STORAGE_KEY]: binding});
    });
  }

  /** Validate window membership and target identity before exposing saved ownership. */
  async function restoreSavedBinding() {
    const stored = await chrome.storage.local.get(STORAGE_KEY);
    const binding = stored[STORAGE_KEY];
    if (!binding || ![1, STORAGE_VERSION].includes(binding.version)
      || (binding.version === 1 && (!Number.isInteger(binding.window_id) || binding.window_id < 0))
      || !Array.isArray(binding.tabs)) return;

    let tabs;
    try {
      tabs = await queryRuntimeTabs(binding.version === 1 ? {windowId: binding.window_id} : undefined);
    } catch (error) {
      if (!/No window with id/i.test(String(error?.message))) throw error;
      await enqueueWrite(() => chrome.storage.local.set({[STORAGE_KEY]: null}));
      return;
    }
    const targets = await liveTargetIds();
    const liveTabs = new Map(tabs.map(tab => [tab.id, tab]));
    const owned = binding.tabs.filter(tab => tab && Number.isInteger(tab.tab_id)
      && liveTabs.has(tab.tab_id)
      && liveTabs.get(tab.tab_id).windowId === (binding.version === 1 ? binding.window_id : tab.window_id)
      && typeof tab.target_id === 'string'
      && targets.get(tab.tab_id) === tab.target_id);
    const windowId = owned.some(tab => liveTabs.get(tab.tab_id).windowId === binding.window_id)
      ? binding.window_id : owned.length ? liveTabs.get(owned[0].tab_id).windowId : null;
    const pruned = owned.length ? {
      version: STORAGE_VERSION,
      window_id: windowId,
      group_id: Number.isInteger(binding.group_id) ? binding.group_id : null,
      bootstrap_tab_id: owned.some(tab => tab.tab_id === binding.bootstrap_tab_id)
        ? binding.bootstrap_tab_id : null,
      tabs: owned.map(tab => ({
        tab_id: tab.tab_id, target_id: tab.target_id,
        window_id: liveTabs.get(tab.tab_id).windowId,
        page_id: typeof tab.page_id === 'string' ? tab.page_id : null,
      })),
    } : null;
    // Commit the validated snapshot before exposing ownership to requests. An
    // interrupted or failed restore must leave memory and trusted storage intact.
    await enqueueWrite(() => chrome.storage.local.set({[STORAGE_KEY]: pruned}));
    if (owned.length) {
      state.workspaceWindowId = windowId;
      state.workspaceGroupId = pruned.group_id;
      state.bootstrapTabId = pruned.bootstrap_tab_id;
      state.managedTabIds = new Set(owned.map(tab => tab.tab_id));
      state.pageIdByTabId = new Map(owned.filter(tab => typeof tab.page_id === 'string' && tab.page_id)
        .map(tab => [tab.tab_id, tab.page_id]));
    }
  }

  return {
    save,
    flush: () => writing,
    /** Share one restore attempt and allow retry after a transient API failure. */
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
