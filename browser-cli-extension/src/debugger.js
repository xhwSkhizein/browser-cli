const attached = new Set();
const traceWaiters = new Map();
const screencastConsumers = new Map();
const networkSessions = new Map();

const DEFAULT_NETWORK_RECENT_LIMIT = 200;
const DEFAULT_NETWORK_CAPTURE_LIMIT = 200;
const DEFAULT_TRACE_CAPTURE_LIMIT = 200;
const INLINE_TEXT_MAX_BYTES = 128 * 1024;
const INLINE_BINARY_MAX_BYTES = 64 * 1024;
const MAX_CAPTURE_BODY_BYTES = 8 * 1024 * 1024;
const STATIC_RESOURCE_TYPES = new Set(['image', 'stylesheet', 'script', 'font', 'media']);

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

function isDebuggableUrl(url = '') {
  return url.startsWith('http://') || url.startsWith('https://') || url.startsWith('file://') || url === 'about:blank';
}

function encodeUtf8(value = '') {
  return textEncoder.encode(String(value || ''));
}

function decodeUtf8(bytes) {
  return textDecoder.decode(bytes);
}

function bytesToBase64(bytes) {
  let text = '';
  for (let index = 0; index < bytes.length; index += 0x8000) {
    text += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(text);
}

function decodeBase64Bytes(value = '') {
  return Uint8Array.from(atob(String(value || '')), (char) => char.charCodeAt(0));
}

function base64ByteLength(value = '') {
  const normalized = String(value || '');
  if (!normalized) {
    return 0;
  }
  let padding = 0;
  if (normalized.endsWith('==')) {
    padding = 2;
  } else if (normalized.endsWith('=')) {
    padding = 1;
  }
  return Math.floor((normalized.length * 3) / 4) - padding;
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeHeaders(headers = {}) {
  const normalized = {};
  for (const [key, value] of Object.entries(headers || {})) {
    normalized[String(key)] = Array.isArray(value) ? value.join(', ') : String(value ?? '');
  }
  return normalized;
}

function extractMimeType(headers = {}, fallback = '') {
  for (const [key, value] of Object.entries(headers || {})) {
    if (String(key).toLowerCase() !== 'content-type') {
      continue;
    }
    return String(value || '').split(';', 1)[0].trim().toLowerCase();
  }
  return String(fallback || '').split(';', 1)[0].trim().toLowerCase();
}

function parseContentLength(headers = {}) {
  for (const [key, value] of Object.entries(headers || {})) {
    if (String(key).toLowerCase() !== 'content-length') {
      continue;
    }
    const parsed = Number.parseInt(String(value || ''), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function chooseBodyFilename(publicRequestId, url = '', mimeType = '') {
  try {
    const parsed = new URL(url);
    const pathname = parsed.pathname || '';
    const suffix = pathname.includes('.') ? pathname.slice(pathname.lastIndexOf('.')) : '';
    if (suffix) {
      return `${publicRequestId}${suffix}`;
    }
  } catch (_error) {
    // ignore invalid URLs
  }
  if (mimeType.includes('json')) return `${publicRequestId}.json`;
  if (mimeType.includes('html')) return `${publicRequestId}.html`;
  if (mimeType.includes('xml')) return `${publicRequestId}.xml`;
  if (mimeType.startsWith('text/')) return `${publicRequestId}.txt`;
  if (mimeType.includes('javascript')) return `${publicRequestId}.js`;
  if (mimeType.includes('css')) return `${publicRequestId}.css`;
  if (mimeType.includes('svg')) return `${publicRequestId}.svg`;
  return `${publicRequestId}.bin`;
}

function isTextualMime(mimeType = '') {
  const normalized = String(mimeType || '').toLowerCase();
  if (!normalized) {
    return false;
  }
  if (normalized.startsWith('text/')) {
    return true;
  }
  return ['json', 'xml', 'javascript', 'ecmascript', 'svg', 'x-www-form-urlencoded'].some((token) => normalized.includes(token));
}

function isStaticResourceType(resourceType = '') {
  return STATIC_RESOURCE_TYPES.has(String(resourceType || '').toLowerCase());
}

function normalizeResourceType(resourceType = '') {
  return String(resourceType || '').toLowerCase();
}

function trimArray(items, limit) {
  while (items.length > limit) {
    items.shift();
  }
}

function matchesNetworkFilter(record, filter = {}) {
  if (!filter.include_static && isStaticResourceType(record.resource_type)) {
    return false;
  }
  if (filter.url_contains && !String(record.url || '').includes(String(filter.url_contains))) {
    return false;
  }
  if (filter.url_regex) {
    try {
      const regex = new RegExp(String(filter.url_regex));
      if (!regex.test(String(record.url || ''))) {
        return false;
      }
    } catch (_error) {
      return false;
    }
  }
  if (filter.method && String(record.method || '').toUpperCase() !== String(filter.method || '').toUpperCase()) {
    return false;
  }
  if (filter.status !== undefined && filter.status !== null && Number(record.status || 0) !== Number(filter.status)) {
    return false;
  }
  if (filter.resource_type && String(record.resource_type || '') !== String(filter.resource_type || '')) {
    return false;
  }
  if (filter.mime_contains && !String(record.mime_type || '').toLowerCase().includes(String(filter.mime_contains || '').toLowerCase())) {
    return false;
  }
  return true;
}

function createNetworkSession() {
  return {
    enabled: false,
    capturing: false,
    recentRecords: [],
    capturedRecords: [],
    pendingByRequestId: new Map(),
    waiters: [],
    traceBuffers: new Map(),
    pendingCount: 0,
    lastActivityAt: Date.now(),
    sequence: 0,
  };
}

export function disposeNetworkSession(tabId) {
  const session = networkSessions.get(tabId);
  if (!session) {
    return;
  }
  for (const waiter of session.waiters) {
    clearTimeout(waiter.timeoutId);
    waiter.reject(new Error(`Tab ${tabId} is no longer available.`));
  }
  session.waiters = [];
  networkSessions.delete(tabId);
}

function ensureSession(tabId) {
  let session = networkSessions.get(tabId);
  if (!session) {
    session = createNetworkSession();
    networkSessions.set(tabId, session);
  }
  return session;
}

function touchNetworkActivity(session, { pendingDelta = 0 } = {}) {
  session.pendingCount = Math.max(0, Number(session.pendingCount || 0) + pendingDelta);
  session.lastActivityAt = Date.now();
}

function addTraceRecord(session, record) {
  for (const buffer of session.traceBuffers.values()) {
    buffer.records.push(record);
    trimArray(buffer.records, DEFAULT_TRACE_CAPTURE_LIMIT);
  }
}

function publishNetworkRecord(session, record) {
  session.recentRecords.push(record);
  trimArray(session.recentRecords, DEFAULT_NETWORK_RECENT_LIMIT);
  if (session.capturing) {
    session.capturedRecords.push(record);
    trimArray(session.capturedRecords, DEFAULT_NETWORK_CAPTURE_LIMIT);
  }
  addTraceRecord(session, record);
  const remainingWaiters = [];
  for (const waiter of session.waiters) {
    if (matchesNetworkFilter(record, waiter.filter)) {
      clearTimeout(waiter.timeoutId);
      waiter.resolve(cloneJson(record));
      continue;
    }
    remainingWaiters.push(waiter);
  }
  session.waiters = remainingWaiters;
}

function buildPendingRequest(session, params) {
  session.sequence += 1;
  return {
    publicRequestId: `tab-${session.sequence.toString().padStart(4, '0')}`,
    requestId: String(params.requestId || ''),
    url: String(params.request?.url || ''),
    method: String(params.request?.method || ''),
    resourceType: normalizeResourceType(params.type || ''),
    requestHeaders: normalizeHeaders(params.request?.headers || {}),
    requestPostData: params.request?.postData ? String(params.request.postData) : null,
    responseHeaders: {},
    mimeType: '',
    status: 0,
    ok: false,
    startedAt: Date.now() / 1000,
  };
}

function upsertPendingRequest(tabId, params) {
  const session = ensureSession(tabId);
  const existing = session.pendingByRequestId.get(String(params.requestId || ''));
  if (existing) {
    return existing;
  }
  const pending = buildPendingRequest(session, params);
  session.pendingByRequestId.set(String(params.requestId || ''), pending);
  return pending;
}

async function buildResponseBodyPayload(tabId, pending) {
  const contentLength = parseContentLength(pending.responseHeaders);
  if (contentLength !== null && contentLength > MAX_CAPTURE_BODY_BYTES) {
    return {
      kind: 'omitted',
      bytes: contentLength,
      truncated: false,
      error: 'Response body exceeded the capture limit.',
    };
  }
  let responseBody;
  try {
    responseBody = await sendCommand(tabId, 'Network.getResponseBody', { requestId: pending.requestId });
  } catch (error) {
    return {
      kind: 'unavailable',
      bytes: contentLength || 0,
      truncated: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
  const rawBody = String(responseBody?.body || '');
  const base64Encoded = !!responseBody?.base64Encoded;
  const mimeType = pending.mimeType || extractMimeType(pending.responseHeaders);
  const bytesLength = base64Encoded ? base64ByteLength(rawBody) : encodeUtf8(rawBody).length;
  if (bytesLength > MAX_CAPTURE_BODY_BYTES) {
    return {
      kind: 'omitted',
      bytes: bytesLength,
      truncated: false,
      error: 'Response body exceeded the capture limit.',
    };
  }
  if (isTextualMime(mimeType)) {
    const text = base64Encoded ? decodeUtf8(decodeBase64Bytes(rawBody)) : rawBody;
    if (bytesLength <= INLINE_TEXT_MAX_BYTES) {
      return {
        kind: 'text',
        text,
        bytes: bytesLength,
        truncated: false,
      };
    }
    return {
      kind: 'artifact',
      artifact_base64: base64Encoded ? rawBody : bytesToBase64(encodeUtf8(rawBody)),
      artifact_filename: chooseBodyFilename(pending.publicRequestId, pending.url, mimeType),
      artifact_mime_type: mimeType || 'text/plain',
      bytes: bytesLength,
      truncated: false,
    };
  }
  const base64 = base64Encoded ? rawBody : bytesToBase64(encodeUtf8(rawBody));
  if (bytesLength <= INLINE_BINARY_MAX_BYTES) {
    return {
      kind: 'base64',
      base64,
      bytes: bytesLength,
      truncated: false,
    };
  }
  return {
    kind: 'artifact',
    artifact_base64: base64,
    artifact_filename: chooseBodyFilename(pending.publicRequestId, pending.url, mimeType),
    artifact_mime_type: mimeType || 'application/octet-stream',
    bytes: bytesLength,
    truncated: false,
  };
}

function buildCompletedRecord(pending, { endedAt, failed = false, failureReason = null, body }) {
  return {
    request_id: pending.publicRequestId,
    url: pending.url,
    method: pending.method,
    resource_type: pending.resourceType,
    status: Number(pending.status || 0),
    ok: !!pending.ok && !failed,
    request_headers: cloneJson(pending.requestHeaders || {}),
    request_post_data: pending.requestPostData ?? null,
    response_headers: cloneJson(pending.responseHeaders || {}),
    mime_type: pending.mimeType || '',
    started_at: Number(pending.startedAt || 0),
    ended_at: Number(endedAt || pending.startedAt || 0),
    duration_ms: Math.max((Number(endedAt || 0) - Number(pending.startedAt || 0)) * 1000, 0),
    failed,
    failure_reason: failureReason,
    body,
  };
}

async function finalizeSuccessfulRequest(tabId, requestId) {
  const session = networkSessions.get(tabId);
  if (!session) {
    return;
  }
  const pending = session.pendingByRequestId.get(String(requestId || ''));
  if (!pending) {
    return;
  }
  session.pendingByRequestId.delete(String(requestId || ''));
  const body = await buildResponseBodyPayload(tabId, pending);
  publishNetworkRecord(
    session,
    buildCompletedRecord(pending, {
      endedAt: Date.now() / 1000,
      failed: false,
      failureReason: null,
      body,
    }),
  );
}

function finalizeFailedRequest(tabId, requestId, failureReason) {
  const session = networkSessions.get(tabId);
  if (!session) {
    return;
  }
  const pending = session.pendingByRequestId.get(String(requestId || ''));
  if (!pending) {
    return;
  }
  session.pendingByRequestId.delete(String(requestId || ''));
  publishNetworkRecord(
    session,
    buildCompletedRecord(pending, {
      endedAt: Date.now() / 1000,
      failed: true,
      failureReason,
      body: {
        kind: 'unavailable',
        bytes: 0,
        truncated: false,
        error: failureReason,
      },
    }),
  );
}

export async function ensureAttached(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (!isDebuggableUrl(tab.url || '')) {
    throw new Error(`Tab ${tabId} is not debuggable: ${tab.url || 'unknown'}`);
  }
  if (attached.has(tabId)) {
    return;
  }
  await chrome.debugger.attach({ tabId }, '1.3');
  attached.add(tabId);
}

export async function sendCommand(tabId, method, params = {}) {
  await ensureAttached(tabId);
  return await chrome.debugger.sendCommand({ tabId }, method, params);
}

async function readProtocolStream(tabId, handle) {
  let text = '';
  while (true) {
    const chunk = await sendCommand(tabId, 'IO.read', { handle });
    text += String(chunk.data || '');
    if (chunk.eof) {
      break;
    }
  }
  await sendCommand(tabId, 'IO.close', { handle }).catch(() => {});
  return text;
}

export async function ensureNetworkSession(tabId) {
  const session = ensureSession(tabId);
  if (session.enabled) {
    return session;
  }
  await sendCommand(tabId, 'Network.enable');
  session.enabled = true;
  session.lastActivityAt = Date.now();
  return session;
}

export async function startNetworkCapture(tabId) {
  const session = await ensureNetworkSession(tabId);
  session.capturing = true;
  session.capturedRecords = [];
  return { capturing: true };
}

export async function getNetworkRecords(tabId, filter = {}, { clear = true } = {}) {
  const session = await ensureNetworkSession(tabId);
  const matched = [];
  const retained = [];
  for (const record of session.capturedRecords) {
    if (matchesNetworkFilter(record, filter)) {
      matched.push(cloneJson(record));
      if (!clear) {
        retained.push(record);
      }
      continue;
    }
    retained.push(record);
  }
  if (clear) {
    session.capturedRecords = retained;
  }
  return matched;
}

export async function waitForNetworkRecord(tabId, filter = {}, { timeoutMs = 30000 } = {}) {
  const session = await ensureNetworkSession(tabId);
  for (let index = session.recentRecords.length - 1; index >= 0; index -= 1) {
    const record = session.recentRecords[index];
    if (matchesNetworkFilter(record, filter)) {
      return cloneJson(record);
    }
  }
  return await new Promise((resolve, reject) => {
    const waiter = {
      filter,
      resolve,
      reject,
      timeoutId: setTimeout(() => {
        session.waiters = session.waiters.filter((item) => item !== waiter);
        reject(new Error(`Timed out waiting for a matching network record after ${Math.round(timeoutMs / 100) / 10}s.`));
      }, timeoutMs),
    };
    session.waiters.push(waiter);
  });
}

export async function stopNetworkCapture(tabId) {
  const session = await ensureNetworkSession(tabId);
  session.capturing = false;
  return { capturing: false };
}

export async function waitForNetworkIdle(tabId, { timeoutMs = 30000, quietMs = 500 } = {}) {
  const session = await ensureNetworkSession(tabId);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const idleFor = Date.now() - Number(session.lastActivityAt || 0);
    if (Number(session.pendingCount || 0) === 0 && idleFor >= quietMs) {
      return { network_idle: true, quiet_ms: quietMs };
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error('network idle timed out');
}

export async function startTraceNetworkCapture(tabId, traceId = 'trace') {
  const session = await ensureNetworkSession(tabId);
  session.traceBuffers.set(String(traceId), {
    records: [],
    startedAt: Date.now(),
  });
}

export async function stopTraceNetworkCapture(tabId, traceId = 'trace') {
  const session = await ensureNetworkSession(tabId);
  const buffer = session.traceBuffers.get(String(traceId));
  session.traceBuffers.delete(String(traceId));
  return cloneJson(buffer?.records || []);
}

export async function captureScreenshot(tabId, { format = 'png', fullPage = false } = {}) {
  if (fullPage) {
    const metrics = await sendCommand(tabId, 'Page.getLayoutMetrics');
    const size = metrics.cssContentSize || metrics.contentSize;
    if (size) {
      await sendCommand(tabId, 'Emulation.setDeviceMetricsOverride', {
        mobile: false,
        width: Math.ceil(size.width),
        height: Math.ceil(size.height),
        deviceScaleFactor: 1,
      });
    }
  }
  try {
    const result = await sendCommand(tabId, 'Page.captureScreenshot', { format });
    return String(result.data || '');
  } finally {
    if (fullPage) {
      await sendCommand(tabId, 'Emulation.clearDeviceMetricsOverride').catch(() => {});
    }
  }
}

export async function printToPdf(tabId) {
  const result = await sendCommand(tabId, 'Page.printToPDF', {
    printBackground: true,
  });
  return String(result.data || '');
}

export async function startTracing(
  tabId,
  {
    screenshots = true,
    snapshots = true,
    sources = false,
  } = {},
) {
  const categories = [
    'devtools.timeline',
    'disabled-by-default-devtools.timeline',
    'disabled-by-default-devtools.timeline.frame',
    'blink.user_timing',
    'v8.execute',
    'netlog',
  ];
  if (screenshots) {
    categories.push('disabled-by-default-devtools.screenshot');
  }
  if (snapshots) {
    categories.push('disabled-by-default-devtools.timeline.stack');
  }
  if (sources) {
    categories.push('disabled-by-default-devtools.v8.compile');
  }
  await sendCommand(tabId, 'Tracing.start', {
    transferMode: 'ReturnAsStream',
    categories: categories.join(','),
  });
}

export async function stopTracing(tabId) {
  await ensureAttached(tabId);
  const waiter = new Promise((resolve, reject) => {
    traceWaiters.set(tabId, { resolve, reject });
  });
  await sendCommand(tabId, 'Tracing.end');
  const streamHandle = await waiter;
  return await readProtocolStream(tabId, streamHandle);
}

export async function startScreencast(
  tabId,
  {
    format = 'jpeg',
    quality = 70,
    everyNthFrame = 1,
    maxWidth = undefined,
    maxHeight = undefined,
    onFrame = null,
  } = {},
) {
  await ensureAttached(tabId);
  screencastConsumers.set(tabId, onFrame);
  await sendCommand(tabId, 'Page.startScreencast', {
    format,
    quality,
    everyNthFrame,
    maxWidth,
    maxHeight,
  });
}

export async function stopScreencast(tabId) {
  await ensureAttached(tabId);
  try {
    await sendCommand(tabId, 'Page.stopScreencast');
  } finally {
    screencastConsumers.delete(tabId);
  }
}

export async function setFileInputFiles(tabId, files, selector) {
  await sendCommand(tabId, 'DOM.enable');
  const doc = await sendCommand(tabId, 'DOM.getDocument');
  const query = selector || 'input[type="file"]';
  const result = await sendCommand(tabId, 'DOM.querySelector', {
    nodeId: doc.root.nodeId,
    selector: query,
  });
  if (!result.nodeId) {
    throw new Error(`No element found matching selector: ${query}`);
  }
  await sendCommand(tabId, 'DOM.setFileInputFiles', {
    files,
    nodeId: result.nodeId,
  });
}

export async function handleJavascriptDialog(tabId, { accept = true, promptText = null } = {}) {
  await sendCommand(tabId, 'Page.handleJavaScriptDialog', {
    accept,
    promptText: promptText ?? undefined,
  });
}

export function registerDebuggerListeners() {
  chrome.tabs.onRemoved.addListener((tabId) => {
    attached.delete(tabId);
    screencastConsumers.delete(tabId);
    disposeNetworkSession(tabId);
    const trace = traceWaiters.get(tabId);
    if (trace) {
      trace.reject(new Error(`Tab ${tabId} was removed while tracing.`));
      traceWaiters.delete(tabId);
    }
  });
  chrome.debugger.onDetach.addListener((source) => {
    if (source.tabId) {
      attached.delete(source.tabId);
      screencastConsumers.delete(source.tabId);
      disposeNetworkSession(source.tabId);
      const trace = traceWaiters.get(source.tabId);
      if (trace) {
        trace.reject(new Error(`Debugger detached from tab ${source.tabId}.`));
        traceWaiters.delete(source.tabId);
      }
    }
  });
  chrome.debugger.onEvent.addListener((source, method, params) => {
    if (!source.tabId) {
      return;
    }
    if (method === 'Tracing.tracingComplete') {
      const trace = traceWaiters.get(source.tabId);
      if (!trace) {
        return;
      }
      trace.resolve(String(params?.stream || ''));
      traceWaiters.delete(source.tabId);
      return;
    }
    if (method === 'Page.screencastFrame') {
      const consumer = screencastConsumers.get(source.tabId);
      void Promise.resolve(consumer?.({
        data: String(params?.data || ''),
        metadata: params?.metadata || {},
        sessionId: Number(params?.sessionId || 0),
      }))
        .catch(() => {})
        .finally(() => {
          void sendCommand(source.tabId, 'Page.screencastFrameAck', {
            sessionId: Number(params?.sessionId || 0),
          }).catch(() => {});
        });
      return;
    }
    const session = networkSessions.get(source.tabId);
    if (!session) {
      return;
    }
    if (method === 'Network.requestWillBeSent') {
      touchNetworkActivity(session, { pendingDelta: 1 });
      const pending = buildPendingRequest(session, params || {});
      session.pendingByRequestId.set(String(params?.requestId || ''), pending);
      return;
    }
    if (method === 'Network.responseReceived') {
      const pending = upsertPendingRequest(source.tabId, params || {});
      pending.resourceType = normalizeResourceType(params?.type || pending.resourceType);
      pending.status = Number(params?.response?.status || pending.status || 0);
      pending.ok = pending.status >= 200 && pending.status < 400;
      pending.responseHeaders = normalizeHeaders(params?.response?.headers || {});
      pending.mimeType = extractMimeType(pending.responseHeaders, params?.response?.mimeType || '');
      return;
    }
    if (method === 'Network.loadingFinished') {
      touchNetworkActivity(session, { pendingDelta: -1 });
      void finalizeSuccessfulRequest(source.tabId, params?.requestId).catch(() => {});
      return;
    }
    if (method === 'Network.loadingFailed') {
      touchNetworkActivity(session, { pendingDelta: -1 });
      finalizeFailedRequest(source.tabId, params?.requestId, String(params?.errorText || 'Request failed.'));
    }
  });
}
