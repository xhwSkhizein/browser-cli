const attached = new Set();
const traceWaiters = new Map();
const screencastConsumers = new Map();

function isDebuggableUrl(url = '') {
  return url.startsWith('http://') || url.startsWith('https://') || url.startsWith('file://') || url === 'about:blank';
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
    }
  });
}
