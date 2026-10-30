import { flushAllPendingVideoArtifacts, flushPendingVideoArtifactsForTab } from './video_actions.js';
import {queryRuntimeTabs} from '../runtime_health.js';

function artifactRequestedPath(artifact) {
  return String(artifact?.metadata?.requested_path || '');
}

/** Probe the bound window without discarding ownership on a transient API failure. */
export async function buildWorkspaceStatus(context) {
  const windowId = context.state.workspaceWindowId;
  if (windowId === null) {
    await queryRuntimeTabs();
    return { window_id: null, tab_count: 0, managed_tab_count: 0, binding_state: 'absent' };
  }

  try {
    const tabs = await queryRuntimeTabs({ windowId });
    const managedTabs = tabs.filter(
      (tab) => tab.id !== undefined && context.state.managedTabIds.has(tab.id),
    );
    return {
      window_id: windowId,
      tab_count: tabs.length,
      managed_tab_count: managedTabs.length,
      binding_state: managedTabs.length > 0 ? 'tracked' : 'stale',
    };
  } catch (_error) {
    if (_error?.code === 'EXTENSION_RUNTIME_UNHEALTHY') throw _error;
    if (!/No window with id/i.test(String(_error?.message))) throw _error;
    context.state.workspaceWindowId = null;
    context.state.managedTabIds.clear();
    context.state.pageIdByTabId.clear();
    await context.saveWorkspaceBinding();
    return { window_id: null, tab_count: 0, managed_tab_count: 0, binding_state: 'absent' };
  }
}

/** Bind workspace actions to shared ownership, recording, and persistence helpers. */
export function createWorkspaceHandlers(context) {
  return {
    /** Tear down workspace tracking after collecting pending recording artifacts. */
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
      await context.saveWorkspaceBinding();
      return {
        closed: true,
        video_paths: artifacts.map(artifactRequestedPath).filter(Boolean),
        artifacts,
      };
    },
    async 'workspace-status'() {
      return await buildWorkspaceStatus(context);
    },
    /** Replace the dedicated workspace binding and retain emitted recordings. */
    async 'workspace-rebuild-binding'(_payload, meta) {
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
      await context.saveWorkspaceBinding();
      await context.ensureWorkspaceWindow('about:blank');
      return {
        rebuilt: true,
        video_paths: artifacts.map(artifactRequestedPath).filter(Boolean),
        artifacts,
        ...(await buildWorkspaceStatus(context)),
      };
    },
    /** Open a managed tab and persist its daemon page identifier. */
    async 'open-tab'(payload) {
      const tab = await context.openTab(payload.url || 'about:blank');
      if (payload.page_id) {
        context.state.pageIdByTabId.set(tab.id, String(payload.page_id));
      }
      await context.saveWorkspaceBinding();
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
    /** Preserve confirmed Chrome closure even if later persistence cleanup fails. */
    async 'close-tab'(payload, meta) {
      const tab = await context.getManagedTab(payload.tab_id);
      const pageId = context.pageIdForTab(tab.id);
      const artifacts = await flushPendingVideoArtifactsForTab(context, meta.requestId, payload.tab_id);
      await chrome.tabs.remove(tab.id);
      await context.untrackTab(tab.id).catch(error => {
        // Chrome confirmed destruction. Stale storage cannot restore a removed
        // target, so persistence failure must not turn this into a failed close.
        context.state.runtimeState = context.state.runtimeState || {};
        context.state.runtimeState.lastError = `Page closed; workspace cleanup failed: ${String(error?.message || error)}`;
      });
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
