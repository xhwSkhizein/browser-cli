import {
  getConsoleMessagesJs,
  installConsoleCaptureJs,
  stopConsoleCaptureJs,
  storageGetJs,
  storageSetJs,
  verifyTextJs,
  verifyTitleJs,
  verifyUrlJs,
  verifyVisibleJs,
  waitJs,
} from '../page_runtime.js';
import {
  getNetworkRecords,
  startNetworkCapture,
  stopNetworkCapture,
  waitForNetworkIdle,
  waitForNetworkRecord,
} from '../debugger.js';
import {
  buildArtifactDescriptor,
  decodeBase64Bytes,
  emitArtifact,
} from './artifact_actions.js';

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

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function networkFilterFromPayload(payload) {
  return {
    url_contains: payload.url_contains || null,
    url_regex: payload.url_regex || null,
    method: payload.method || null,
    status: payload.status ?? null,
    resource_type: payload.resource_type || null,
    mime_contains: payload.mime_contains || null,
    include_static: !!payload.include_static,
  };
}

async function materializeNetworkRecords(context, tabId, requestId, records) {
  const cloned = cloneJson(records || []);
  const artifacts = [];
  for (const record of cloned) {
    const body = record?.body || {};
    if (body.kind !== 'artifact') {
      continue;
    }
    const descriptor = buildArtifactDescriptor({
      artifactKind: 'network-body',
      mimeType: body.artifact_mime_type || record.mime_type || 'application/octet-stream',
      filename: body.artifact_filename || `${record.request_id || 'network-body'}.bin`,
      pageId: context.pageIdForTab(tabId),
      metadata: {
        network_request_id: record.request_id || null,
      },
    });
    await emitArtifact(context, requestId, descriptor, decodeBase64Bytes(body.artifact_base64 || ''));
    artifacts.push(descriptor);
    record.body = {
      kind: 'path',
      path: `artifact://${descriptor.artifact_id}`,
      bytes: Number(body.bytes || 0),
      truncated: !!body.truncated,
    };
  }
  return { records: cloned, artifacts };
}

export function createObserveHandlers(context) {
  return {
    async wait(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, waitJs(payload));
    },
    async 'wait-network'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await waitForNetworkIdle(
        payload.tab_id,
        { timeoutMs: Math.max(0, Number(payload.timeout_seconds || 30) * 1000) },
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
      return await startNetworkCapture(payload.tab_id);
    },
    async network(payload, meta) {
      await context.getManagedTab(payload.tab_id);
      const records = await getNetworkRecords(
        payload.tab_id,
        networkFilterFromPayload(payload),
        { clear: payload.clear !== false },
      );
      const materialized = await materializeNetworkRecords(context, payload.tab_id, meta.requestId, records);
      return {
        records: materialized.records,
        artifacts: materialized.artifacts,
      };
    },
    async 'network-wait'(payload, meta) {
      await context.getManagedTab(payload.tab_id);
      const record = await waitForNetworkRecord(
        payload.tab_id,
        networkFilterFromPayload(payload),
        { timeoutMs: Math.max(0, Number(payload.timeout_seconds || 30) * 1000) },
      );
      const materialized = await materializeNetworkRecords(context, payload.tab_id, meta.requestId, [record]);
      return {
        record: materialized.records[0] || null,
        artifacts: materialized.artifacts,
      };
    },
    async 'network-stop'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await stopNetworkCapture(payload.tab_id);
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
