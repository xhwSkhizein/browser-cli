import {
  startScreencast,
  stopScreencast,
} from '../debugger.js';
import {
  buildArtifactDescriptor,
  emitBase64Artifact,
} from './artifact_actions.js';

const DEFAULT_VIDEO_FPS = 8;

async function ensureOffscreenDocument() {
  if (!chrome.offscreen) {
    throw new Error('Chrome offscreen documents are not available.');
  }
  const hasDocument = typeof chrome.offscreen.hasDocument === 'function'
    ? await chrome.offscreen.hasDocument()
    : false;
  if (hasDocument) {
    return;
  }
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: [chrome.offscreen.Reason.DISPLAY_MEDIA, chrome.offscreen.Reason.BLOBS],
    justification: 'Encode Browser CLI screencast frames into deferred video artifacts.',
  });
}

async function sendOffscreenCommand(command, payload) {
  const response = await chrome.runtime.sendMessage({
    type: 'offscreen-command',
    command,
    payload,
  });
  if (!response?.ok) {
    throw new Error(response?.error || `Offscreen command failed: ${command}`);
  }
  return response.data || {};
}

function defaultVideoFilename(context, tabId) {
  return `${context.pageIdForTab(tabId) || 'page'}.webm`;
}

async function ensureStoppedRecording(context, tabId) {
  const session = context.state.videoSessions.get(tabId);
  if (!session) {
    return null;
  }
  if (!session.recording) {
    return session;
  }
  try {
    await stopScreencast(tabId);
  } catch (_error) {
    // Missing tabs during shutdown shouldn't block workspace teardown.
  }
  let stopped = {};
  try {
    stopped = await sendOffscreenCommand('video-stop', { tabId });
  } catch (_error) {
    stopped = {};
  }
  const updated = {
    ...session,
    recording: false,
    pendingBase64: String(stopped.data_base64 || session.pendingBase64 || ''),
    mimeType: String(stopped.mime_type || 'video/webm'),
    sizeBytes: Number(stopped.size_bytes || 0),
  };
  context.state.videoSessions.set(tabId, updated);
  return updated;
}

export async function flushPendingVideoArtifactsForTab(context, requestId, tabId) {
  const session = await ensureStoppedRecording(context, tabId);
  if (!session || !session.pendingBase64) {
    context.state.videoSessions.delete(tabId);
    return [];
  }
  const descriptor = buildArtifactDescriptor({
    artifactKind: 'video',
    mimeType: session.mimeType || 'video/webm',
    filename: defaultVideoFilename(context, tabId),
    pageId: context.pageIdForTab(tabId),
    metadata: {
      requested_path: session.requestedPath || null,
      width: session.width ?? null,
      height: session.height ?? null,
      fps: session.fps ?? DEFAULT_VIDEO_FPS,
      deferred: true,
      frame_count: session.frameCount ?? 0,
    },
  });
  await emitBase64Artifact(context, requestId, descriptor, session.pendingBase64);
  context.state.videoSessions.delete(tabId);
  void sendOffscreenCommand('video-cleanup', { tabId }).catch(() => {});
  return [descriptor];
}

export async function flushAllPendingVideoArtifacts(context, requestId) {
  const artifacts = [];
  for (const tabId of Array.from(context.state.videoSessions.keys())) {
    let emitted = [];
    try {
      emitted = await flushPendingVideoArtifactsForTab(context, requestId, tabId);
    } catch (_error) {
      context.state.videoSessions.delete(tabId);
      void sendOffscreenCommand('video-cleanup', { tabId }).catch(() => {});
      emitted = [];
    }
    artifacts.push(...emitted);
  }
  return artifacts;
}

function buildScreencastConsumer(context, tabId) {
  return async ({ data, metadata }) => {
    const session = context.state.videoSessions.get(tabId);
    if (!session || !session.recording) {
      return;
    }
    await sendOffscreenCommand('video-frame', {
      tabId,
      dataBase64: data,
      metadata,
    });
    session.frameCount = Number(session.frameCount || 0) + 1;
    context.state.videoSessions.set(tabId, session);
  };
}

export function createVideoHandlers(context) {
  return {
    async 'video-start'(payload) {
      await context.getManagedTab(payload.tab_id);
      if (context.state.videoSessions.get(payload.tab_id)?.recording) {
        throw new Error('Video recording is already active. Stop the current recording first.');
      }
      await ensureOffscreenDocument();
      const fps = Number(payload.fps || DEFAULT_VIDEO_FPS);
      await sendOffscreenCommand('video-start', {
        tabId: payload.tab_id,
        fps,
        width: payload.width ?? null,
        height: payload.height ?? null,
      });
      await startScreencast(payload.tab_id, {
        format: 'jpeg',
        quality: 70,
        everyNthFrame: 1,
        maxWidth: payload.width ?? undefined,
        maxHeight: payload.height ?? undefined,
        onFrame: buildScreencastConsumer(context, payload.tab_id),
      });
      context.state.videoSessions.set(payload.tab_id, {
        pageId: context.pageIdForTab(payload.tab_id),
        requestedPath: null,
        recording: true,
        pendingBase64: null,
        width: payload.width ?? null,
        height: payload.height ?? null,
        fps,
        frameCount: 0,
        mimeType: 'video/webm',
        startedAt: Date.now(),
      });
      return {
        recording: true,
        width: payload.width ?? null,
        height: payload.height ?? null,
      };
    },
    async 'video-stop'(payload) {
      await context.getManagedTab(payload.tab_id);
      const existing = context.state.videoSessions.get(payload.tab_id);
      if (!existing || (!existing.recording && !existing.pendingBase64)) {
        throw new Error('No active video recording. Use video-start first.');
      }
      const session = await ensureStoppedRecording(context, payload.tab_id);
      const updated = {
        ...session,
        requestedPath: payload.path || session?.requestedPath || null,
      };
      context.state.videoSessions.set(payload.tab_id, updated);
      return {
        recording: false,
        path: updated.requestedPath,
        deferred: true,
      };
    },
  };
}
