import { buildPopupViewModel } from './popup_view.js'

const els = {
  badge: document.getElementById('connection-badge'),
  connectionStatus: document.getElementById('connection-status'),
  daemonAddress: document.getElementById('daemon-address'),
  summaryReason: document.getElementById('summary-reason'),
  executionDriver: document.getElementById('execution-driver'),
  executionRebind: document.getElementById('execution-rebind'),
  lastTransition: document.getElementById('last-transition'),
  workspaceBinding: document.getElementById('workspace-binding'),
  workspaceWindow: document.getElementById('workspace-window'),
  workspaceTabs: document.getElementById('workspace-tabs'),
  workspaceManagedTabs: document.getElementById('workspace-managed-tabs'),
  workspaceBusyTabs: document.getElementById('workspace-busy-tabs'),
  recoveryGuidance: document.getElementById('recovery-guidance'),
  lastConnected: document.getElementById('last-connected'),
  daemonHost: document.getElementById('daemon-host'),
  daemonPort: document.getElementById('daemon-port'),
  lastError: document.getElementById('last-error'),
  saveConfig: document.getElementById('save-config'),
  refreshStatus: document.getElementById('refresh-status'),
  reconnectNow: document.getElementById('reconnect-now'),
  rebuildWorkspace: document.getElementById('rebuild-workspace'),
}

const DEFAULT_HOST = '127.0.0.1'
const DEFAULT_PORT = 19825
const AUTO_REFRESH_MS = 1000

let refreshTimer = null
let busy = false
let lastStatus = null
let currentView = null

function formatTimestamp(value) {
  if (!value) return 'Never'
  try {
    return new Date(value).toLocaleString()
  } catch (_error) {
    return 'Unknown'
  }
}

function formatPendingRebind(pendingRebind) {
  if (!pendingRebind) {
    return 'none'
  }
  const target = pendingRebind.target || 'unknown'
  const reason = pendingRebind.reason || 'pending'
  return `${target} (${reason})`
}

function formatTransition(transition) {
  if (!transition) {
    return 'none'
  }
  const from = transition.driver_changed_from || 'unknown'
  const to = transition.driver_changed_to || 'unknown'
  const reason = transition.driver_reason || 'state-reset'
  return `${from} -> ${to} (${reason})`
}

function formatWorkspaceWindow(state) {
  const windowId = state?.window_id
  if (windowId == null) {
    return 'none'
  }
  return `window ${windowId}`
}

function applyActionState() {
  els.saveConfig.disabled = busy
  if (!currentView) {
    els.refreshStatus.disabled = busy
    els.reconnectNow.disabled = busy
    els.rebuildWorkspace.disabled = busy
    return
  }
  for (const action of currentView.actions) {
    els[action.domId].disabled = busy || !action.enabled
  }
}

async function sendMessage(message) {
  return await chrome.runtime.sendMessage(message)
}

function renderStatus(status) {
  lastStatus = status
  currentView = buildPopupViewModel(status)
  els.badge.textContent = currentView.badgeLabel
  els.badge.className = `badge badge-${currentView.badgeTone}`
  els.connectionStatus.textContent = currentView.connectionStatus
  els.daemonAddress.textContent = currentView.daemonAddress
  els.summaryReason.textContent = currentView.summaryReason
  els.executionDriver.textContent = currentView.executionPath.active_driver
  els.executionRebind.textContent = formatPendingRebind(currentView.executionPath.pending_rebind)
  els.lastTransition.textContent = formatTransition(currentView.executionPath.last_transition)
  els.workspaceBinding.textContent = currentView.workspaceState.binding_state
  els.workspaceWindow.textContent = formatWorkspaceWindow(currentView.workspaceState)
  els.workspaceTabs.textContent = String(currentView.workspaceState.tab_count)
  els.workspaceManagedTabs.textContent = String(currentView.workspaceState.managed_tab_count)
  els.workspaceBusyTabs.textContent = String(currentView.workspaceState.busy_tab_count)
  els.lastConnected.textContent = formatTimestamp(currentView.lastConnectedAt)
  els.recoveryGuidance.replaceChildren(
    ...currentView.guidance.map((text) => {
      const item = document.createElement('li')
      item.textContent = text
      return item
    }),
  )

  if (document.activeElement !== els.daemonHost) {
    els.daemonHost.value = currentView.daemonHost
  }
  if (document.activeElement !== els.daemonPort) {
    els.daemonPort.value = String(currentView.daemonPort)
  }

  if (currentView.lastError) {
    els.lastError.textContent = currentView.lastError
    els.lastError.classList.remove('empty')
  } else {
    els.lastError.textContent = 'No recent errors'
    els.lastError.classList.add('empty')
  }

  applyActionState()
}

function setBusy(disabled) {
  busy = disabled
  applyActionState()
}

function buildFallbackStatus(error) {
  const message = error instanceof Error ? error.message : String(error)
  return {
    ...(lastStatus || {}),
    connectionStatus: lastStatus?.connectionStatus || 'disconnected',
    daemonHost: els.daemonHost.value || DEFAULT_HOST,
    daemonPort: Number(els.daemonPort.value || DEFAULT_PORT),
    presentation: lastStatus?.presentation || null,
    lastError: message,
  }
}

async function refreshStatus() {
  try {
    renderStatus(await sendMessage({ type: 'refresh-status' }))
  } catch (error) {
    renderStatus(buildFallbackStatus(error))
  }
}

async function saveConfig() {
  const host = els.daemonHost.value.trim() || DEFAULT_HOST
  const port = Number(els.daemonPort.value || DEFAULT_PORT)
  setBusy(true)
  try {
    renderStatus(await sendMessage({ type: 'update-config', host, port }))
  } catch (error) {
    renderStatus(buildFallbackStatus(error))
  } finally {
    setBusy(false)
  }
}

async function reconnectNow() {
  setBusy(true)
  try {
    renderStatus(await sendMessage({ type: 'reconnect-now' }))
  } catch (error) {
    renderStatus(buildFallbackStatus(error))
  } finally {
    setBusy(false)
  }
}

async function rebuildWorkspace() {
  setBusy(true)
  try {
    renderStatus(await sendMessage({ type: 'rebuild-workspace' }))
  } catch (error) {
    renderStatus(buildFallbackStatus(error))
  } finally {
    setBusy(false)
  }
}

els.saveConfig.addEventListener('click', () => {
  void saveConfig()
})

els.refreshStatus.addEventListener('click', () => {
  void refreshStatus()
})

els.reconnectNow.addEventListener('click', () => {
  void reconnectNow()
})

els.rebuildWorkspace.addEventListener('click', () => {
  void rebuildWorkspace()
})

document.addEventListener('DOMContentLoaded', () => {
  void refreshStatus()
  refreshTimer = window.setInterval(() => {
    void refreshStatus()
  }, AUTO_REFRESH_MS)
})

window.addEventListener('unload', () => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
  }
})
