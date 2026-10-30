const RELOAD_KEY = 'browserCliLastRuntimeReload';
const RELOAD_COOLDOWN_MS = 5 * 60 * 1000;
const REQUIRED_APIS = [
  'tabs.query', 'tabs.get', 'tabs.create', 'tabs.update', 'tabs.remove',
  'windows.get', 'windows.create', 'windows.remove',
  'scripting.executeScript', 'debugger.attach', 'debugger.sendCommand',
];

export class ExtensionRuntimeError extends Error {
  constructor(message) {
    super(`Chrome extension runtime is unusable: ${message}. Reload the Browser CLI extension if automatic recovery does not restore it.`);
    this.code = 'EXTENSION_RUNTIME_UNHEALTHY';
  }
}

export function assertRuntimeApis() {
  for (const path of REQUIRED_APIS) {
    const [namespace, method] = path.split('.');
    if (typeof globalThis.chrome?.[namespace]?.[method] !== 'function') {
      throw new ExtensionRuntimeError(`${path} is unavailable`);
    }
  }
}

export async function queryRuntimeTabs(query = {windowType: 'normal'}) {
  assertRuntimeApis();
  let timeoutId;
  try {
    const tabs = await Promise.race([
      chrome.tabs.query(query),
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error('tabs.query probe timed out')), 1500);
      }),
    ]);
    if (!Array.isArray(tabs)) throw new Error('tabs.query returned an invalid result');
    return tabs;
  } catch (error) {
    // A removed owned window loses its binding; it does not invalidate Chrome APIs.
    if (query.windowId !== undefined && /No window with id/i.test(String(error?.message))) {
      throw error;
    }
    throw new ExtensionRuntimeError(error instanceof Error ? error.message : String(error));
  } finally {
    clearTimeout(timeoutId);
  }
}

// Persist the limit across service-worker and extension reloads. Never retry an action.
export function createRuntimeRecovery({canReload, now = Date.now, schedule = setTimeout}) {
  let pending;
  return {
    recover({force = false} = {}) {
      if (pending) return pending;
      pending = (async () => {
        const api = globalThis.chrome;
        if (!canReload() || typeof api?.runtime?.reload !== 'function'
          || !api?.storage?.local?.get || !api?.storage?.local?.set) return false;
        const stored = await api.storage.local.get(RELOAD_KEY);
        const previous = Number(stored[RELOAD_KEY] || 0);
        const timestamp = now();
        if (!force && previous && timestamp >= previous
          && timestamp - previous < RELOAD_COOLDOWN_MS) return false;
        if (!canReload()) return false;
        await api.storage.local.set({[RELOAD_KEY]: timestamp});
        schedule(() => {
          if (canReload()) api.runtime.reload();
        }, 100);
        return true;
      })().catch(() => false).finally(() => { pending = undefined; });
      return pending;
    },
  };
}
