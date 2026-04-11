import {
  dragBetweenLocatorsJs,
  markUploadTargetJs,
  locatorActionJs,
} from '../page_runtime.js';
import { setFileInputFiles } from '../debugger.js';

async function handleUpload(context, tabId, payload) {
  const marker = `upload-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const target = await context.executeExpression(tabId, markUploadTargetJs(payload.locator, marker));
  await setFileInputFiles(tabId, [payload.path], target.selector);
  return { uploaded: true, path: payload.path };
}

export function createLocatorHandlers(context) {
  return {
    async 'eval-on'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'eval-on', payload.locator, payload);
    },
    async click(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'click', payload.locator, payload);
    },
    async 'double-click'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'double-click', payload.locator, payload);
    },
    async hover(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'hover', payload.locator, payload);
    },
    async focus(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'focus', payload.locator, payload);
    },
    async fill(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'fill', payload.locator, payload);
    },
    async select(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'select', payload.locator, payload);
    },
    async options(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'options', payload.locator, payload);
    },
    async check(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'check', payload.locator, payload);
    },
    async 'scroll-to'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'scroll-to', payload.locator, payload);
    },
    async 'verify-state'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'verify-state', payload.locator, payload);
    },
    async 'verify-value'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.runLocatorAction(payload.tab_id, 'verify-value', payload.locator, payload);
    },
    async drag(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(
        payload.tab_id,
        dragBetweenLocatorsJs(payload.start_locator, payload.end_locator),
      );
    },
    async upload(payload) {
      await context.getManagedTab(payload.tab_id);
      return await handleUpload(context, payload.tab_id, payload);
    },
  };
}
