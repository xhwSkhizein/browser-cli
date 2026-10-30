import {
  DEFAULT_DAEMON_HOST,
  DEFAULT_DAEMON_PORT,
  PROTOCOL_VERSION,
  REQUIRED_CAPABILITIES,
  SUPPORTED_CAPABILITIES,
  buildWsUrl,
} from './protocol.js';
import { locatorActionJs } from './page_runtime.js';
import { disposeNetworkSession, ensureNetworkSession, registerDebuggerListeners } from './debugger.js';
import { createArtifactHandlers } from './background/artifact_actions.js';
import { createDialogHandlers } from './background/dialog_actions.js';
import { createInputHandlers } from './background/input_actions.js';
import { createLocatorHandlers } from './background/locator_actions.js';
import { createObserveHandlers } from './background/observe_actions.js';
import { createPageHandlers } from './background/page_actions.js';
import { sendFramedMessage } from './background/response_framing.js';
import { createTraceHandlers } from './background/trace_actions.js';
import { createVideoHandlers } from './background/video_actions.js';
import { buildWorkspaceStatus, createWorkspaceHandlers } from './background/workspace.js';
import { createWorkspaceBinding } from './background/workspace_binding.js';
import {assertRuntimeApis, createRuntimeRecovery, queryRuntimeTabs} from './runtime_health.js';

const RECONNECT_ALARM = 'browser-cli-bridge-reconnect';
const INITIAL_RECONNECT_BACKOFF_MS = 1000;
const KEEPALIVE_INTERVAL_MS = 20 * 1000;
const MAX_RECONNECT_BACKOFF_MS = 30000;
const RUNTIME_REQUEST_TIMEOUT_MS = 1500;
let connecting;
let activeRequests = 0;
let checkingRuntime = false;
const runtimeRecovery = createRuntimeRecovery({canReload: () => activeRequests === 0
  && state.videoSessions.size === 0 && state.traceSessions.size === 0});

const state = {
  ws: null,
  keepAliveIntervalId: null,
  reconnectBackoffMs: INITIAL_RECONNECT_BACKOFF_MS,
  workspaceWindowId: null,
  managedTabIds: new Set(),
  pageIdByTabId: new Map(),
  traceSessions: new Map(),
  videoSessions: new Map(),
  runtimeState: {
    connectionStatus: 'disconnected',
    lastError: null,
    lastConnectedAt: null,
  },
};
const workspaceBinding = createWorkspaceBinding(state);

function requiredCapabilityGap() {
  const supported = new Set(SUPPORTED_CAPABILITIES);
  return REQUIRED_CAPABILITIES.filter((item) => !supported.has(item));
}

function setConnectionStatus(status, { error = undefined } = {}) {
  state.runtimeState.connectionStatus = status;
  if (error !== undefined) {
    state.runtimeState.lastError = error;
  }
  if (status === 'connected') {
    state.runtimeState.lastConnectedAt = Date.now();
    state.runtimeState.lastError = null;
  }
}

function buildHttpProbeUrl(host, port) {
  return `http://${host}:${port}/ext`;
}

function buildRuntimeStatusUrl(host, port) {
  return `http://${host}:${port}/ext/runtime-status`;
}

function buildWorkspaceRebuildUrl(host, port) {
  return `http://${host}:${port}/ext/workspace-rebuild`;
}

