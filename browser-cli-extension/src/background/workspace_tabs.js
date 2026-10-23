import { ensureNetworkSession, releaseTabDebugger } from '../debugger.js';

const GROUP_TITLE = 'Browser CLI';
const GROUP_COLOR = 'green';

// Tab ownership is independent of group membership: users may move their own
// tabs into the group, or move our tabs out of it.
export function createWorkspaceTabs({ state, waitForLoad, untrackTab }) {
  let pendingOpen = Promise.resolve();

  async function managedTabs() {
    const tabs = [];
    for (const tabId of Array.from(state.managedTabIds)) {
      try {
        tabs.push(await chrome.tabs.get(tabId));
      } catch (_error) {
        untrackTab(tabId);
      }
    }
    return tabs;
  }

  async function findWorkspaceGroup() {
    // Native groups outlive an extension reload. Reuse their visual identity,
    // but never infer ownership of their pages from their name or membership.
    const groups = await chrome.tabGroups.query({ title: GROUP_TITLE, color: GROUP_COLOR });
    const candidates = groups.filter(group => group.title === GROUP_TITLE && !group.shared);
    candidates.sort((a, b) => Number(b.windowId === state.workspaceWindowId) - Number(a.windowId === state.workspaceWindowId));
    for (const group of candidates) {
      const window = await chrome.windows.get(group.windowId).catch(() => null);
      if (window?.type === 'normal' && !window.incognito) return group;
    }
    return null;
  }

  async function ensureWorkspaceWindow() {
    if (state.workspaceGroupId !== null) {
      try {
        const group = await chrome.tabGroups.get(state.workspaceGroupId);
        state.workspaceWindowId = group.windowId;
      } catch (_error) {
        state.workspaceGroupId = null;
      }
    }
    if (state.workspaceGroupId === null) {
      const group = await findWorkspaceGroup();
      if (group) {
        state.workspaceGroupId = group.id;
        state.workspaceWindowId = group.windowId;
      }
    }
    if (state.workspaceWindowId !== null) {
      try {
        const window = await chrome.windows.get(state.workspaceWindowId);
        if (window.type === 'normal' && !window.incognito) return window.id;
      } catch (_error) {
        // The user may have closed the original window and moved our tabs out.
      }
      state.workspaceWindowId = null;
    }
    const owned = await managedTabs();
    const windows = await chrome.windows.getAll({ windowTypes: ['normal'] });
    const candidates = windows.filter(window => !window.incognito);
    const lastFocused = await chrome.windows.getLastFocused({ windowTypes: ['normal'] }).catch(() => null);
    const window = candidates.find(window => window.id === owned[0]?.windowId)
      || candidates.find(window => window.id === lastFocused?.id)
      || candidates.find(window => window.focused)
      || candidates[0];
    if (window) {
      state.workspaceWindowId = window.id;
      return window.id;
    }
    const created = await chrome.windows.create({ url: 'about:blank', type: 'normal', focused: false });
    state.workspaceWindowId = created.id;
    // Only tabs returned from our own creation may become owned bootstrap tabs.
    const blank = created.tabs?.[0];
    if (blank?.id !== undefined) {
      state.managedTabIds.add(blank.id);
      state.bootstrapTabId = blank.id;
    }
    return created.id;
  }

  async function groupTab(tab) {
    if (state.workspaceGroupId !== null) {
      const group = await chrome.tabGroups.get(state.workspaceGroupId).catch(() => null);
      if (!group || group.windowId !== tab.windowId) state.workspaceGroupId = null;
    }
    if (state.workspaceGroupId === null) {
      state.workspaceGroupId = await chrome.tabs.group({ tabIds: [tab.id] });
      await chrome.tabGroups.update(state.workspaceGroupId, { title: GROUP_TITLE, color: GROUP_COLOR, collapsed: false });
    } else {
      await chrome.tabs.group({ tabIds: [tab.id], groupId: state.workspaceGroupId });
      // Adding a background page must not unfold a group the user collapsed.
    }
    const duplicates = await chrome.tabGroups.query({ windowId: tab.windowId, title: GROUP_TITLE, color: GROUP_COLOR });
    for (const group of duplicates) {
      if (group.id === state.workspaceGroupId || group.title !== GROUP_TITLE || group.shared) continue;
      const tabs = await chrome.tabs.query({ groupId: group.id });
      if (tabs.length) {
        // Consolidate legacy duplicates in this window without closing pages,
        // moving pages between windows, or adding them to managedTabIds.
        await chrome.tabs.group({ tabIds: tabs.map(tab => tab.id), groupId: state.workspaceGroupId });
      }
    }
  }

  async function closeManagedTab(tabId) {
    if (!state.managedTabIds.has(tabId)) throw new Error('Tab is not managed by Browser CLI');
    const tab = await chrome.tabs.get(tabId);
    // Remove our membership first: closing the last grouped tab can leave a
    // saved group in Chrome. Never ungroup personal members during teardown.
    if (tab.groupId >= 0) await chrome.tabs.ungroup([tabId]);
    await chrome.tabs.remove(tabId);
    await releaseTabDebugger(tabId);
    untrackTab(tabId);
  }

  async function open(url, { observeNetwork = true, bootstrap = false } = {}) {
    const windowId = await ensureWorkspaceWindow();
    let tab;
    if (state.bootstrapTabId !== null) {
      const candidate = await chrome.tabs.get(state.bootstrapTabId).catch(() => null);
      state.bootstrapTabId = null;
      // Never navigate a bootstrap page that the user has since used themselves.
      if (candidate?.windowId === windowId
          && (candidate.url || candidate.pendingUrl) === 'about:blank'
          && (!candidate.pendingUrl || candidate.pendingUrl === 'about:blank')) tab = candidate;
    }
    tab ||= await chrome.tabs.create({ windowId, url: 'about:blank', active: false });
    if (tab.id === undefined) throw new Error('Workspace tab creation failed');
    state.managedTabIds.add(tab.id);
    try {
      await groupTab(tab);
      // Interactive tabs retain network history from the first navigation.
      // One-shot reads close immediately and never expose network commands.
      if (observeNetwork) await ensureNetworkSession(tab.id);
      if (url && url !== 'about:blank') {
        await chrome.tabs.update(tab.id, { url });
        await waitForLoad(tab.id, 30);
      }
      if (bootstrap) state.bootstrapTabId = tab.id;
      return await chrome.tabs.get(tab.id);
    } catch (error) {
      // Failed opens have no caller that could later close the debug session.
      try {
        await closeManagedTab(tab.id);
      } catch (_error) {
        // Retain ownership so workspace teardown can retry removing this tab.
        await releaseTabDebugger(tab.id).catch(() => {});
      }
      throw error;
    }
  }

  function openTab(url, options) {
    const operation = pendingOpen.then(() => open(url, options));
    pendingOpen = operation.catch(() => {});
    return operation;
  }

  async function closeWorkspaceTabs() {
    await pendingOpen;
    for (const tab of await managedTabs()) {
      await closeManagedTab(tab.id);
    }
    state.workspaceWindowId = null;
    state.workspaceGroupId = null;
    state.bootstrapTabId = null;
  }

  async function getWorkspaceWindowState() {
    const tabs = await managedTabs();
    // Follow a group moved to a different window without adopting user tabs.
    if (state.workspaceGroupId !== null) {
      const group = await chrome.tabGroups.get(state.workspaceGroupId).catch(() => null);
      state.workspaceGroupId = group?.id ?? null;
      if (group) state.workspaceWindowId = group.windowId;
    }
    const window = state.workspaceWindowId === null ? null
      : await chrome.windows.get(state.workspaceWindowId).catch(() => null);
    state.workspaceWindowId = window?.id ?? tabs[0]?.windowId ?? null;
    return {
      window_id: state.workspaceWindowId,
      // Preserve the workspace meaning; personal tabs are never counted.
      tab_count: tabs.length,
      managed_tab_count: tabs.length,
      binding_state: tabs.length ? 'tracked' : state.workspaceWindowId === null ? 'absent' : 'stale',
    };
  }

  return { ensureWorkspaceWindow, openTab, managedTabs, closeManagedTab, closeWorkspaceTabs, getWorkspaceWindowState };
}
