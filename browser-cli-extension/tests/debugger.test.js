import test from 'node:test'
import assert from 'node:assert/strict'

function installChromeStub({
  urls,
  attachImpl = async () => {},
}) {
  const sequence = Array.isArray(urls) && urls.length ? [...urls] : ['about:blank']
  let getCallCount = 0
  const attachCalls = []

  globalThis.chrome = {
    tabs: {
      async get(tabId) {
        const index = Math.min(getCallCount, sequence.length - 1)
        const url = sequence[index]
        getCallCount += 1
        return { id: tabId, url }
      },
    },
    debugger: {
      async attach(target, version) {
        attachCalls.push({ target, version })
        return await attachImpl(target, version)
      },
    },
  }

  return {
    attachCalls,
    getCallCount: () => getCallCount,
  }
}

async function loadDebuggerModule() {
  const cacheBust = `${Date.now()}-${Math.random()}`
  return await import(new URL(`../src/debugger.js?test=${cacheBust}`, import.meta.url))
}

test('ensureAttached waits for an initially blank tab URL before attaching', async (t) => {
  const chromeStub = installChromeStub({ urls: ['', '', 'about:blank'] })
  t.after(() => {
    delete globalThis.chrome
  })

  const { ensureAttached } = await loadDebuggerModule()
  await ensureAttached(17, {
    waitTimeoutMs: 25,
    pollIntervalMs: 0,
    retryCount: 1,
  })

  assert.equal(chromeStub.attachCalls.length, 1)
  assert.equal(chromeStub.attachCalls[0].target.tabId, 17)
  assert.equal(chromeStub.getCallCount(), 3)
})

test('ensureAttached retries a transient debugger attach failure', async (t) => {
  let attachAttempts = 0
  installChromeStub({
    urls: ['about:blank'],
    attachImpl: async () => {
      attachAttempts += 1
      if (attachAttempts === 1) {
        throw new Error('transient attach failure')
      }
    },
  })
  t.after(() => {
    delete globalThis.chrome
  })

  const { ensureAttached } = await loadDebuggerModule()
  await ensureAttached(23, {
    waitTimeoutMs: 0,
    pollIntervalMs: 0,
    retryCount: 2,
    retryDelayMs: 0,
  })

  assert.equal(attachAttempts, 2)
})

test('ensureAttached still rejects truly non-debuggable tabs', async (t) => {
  installChromeStub({ urls: ['', 'chrome://newtab/'] })
  t.after(() => {
    delete globalThis.chrome
  })

  const { ensureAttached } = await loadDebuggerModule()
  await assert.rejects(
    ensureAttached(29, {
      waitTimeoutMs: 1,
      pollIntervalMs: 0,
      retryCount: 1,
    }),
    /Tab 29 is not debuggable: chrome:\/\/newtab\//,
  )
})