async function probeDaemon(host, port) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(buildHttpProbeUrl(host, port), {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    });
    return response.status === 426 || response.ok;
  } catch (_error) {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function fetchRuntimeJson(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), RUNTIME_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Runtime request failed: ${response.status}`);
    }
    const payload = await response.json();
    if (payload && payload.ok === false && payload.error) {
      throw new Error(String(payload.error));
    }
    return payload;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function fetchRuntimePresentation(config) {
  return await fetchRuntimeJson(buildRuntimeStatusUrl(config.host, config.port));
}

async function fetchWorkspaceRebuild(config) {
  return await fetchRuntimeJson(buildWorkspaceRebuildUrl(config.host, config.port));
}

function scheduleReconnect(delayMs = state.reconnectBackoffMs) {
  chrome.alarms.create(RECONNECT_ALARM, { when: Date.now() + Math.max(delayMs, 1000) });
}

function stopKeepAlive() {
  if (state.keepAliveIntervalId !== null) {
    clearInterval(state.keepAliveIntervalId);
    state.keepAliveIntervalId = null;
  }
}

function startKeepAlive(socket) {
  stopKeepAlive();
  state.keepAliveIntervalId = setInterval(async () => {
    if (state.ws !== socket) return;
    if (socket.readyState !== WebSocket.OPEN) {
      stopKeepAlive();
      return;
    }
    socket.send(JSON.stringify({ type: 'heartbeat' }));
    if (activeRequests === 0 && !checkingRuntime) {
      checkingRuntime = true;
      try {
        await queryRuntimeTabs();
      } catch (error) {
        if (state.ws === socket) {
          state.runtimeState.lastError = error.message;
          void runtimeRecovery.recover();
        }
      } finally {
        checkingRuntime = false;
      }
    }
  }, KEEPALIVE_INTERVAL_MS);
}

async function loadDaemonConfig() {
  const items = await chrome.storage.local.get(['daemonHost', 'daemonPort']);
  return {
    host: items.daemonHost || DEFAULT_DAEMON_HOST,
    port: items.daemonPort || DEFAULT_DAEMON_PORT,
  };
}

async function buildStatusSnapshot({ runtimeSnapshot = undefined } = {}) {
  const config = await loadDaemonConfig();
  let runtimeError = null;
  if (runtimeSnapshot === undefined) {
    try {
      runtimeSnapshot = await fetchRuntimePresentation(config);
    } catch (error) {
      runtimeSnapshot = null;
      runtimeError = error instanceof Error ? error.message : String(error);
    }
  }
  const missingCapabilities = Array.isArray(runtimeSnapshot?.extension?.missing_capabilities)
    ? runtimeSnapshot.extension.missing_capabilities
    : requiredCapabilityGap();
  return {
    connectionStatus: state.runtimeState.connectionStatus,
    daemonHost: config.host,
    daemonPort: Number(config.port),
    lastError: runtimeError || state.runtimeState.lastError,
    lastConnectedAt: state.runtimeState.lastConnectedAt,
    backendStatus: state.runtimeState.connectionStatus === 'connected'
      ? 'extension active'
      : 'waiting for daemon',
    workspaceWindowState:
      runtimeSnapshot?.workspace_window_state || await getWorkspaceWindowState(),
    capabilityComplete: runtimeSnapshot?.extension
      ? Boolean(runtimeSnapshot.extension.capability_complete)
      : missingCapabilities.length === 0,
    missingCapabilities,
    presentation: runtimeSnapshot?.presentation || null,
    runtimeSnapshot,
  };
}

async function rebuildWorkspaceBinding() {
  const config = await loadDaemonConfig();
  await fetchWorkspaceRebuild(config);
  return await buildStatusSnapshot();
}

function connect() {
  if (connecting) return connecting;
  connecting = connectOnce().catch((error) => {
    setConnectionStatus('disconnected', {error: String(error?.message || error)});
    if (error?.code === 'EXTENSION_RUNTIME_UNHEALTHY') void runtimeRecovery.recover();
    scheduleReconnect();
  }).finally(() => { connecting = undefined; });
  return connecting;
}

async function connectOnce() {
  if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const config = await loadDaemonConfig();
  await workspaceBinding.restore();
  setConnectionStatus('probing');
  const reachable = await probeDaemon(config.host, config.port);
  if (!reachable) {
    setConnectionStatus('disconnected');
    scheduleReconnect();
    state.reconnectBackoffMs = Math.min(state.reconnectBackoffMs * 2, MAX_RECONNECT_BACKOFF_MS);
    return;
  }
  setConnectionStatus('connecting');
  const socket = new WebSocket(buildWsUrl(config.host, config.port));
  state.ws = socket;
  socket.onopen = async () => {
    if (state.ws !== socket) return;
    state.reconnectBackoffMs = INITIAL_RECONNECT_BACKOFF_MS;
    setConnectionStatus('connected');
    startKeepAlive(socket);
    const platform = await chrome.runtime.getPlatformInfo().catch(() => ({ os: 'unknown' }));
    if (state.ws !== socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    let workspaceWindowState;
    try {
      workspaceWindowState = await getWorkspaceWindowState();
    } catch (error) {
      if (state.ws !== socket) return;
      state.runtimeState.lastError = String(error?.message || error);
      if (error?.code === 'EXTENSION_RUNTIME_UNHEALTHY') void runtimeRecovery.recover();
      socket.close();
      return;
    }
    if (state.ws !== socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({
      type: 'hello',
      protocol_version: PROTOCOL_VERSION,
      extension_version: chrome.runtime.getManifest().version,
      browser_name: 'Google Chrome',
      browser_version: platform.os || 'unknown',
      capabilities: SUPPORTED_CAPABILITIES,
      workspace_window_state: workspaceWindowState,
      extension_instance_id: chrome.runtime.id,
    }));
  };
  socket.onmessage = async (event) => {
    if (state.ws !== socket) return;
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (_error) {
      return;
    }
    if (payload.type !== 'request') {
      return;
    }
    const response = await handleRequest(payload);
    if (state.ws === socket && socket.readyState === WebSocket.OPEN) {
      sendFramedMessage(socket, response);
      if (response.error_code === 'EXTENSION_RUNTIME_UNHEALTHY'
        && payload.action !== 'workspace-status') void runtimeRecovery.recover();
    }
  };
  socket.onclose = () => {
    if (state.ws !== socket) return;
    stopKeepAlive();
    if (state.ws === socket) {
      state.ws = null;
    }
    setConnectionStatus('disconnected');
    scheduleReconnect();
    state.reconnectBackoffMs = Math.min(state.reconnectBackoffMs * 2, MAX_RECONNECT_BACKOFF_MS);
  };
  socket.onerror = () => {
    if (state.ws !== socket) return;
    state.runtimeState.lastError = `WebSocket handshake failed for ${config.host}:${config.port}`;
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
  };
}

async function reconnectNow() {
  state.reconnectBackoffMs = INITIAL_RECONNECT_BACKOFF_MS;
  stopKeepAlive();
  if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
    const current = state.ws;
    current.onclose = () => {
      if (state.ws !== current) return;
      stopKeepAlive();
      state.ws = null;
      setConnectionStatus('disconnected');
      void connect();
    };
    current.close();
    return;
  }
  await connect();
}

async function getWorkspaceWindowState() {
  await workspaceBinding.restore();
  if (state.workspaceWindowId === null) {
    return { window_id: null, tab_count: 0, managed_tab_count: 0, binding_state: 'absent' };
  }
  return await buildWorkspaceStatus(context);
}

async function ensureWorkspaceWindow(url = 'about:blank') {
  await workspaceBinding.restore();
  if (state.workspaceWindowId !== null) {
    try {
      await chrome.windows.get(state.workspaceWindowId);
      return state.workspaceWindowId;
    } catch (_error) {
      state.workspaceWindowId = null;
      state.managedTabIds.clear();
      state.pageIdByTabId.clear();
    }
  }
  const windowInfo = await chrome.windows.create({
    url,
    focused: true,
    width: 1280,
    height: 900,
    type: 'normal',
  });
  state.workspaceWindowId = windowInfo.id;
  for (const tab of windowInfo.tabs || []) {
    if (tab.id !== undefined) {
      state.managedTabIds.add(tab.id);
    }
  }
  await workspaceBinding.save();
  return state.workspaceWindowId;
}

async function executeExpression(tabId, expression) {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    func: async (code) => {
      // eslint-disable-next-line no-eval
      const evaluated = await eval(code);
      if (typeof evaluated === 'function') {
        return await evaluated();
      }
      return evaluated;
    },
    args: [expression],
  });
  return result ? result.result : null;
}

async function waitForLoad(tabId, timeoutSeconds = 30) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === 'complete') {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('Timed out waiting for tab load');
}

async function openTab(url) {
  if (state.workspaceWindowId === null) {
    await ensureWorkspaceWindow('about:blank');
    const tabs = await chrome.tabs.query({ windowId: state.workspaceWindowId });
    const activeTab = tabs.find((tab) => tab.active) || tabs[0];
    if (!activeTab || activeTab.id === undefined) {
      throw new Error('Workspace tab creation failed');
    }
    state.managedTabIds.add(activeTab.id);
    await ensureNetworkSession(activeTab.id);
    if (url) {
      await chrome.tabs.update(activeTab.id, { url });
      await waitForLoad(activeTab.id, 30);
    }
    return activeTab;
  }
  const tab = await chrome.tabs.create({
    windowId: state.workspaceWindowId,
    url: 'about:blank',
    active: true,
  });
  if (tab.id === undefined) {
    throw new Error('Workspace tab creation failed');
  }
  state.managedTabIds.add(tab.id);
  await workspaceBinding.save();
  await ensureNetworkSession(tab.id);
  if (url) {
    await chrome.tabs.update(tab.id, { url });
    await waitForLoad(tab.id, 30);
  }
  return tab;
}

async function getManagedTab(tabId) {
  if (!state.managedTabIds.has(tabId)) {
    throw new Error('Tab is not managed by Browser CLI');
  }
  return await chrome.tabs.get(tabId);
}

async function runLocatorAction(tabId, action, locator, payload = {}) {
  return await executeExpression(tabId, locatorActionJs(action, locator, payload));
}

function pageIdForTab(tabId) {
  return state.pageIdByTabId.get(tabId) || null;
}

async function untrackTab(tabId) {
  const wasManaged = state.managedTabIds.has(tabId);
  state.managedTabIds.delete(tabId);
  state.pageIdByTabId.delete(tabId);
  state.traceSessions.delete(tabId);
  state.videoSessions.delete(tabId);
  disposeNetworkSession(tabId);
  if (wasManaged) await workspaceBinding.save();
  else await workspaceBinding.flush();
}

const context = {
  state,
  connect,
  getManagedTab,
  getWorkspaceWindowState,
  ensureWorkspaceWindow,
  executeExpression,
  waitForLoad,
  openTab,
  runLocatorAction,
  pageIdForTab,
  untrackTab,
  saveWorkspaceBinding: () => workspaceBinding.save(),
};

const handlers = {
  ...createWorkspaceHandlers(context),
  ...createPageHandlers(context),
  ...createLocatorHandlers(context),
  ...createInputHandlers(context),
  ...createObserveHandlers(context),
  ...createArtifactHandlers(context),
  ...createDialogHandlers(context),
  ...createTraceHandlers(context),
  ...createVideoHandlers(context),
};

async function dispatch(action, payload, meta) {
  const handler = handlers[action];
  if (!handler) {
    throw new Error(`Unsupported action: ${action}`);
  }
  return await handler(payload, meta);
}

async function handleRequest(payload) {
  const id = String(payload.id || '');
  activeRequests += 1;
  try {
    await workspaceBinding.restore();
    if (payload.action === 'workspace-status') assertRuntimeApis();
    else await queryRuntimeTabs();
    const data = await dispatch(payload.action, payload.payload || {}, { requestId: id });
    return { type: 'response', id, ok: true, data };
  } catch (error) {
    return {
      type: 'response',
      id,
      ok: false,
      error_code: error?.code === 'EXTENSION_RUNTIME_UNHEALTHY'
        ? error.code : 'EXTENSION_ACTION_FAILED',
      error_message: error instanceof Error ? error.message : String(error),
    };
  } finally {
    activeRequests -= 1;
  }
}

chrome.runtime.onInstalled.addListener(() => {
  void connect();
});

chrome.runtime.onStartup.addListener(() => {
  void connect();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === RECONNECT_ALARM) {
    void connect();
    return;
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  void workspaceBinding.restore().then(() => untrackTab(tabId)).catch(error => {
    state.runtimeState.lastError = String(error?.message || error);
  });
});

chrome.windows.onRemoved.addListener((windowId) => {
  if (windowId === state.workspaceWindowId) {
    for (const tabId of Array.from(state.managedTabIds)) {
      disposeNetworkSession(tabId);
    }
    state.workspaceWindowId = null;
    state.managedTabIds.clear();
    state.pageIdByTabId.clear();
    state.traceSessions.clear();
    state.videoSessions.clear();
    void workspaceBinding.save().catch(error => {
      state.runtimeState.lastError = String(error?.message || error);
    });
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'offscreen-command') {
    return false;
  }
  if (message?.type === 'get-status' || message?.type === 'refresh-status') {
    void buildStatusSnapshot().then(sendResponse);
    return true;
  }
  if (message?.type === 'update-config') {
    void chrome.storage.local.set({
      daemonHost: message.host,
      daemonPort: Number(message.port),
    }).then(async () => sendResponse(await buildStatusSnapshot()));
    return true;
  }
  if (message?.type === 'reconnect-now') {
    void reconnectNow().then(async () => sendResponse(await buildStatusSnapshot()));
    return true;
  }
  if (message?.type === 'reload-extension') {
    void buildStatusSnapshot().then(async snapshot => {
      const accepted = await runtimeRecovery.recover({force: true});
      sendResponse({...snapshot, lastError: accepted
        ? 'Reloading the extension. Refresh status after it reconnects.'
        : 'Wait for the current browser operation to finish before reloading the extension.'});
    }).catch(error => sendResponse({lastError: String(error?.message || error)}));
    return true;
  }
  if (message?.type === 'rebuild-workspace') {
    void rebuildWorkspaceBinding().then(sendResponse).catch(error => {
      sendResponse({error: String(error?.message || error), connectionStatus: state.runtimeState.connectionStatus});
    });
    return true;
  }
  return false;
});

registerDebuggerListeners();
void connect();
