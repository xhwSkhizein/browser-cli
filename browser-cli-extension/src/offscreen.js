const videoSessions = new Map();

function preferredMimeType() {
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ];
  for (const candidate of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }
  return 'video/webm';
}

function bytesToBase64(bytes) {
  let text = '';
  for (let index = 0; index < bytes.length; index += 0x8000) {
    text += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(text);
}

function decodeFrameBytes(dataBase64) {
  return Uint8Array.from(atob(String(dataBase64 || '')), (char) => char.charCodeAt(0));
}

async function decodeFrameBitmap(dataBase64) {
  const bytes = decodeFrameBytes(dataBase64);
  const blob = new Blob([bytes], { type: 'image/jpeg' });
  return await createImageBitmap(blob);
}

function createBlankCanvas(width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const ctx = canvas.getContext('2d', { alpha: false });
  ctx.fillStyle = '#111111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  return { canvas, ctx };
}

function cleanupBitmap(bitmap) {
  try {
    bitmap?.close?.();
  } catch (_error) {
    // Ignore bitmap cleanup failures.
  }
}

function startRenderLoop(session) {
  const frameIntervalMs = Math.max(40, Math.round(1000 / Math.max(1, session.fps || 8)));
  session.timerId = setInterval(() => {
    const { ctx, canvas } = session;
    if (!ctx || !canvas) {
      return;
    }
    if (session.latestBitmap) {
      cleanupBitmap(session.renderBitmap);
      session.renderBitmap = session.latestBitmap;
      session.latestBitmap = null;
    }
    ctx.fillStyle = '#111111';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (session.renderBitmap) {
      ctx.drawImage(session.renderBitmap, 0, 0, canvas.width, canvas.height);
    }
  }, frameIntervalMs);
}

function ensureRecorder(session, frameWidth, frameHeight) {
  if (session.recorder) {
    return;
  }
  const width = Number(session.requestedWidth || frameWidth || 1280);
  const height = Number(session.requestedHeight || frameHeight || 720);
  const { canvas, ctx } = createBlankCanvas(width, height);
  const stream = canvas.captureStream(Math.max(1, session.fps || 8));
  const mimeType = preferredMimeType();
  const recorder = new MediaRecorder(stream, { mimeType });
  recorder.addEventListener('dataavailable', (event) => {
    if (event.data && event.data.size > 0) {
      session.chunks.push(event.data);
    }
  });
  recorder.start(250);
  session.canvas = canvas;
  session.ctx = ctx;
  session.stream = stream;
  session.recorder = recorder;
  session.mimeType = mimeType;
  startRenderLoop(session);
}

async function startVideo(tabId, { fps = 8, width = null, height = null } = {}) {
  if (videoSessions.get(tabId)?.recording) {
    throw new Error('Video recording is already active.');
  }
  videoSessions.set(tabId, {
    requestedWidth: width,
    requestedHeight: height,
    fps: Number(fps || 8),
    chunks: [],
    recording: true,
    latestBitmap: null,
    renderBitmap: null,
    recorder: null,
    stream: null,
    canvas: null,
    ctx: null,
    timerId: null,
    dataBase64: null,
    sizeBytes: 0,
    mimeType: preferredMimeType(),
  });
  return { started: true, mime_type: preferredMimeType(), fps: Number(fps || 8) };
}

async function pushFrame(tabId, dataBase64, metadata = {}) {
  const session = videoSessions.get(tabId);
  if (!session?.recording) {
    throw new Error('No active video recording.');
  }
  const bitmap = await decodeFrameBitmap(dataBase64);
  ensureRecorder(
    session,
    Number(metadata.deviceWidth || metadata.width || bitmap.width || 0),
    Number(metadata.deviceHeight || metadata.height || bitmap.height || 0),
  );
  cleanupBitmap(session.latestBitmap);
  session.latestBitmap = bitmap;
  return { accepted: true };
}

async function stopVideo(tabId) {
  const session = videoSessions.get(tabId);
  if (!session?.recording) {
    throw new Error('No active video recording.');
  }
  session.recording = false;
  if (!session.recorder) {
    ensureRecorder(session, session.requestedWidth || 2, session.requestedHeight || 2);
  }
  if (session.latestBitmap) {
    cleanupBitmap(session.renderBitmap);
    session.renderBitmap = session.latestBitmap;
    session.latestBitmap = null;
  }
  if (session.ctx && session.canvas && session.renderBitmap) {
    session.ctx.drawImage(session.renderBitmap, 0, 0, session.canvas.width, session.canvas.height);
  }
  if (session.timerId) {
    clearInterval(session.timerId);
    session.timerId = null;
  }
  const stopped = await new Promise((resolve, reject) => {
    session.recorder.addEventListener('stop', () => resolve(true), { once: true });
    session.recorder.addEventListener(
      'error',
      (event) => reject(event.error || new Error('MediaRecorder stop failed.')),
      { once: true },
    );
    session.recorder.stop();
  });
  if (!stopped) {
    throw new Error('Video recorder did not stop cleanly.');
  }
  const blob = new Blob(session.chunks, { type: session.mimeType || 'video/webm' });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  session.dataBase64 = bytesToBase64(bytes);
  session.sizeBytes = bytes.length;
  for (const track of session.stream?.getTracks?.() || []) {
    try {
      track.stop();
    } catch (_error) {
      // Ignore stopped tracks.
    }
  }
  return {
    data_base64: session.dataBase64,
    size_bytes: session.sizeBytes,
    mime_type: session.mimeType || 'video/webm',
  };
}

async function cleanupVideo(tabId) {
  const session = videoSessions.get(tabId);
  if (!session) {
    return { removed: false };
  }
  if (session.timerId) {
    clearInterval(session.timerId);
  }
  try {
    session.recorder?.stop?.();
  } catch (_error) {
    // Ignore already-stopped recorders.
  }
  for (const track of session.stream?.getTracks?.() || []) {
    try {
      track.stop();
    } catch (_error) {
      // Ignore stopped tracks.
    }
  }
  cleanupBitmap(session.latestBitmap);
  cleanupBitmap(session.renderBitmap);
  videoSessions.delete(tabId);
  return { removed: true };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== 'offscreen-command') {
    return false;
  }
  const tabId = Number(message.payload?.tabId || 0);
  const command = String(message.command || '');
  void (async () => {
    try {
      let data;
      if (command === 'video-start') {
        data = await startVideo(tabId, {
          fps: message.payload?.fps,
          width: message.payload?.width ?? null,
          height: message.payload?.height ?? null,
        });
      } else if (command === 'video-frame') {
        data = await pushFrame(tabId, String(message.payload?.dataBase64 || ''), message.payload?.metadata || {});
      } else if (command === 'video-stop') {
        data = await stopVideo(tabId);
      } else if (command === 'video-cleanup') {
        data = await cleanupVideo(tabId);
      } else {
        throw new Error(`Unsupported offscreen command: ${command}`);
      }
      sendResponse({ ok: true, data });
    } catch (error) {
      sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  })();
  return true;
});
