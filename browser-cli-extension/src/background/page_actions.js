import {
  captureHtmlJs,
  generateSnapshotJs,
  pageInfoJs,
} from '../page_runtime.js';

export function createPageHandlers(context) {
  return {
    async 'page-info'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, pageInfoJs());
    },
    async 'capture-html'(payload) {
      await context.getManagedTab(payload.tab_id);
      const html = await context.executeExpression(payload.tab_id, captureHtmlJs());
      return { html };
    },
    async 'capture-snapshot-input'(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      const rawSnapshot = await context.executeExpression(
        payload.tab_id,
        generateSnapshotJs({ interactive: !!payload.interactive }),
      );
      return {
        raw_snapshot: rawSnapshot || '',
        captured_url: tab.url || '',
        captured_at: Date.now() / 1000,
      };
    },
    async navigate(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      await chrome.tabs.update(tab.id, { url: payload.url });
      await context.waitForLoad(tab.id, Number(payload.timeout_seconds || 30));
      const refreshed = await chrome.tabs.get(tab.id);
      return { url: refreshed.url || payload.url || '', title: refreshed.title || '' };
    },
    async reload(payload) {
      await context.getManagedTab(payload.tab_id);
      await chrome.tabs.reload(payload.tab_id);
      await context.waitForLoad(payload.tab_id, Number(payload.timeout_seconds || 30));
      const tab = await chrome.tabs.get(payload.tab_id);
      return { url: tab.url || '', title: tab.title || '' };
    },
    async 'go-back'(payload) {
      await context.getManagedTab(payload.tab_id);
      await context.executeExpression(payload.tab_id, 'history.back(); true');
      await context.waitForLoad(payload.tab_id, 15);
      const tab = await chrome.tabs.get(payload.tab_id);
      return { url: tab.url || '', title: tab.title || '' };
    },
    async 'go-forward'(payload) {
      await context.getManagedTab(payload.tab_id);
      await context.executeExpression(payload.tab_id, 'history.forward(); true');
      await context.waitForLoad(payload.tab_id, 15);
      const tab = await chrome.tabs.get(payload.tab_id);
      return { url: tab.url || '', title: tab.title || '' };
    },
    async resize(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      await chrome.windows.update(tab.windowId, {
        width: Number(payload.width),
        height: Number(payload.height),
      });
      return { width: Number(payload.width), height: Number(payload.height) };
    },
    async eval(payload) {
      await context.getManagedTab(payload.tab_id);
      const result = await context.executeExpression(payload.tab_id, payload.code);
      return { result };
    },
  };
}
