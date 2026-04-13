const DEFAULT_HOST = '127.0.0.1'
const DEFAULT_PORT = 19825

const ACTION_SPECS = [
  {
    id: 'refresh-status',
    domId: 'refreshStatus',
    label: 'Refresh Status',
  },
  {
    id: 'reconnect-extension',
    domId: 'reconnectNow',
    label: 'Reconnect Extension',
  },
  {
    id: 'rebuild-workspace-binding',
    domId: 'rebuildWorkspace',
    label: 'Rebuild Workspace',
  },
]

const BADGE_TONES = {
  healthy: 'healthy',
  degraded: 'degraded',
  recovering: 'recovering',
  broken: 'broken',
  connected: 'healthy',
  connecting: 'recovering',
  probing: 'recovering',
  disconnected: 'idle',
}

function normalizePort(value) {
  const port = Number(value)
  if (!Number.isFinite(port) || port <= 0) {
    return DEFAULT_PORT
  }
  return port
}

function defaultSummaryReason(connectionStatus) {
  if (connectionStatus === 'connected') {
    return 'Waiting for Browser CLI runtime status.'
  }
  if (connectionStatus === 'connecting' || connectionStatus === 'probing') {
    return 'Extension is checking Browser CLI runtime availability.'
  }
  return 'Browser CLI runtime status is unavailable. Refresh status after the daemon reconnects.'
}

function defaultGuidance() {
  return ['Open Browser CLI to initialize runtime state.']
}

function normalizeDict(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value
}

export function buildPopupViewModel(status) {
  const presentation = normalizeDict(status?.presentation)
  const hasPresentation = Object.keys(presentation).length > 0
  const availableActions = Array.isArray(presentation.available_actions)
    ? presentation.available_actions
    : null
  const actionSet = new Set(availableActions || [])
  const connectionStatus = String(status?.connectionStatus || 'disconnected')
  const daemonHost = String(status?.daemonHost || DEFAULT_HOST)
  const daemonPort = normalizePort(status?.daemonPort)
  const guidance = Array.isArray(presentation.recovery_guidance) && presentation.recovery_guidance.length > 0
    ? presentation.recovery_guidance.map((item) => String(item))
    : defaultGuidance()
  const executionPath = normalizeDict(presentation.execution_path)
  const workspaceState = normalizeDict(presentation.workspace_state)
  const badgeLabel = String(presentation.overall_state || connectionStatus)

  return {
    badgeLabel,
    badgeTone: BADGE_TONES[badgeLabel] || 'idle',
    connectionStatus,
    daemonAddress: `${daemonHost}:${daemonPort}`,
    summaryReason: String(
      presentation.summary_reason || defaultSummaryReason(connectionStatus),
    ),
    executionPath: {
      active_driver: String(executionPath.active_driver || 'not-started'),
      pending_rebind:
        executionPath.pending_rebind && typeof executionPath.pending_rebind === 'object'
          ? executionPath.pending_rebind
          : null,
      safe_point_wait: Boolean(executionPath.safe_point_wait),
      last_transition:
        executionPath.last_transition && typeof executionPath.last_transition === 'object'
          ? executionPath.last_transition
          : null,
    },
    workspaceState: {
      window_id:
        workspaceState.window_id === null || workspaceState.window_id === undefined
          ? null
          : workspaceState.window_id,
      tab_count: Number(workspaceState.tab_count || 0),
      managed_tab_count: Number(workspaceState.managed_tab_count || 0),
      binding_state: String(workspaceState.binding_state || 'absent'),
      busy_tab_count: Number(workspaceState.busy_tab_count || 0),
    },
    guidance,
    lastError: String(status?.lastError || ''),
    lastConnectedAt: status?.lastConnectedAt || null,
    daemonHost,
    daemonPort,
    actions: ACTION_SPECS.map((action) => ({
      ...action,
      enabled:
        action.id === 'refresh-status'
          ? true
          : availableActions === null
            ? action.id === 'reconnect-extension' && !hasPresentation
            : actionSet.has(action.id),
    })),
  }
}
