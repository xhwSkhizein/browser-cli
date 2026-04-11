import { flushAllPendingVideoArtifacts, flushPendingVideoArtifactsForTab } from './video_actions.js';

function artifactRequestedPath(artifact) {
  return String(artifact?.metadata?.requested_path || '');
}

export function createWorkspaceHandlers(context) {
  return {
    async 'workspace-close'(_payload, meta) {
      const artifacts = await flushAllPendingVideoArtifacts(context, meta.requestId);
      if (context.state.workspaceWindowId !== null) {
        try {
          await chrome.windows.remove(context.state.workspaceWindowId);
        } catch (_error) {
          // Ignore already-closed workspace windows.
        }
      }
      context.state.workspaceWindowId = null;
      context.state.managedTabIds.clear();
      context.state.pageIdByTabId.clear();
      return {
        closed: true,
        video_paths: artifacts.map(artifactRequestedPath).filter(Boolean),
        artifacts,
      };
    },
    async 'open-tab'(payload) {
      const tab = await context.openTab(payload.url || 'about:blank');
      if (payload.page_id) {
        context.state.pageIdByTabId.set(tab.id, String(payload.page_id));
      }
      return {
        tab_id: tab.id,
        url: tab.url || '',
        title: tab.title || '',
        page_id: payload.page_id || null,
      };
    },
    async 'list-tabs'() {
      if (context.state.workspaceWindowId === null) {
        return { tabs: [] };
      }
      const tabs = await chrome.tabs.query({ windowId: context.state.workspaceWindowId });
      return {
        tabs: tabs
          .filter((tab) => tab.id !== undefined && context.state.managedTabIds.has(tab.id))
          .map((tab) => ({
            tab_id: tab.id,
            page_id: context.pageIdForTab(tab.id),
            url: tab.url || '',
            title: tab.title || '',
            active: !!tab.active,
          })),
      };
    },
    async 'activate-tab'(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      await chrome.tabs.update(tab.id, { active: true });
      return {
        url: tab.url || '',
        title: tab.title || '',
        page_id: context.pageIdForTab(tab.id),
      };
    },
    async 'close-tab'(payload, meta) {
      const tab = await context.getManagedTab(payload.tab_id);
      const pageId = context.pageIdForTab(tab.id);
      const artifacts = await flushPendingVideoArtifactsForTab(context, meta.requestId, payload.tab_id);
      await chrome.tabs.remove(tab.id);
      context.untrackTab(tab.id);
      return {
        url: tab.url || '',
        title: tab.title || '',
        page_id: pageId,
        video_path: artifactRequestedPath(artifacts[0]) || null,
        artifacts,
      };
    },
    async 'page-summary'(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      return {
        url: tab.url || '',
        title: tab.title || '',
        page_id: context.pageIdForTab(tab.id),
      };
    },
  };
}
