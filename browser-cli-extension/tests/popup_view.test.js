import test from 'node:test'
import assert from 'node:assert/strict'

import { buildPopupViewModel } from '../src/popup_view.js'

test('buildPopupViewModel exposes runtime summary and actions', () => {
  const view = buildPopupViewModel({
    daemonHost: '127.0.0.1',
    daemonPort: 19825,
    connectionStatus: 'connected',
    presentation: {
      overall_state: 'recovering',
      summary_reason:
        'Extension disconnected; Browser CLI will switch to Playwright at the next safe point.',
      execution_path: {
        active_driver: 'extension',
        pending_rebind: {
          target: 'playwright',
          reason: 'extension-disconnected-waiting-command',
        },
        safe_point_wait: true,
        last_transition: null,
      },
      workspace_state: {
        window_id: 91,
        tab_count: 1,
        managed_tab_count: 1,
        binding_state: 'tracked',
        busy_tab_count: 0,
      },
      recovery_guidance: [
        'Agent can continue; Browser CLI is waiting for a safe-point rebind.',
      ],
      available_actions: ['refresh-status', 'reconnect-extension'],
    },
  })

  assert.equal(view.badgeLabel, 'recovering')
  assert.equal(
    view.summaryReason,
    'Extension disconnected; Browser CLI will switch to Playwright at the next safe point.',
  )
  assert.deepEqual(view.actions, [
    {
      id: 'refresh-status',
      domId: 'refreshStatus',
      label: 'Refresh Status',
      enabled: true,
    },
    {
      id: 'reconnect-extension',
      domId: 'reconnectNow',
      label: 'Reconnect Extension',
      enabled: true,
    },
    {
      id: 'rebuild-workspace-binding',
      domId: 'rebuildWorkspace',
      label: 'Rebuild Workspace',
      enabled: false,
    },
  ])
})

test('buildPopupViewModel falls back cleanly when runtime presentation is unavailable', () => {
  const view = buildPopupViewModel({
    daemonHost: '127.0.0.1',
    daemonPort: 19825,
    connectionStatus: 'disconnected',
    presentation: null,
  })

  assert.equal(view.badgeLabel, 'disconnected')
  assert.equal(
    view.summaryReason,
    'Browser CLI runtime status is unavailable. Refresh status after the daemon reconnects.',
  )
  assert.deepEqual(
    view.guidance,
    ['Open Browser CLI to initialize runtime state.'],
  )
  assert.deepEqual(view.actions, [
    {
      id: 'refresh-status',
      domId: 'refreshStatus',
      label: 'Refresh Status',
      enabled: true,
    },
    {
      id: 'reconnect-extension',
      domId: 'reconnectNow',
      label: 'Reconnect Extension',
      enabled: true,
    },
    {
      id: 'rebuild-workspace-binding',
      domId: 'rebuildWorkspace',
      label: 'Rebuild Workspace',
      enabled: false,
    },
  ])
})
