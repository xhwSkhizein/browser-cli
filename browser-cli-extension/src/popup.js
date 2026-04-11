const els = {
  badge: document.getElementById('connection-badge'),
  connectionStatus: document.getElementById('connection-status'),
  daemonAddress: document.getElementById('daemon-address'),
  backendStatus: document.getElementById('backend-status'),
  missingCapabilities: document.getElementById('missing-capabilities'),
  workspaceStatus: document.getElementById('workspace-status'),
  lastConnected: document.getElementById('last-connected'),
  daemonHost: document.getElementById('daemon-host'),
  daemonPort: document.getElementById('daemon-port'),
  lastError: document.getElementById('last-error'),
  saveConfig: document.getElementById('save-config'),
  reconnectNow: document.getElementById('reconnect-now'),
};

let refreshTimer = null;

function formatTimestamp(value) {
  if (!value) return 'Never';
  try {
    return new Date(value).toLocaleString();
  } catch (_error) {
    return 'Unknown';
  }
}

function formatWorkspace(state) {
  const windowId = state?.window_id;
  const tabCount = Number(state?.tab_count || 0);
  if (windowId == null) {
    return 'No workspace window';
  }
  return `Window ${windowId}, ${tabCount} tab${tabCount === 1 ? '' : 's'}`;
}

function setBusy(disabled) {
  els.saveConfig.disabled = disabled;
  els.reconnectNow.disabled = disabled;
}

async function sendMessage(message) {
  return await chrome.runtime.sendMessage(message);
}

function renderStatus(status) {
  const connectionStatus = status.connectionStatus || 'disconnected';
  els.badge.textContent = connectionStatus;
  els.badge.className = `badge badge-${connectionStatus}`;
  els.connectionStatus.textContent = connectionStatus;
  els.daemonAddress.textContent = `${status.daemonHost}:${status.daemonPort}`;
  els.backendStatus.textContent = status.backendStatus || 'waiting for daemon';
  els.missingCapabilities.textContent = (status.missingCapabilities || []).length
    ? status.missingCapabilities.join(', ')
    : 'none';
  els.workspaceStatus.textContent = formatWorkspace(status.workspaceWindowState);
  els.lastConnected.textContent = formatTimestamp(status.lastConnectedAt);

  if (document.activeElement !== els.daemonHost) {
    els.daemonHost.value = status.daemonHost || '';
  }
  if (document.activeElement !== els.daemonPort) {
    els.daemonPort.value = String(status.daemonPort || '');
  }

  if (status.lastError) {
    els.lastError.textContent = status.lastError;
    els.lastError.classList.remove('empty');
  } else {
    els.lastError.textContent = 'No recent errors';
    els.lastError.classList.add('empty');
  }
}

async function refreshStatus() {
  try {
    renderStatus(await sendMessage({ type: 'get-status' }));
  } catch (error) {
    renderStatus({
      connectionStatus: 'disconnected',
      daemonHost: els.daemonHost.value || '127.0.0.1',
      daemonPort: Number(els.daemonPort.value || 19825),
      backendStatus: 'waiting for daemon',
      missingCapabilities: [],
      workspaceWindowState: null,
      lastConnectedAt: null,
      lastError: error instanceof Error ? error.message : String(error),
    });
  }
}

async function saveConfig() {
  const host = els.daemonHost.value.trim() || '127.0.0.1';
  const port = Number(els.daemonPort.value || 19825);
  setBusy(true);
  try {
    renderStatus(await sendMessage({ type: 'update-config', host, port }));
  } finally {
    setBusy(false);
  }
}

async function reconnectNow() {
  setBusy(true);
  try {
    renderStatus(await sendMessage({ type: 'reconnect-now' }));
  } finally {
    setBusy(false);
  }
}

els.saveConfig.addEventListener('click', () => {
  void saveConfig();
});

els.reconnectNow.addEventListener('click', () => {
  void reconnectNow();
});

document.addEventListener('DOMContentLoaded', () => {
  void refreshStatus();
  refreshTimer = window.setInterval(() => {
    void refreshStatus();
  }, 1000);
});

window.addEventListener('unload', () => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
  }
});
