import {
  getConsoleMessagesJs,
  getNetworkRequestsJs,
  installConsoleCaptureJs,
  installNetworkCaptureJs,
  stopConsoleCaptureJs,
  stopNetworkCaptureJs,
  storageGetJs,
  storageSetJs,
  verifyTextJs,
  verifyTitleJs,
  verifyUrlJs,
  verifyVisibleJs,
  waitForNetworkIdleJs,
  waitJs,
} from '../page_runtime.js';

async function setCookieForTab(context, tabId, payload) {
  const tab = await context.getManagedTab(tabId);
  const currentUrl = tab.url || 'https://example.com/';
  const targetUrl = payload.domain
    ? `${payload.secure ? 'https' : 'http'}://${String(payload.domain).replace(/^\./, '')}${payload.path || '/'}`
    : currentUrl;
  const cookie = await chrome.cookies.set({
    url: targetUrl,
    name: payload.name,
    value: payload.value,
    domain: payload.domain || undefined,
    path: payload.path || '/',
    expirationDate: payload.expires || undefined,
    httpOnly: !!payload.http_only,
    secure: !!payload.secure,
    sameSite: payload.same_site || undefined,
  });
  return { cookie };
}

async function clearCookiesForTab(context, tabId, payload) {
  const tab = await context.getManagedTab(tabId);
  const currentUrl = tab.url || 'https://example.com/';
  const cookies = await chrome.cookies.getAll({
    url: currentUrl,
    name: payload.name || undefined,
    domain: payload.domain || undefined,
  });
  let cleared = 0;
  for (const cookie of cookies) {
    if (payload.path && (cookie.path || '') !== payload.path) {
      continue;
    }
    const protocol = cookie.secure ? 'https://' : 'http://';
    const domain = (cookie.domain || '').replace(/^\./, '');
    const removalUrl = `${protocol}${domain}${cookie.path || '/'}`;
    await chrome.cookies.remove({
      url: removalUrl,
      name: cookie.name,
      storeId: cookie.storeId,
    });
    cleared += 1;
  }
  return { cleared };
}

export function createObserveHandlers(context) {
  return {
    async wait(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, waitJs(payload));
    },
    async 'wait-network'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(
        payload.tab_id,
        waitForNetworkIdleJs({ timeoutSeconds: Number(payload.timeout_seconds || 30) }),
      );
    },
    async 'console-start'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, installConsoleCaptureJs());
    },
    async 'console-get'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, getConsoleMessagesJs(payload));
    },
    async 'console-stop'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, stopConsoleCaptureJs());
    },
    async 'network-start'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, installNetworkCaptureJs());
    },
    async 'network-get'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, getNetworkRequestsJs(payload));
    },
    async 'network-stop'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, stopNetworkCaptureJs());
    },
    async 'cookies-get'(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      const url = tab.url || 'https://example.com/';
      const cookies = await chrome.cookies.getAll({
        url,
        name: payload.name || undefined,
        domain: payload.domain || undefined,
      });
      return {
        cookies: cookies.filter((cookie) => !payload.path || (cookie.path || '').startsWith(payload.path)),
      };
    },
    async 'cookie-set'(payload) {
      return await setCookieForTab(context, payload.tab_id, payload);
    },
    async 'cookies-clear'(payload) {
      return await clearCookiesForTab(context, payload.tab_id, payload);
    },
    async 'storage-get'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, storageGetJs());
    },
    async 'storage-set'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, storageSetJs(payload));
    },
    async 'verify-text'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(
        payload.tab_id,
        verifyTextJs({
          text: payload.text,
          exact: !!payload.exact,
          timeoutSeconds: Number(payload.timeout_seconds || 5),
        }),
      );
    },
    async 'verify-url'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, verifyUrlJs(payload));
    },
    async 'verify-title'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, verifyTitleJs(payload));
    },
    async 'verify-visible'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(
        payload.tab_id,
        verifyVisibleJs({
          role: payload.role,
          name: payload.name,
          timeoutSeconds: Number(payload.timeout_seconds || 5),
        }),
      );
    },
  };
}
