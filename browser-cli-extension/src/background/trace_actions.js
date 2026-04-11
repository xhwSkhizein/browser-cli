import {
  getConsoleMessagesJs,
  installConsoleCaptureJs,
} from '../page_runtime.js';
import {
  startTraceNetworkCapture,
  startTracing,
  stopTraceNetworkCapture,
  stopTracing,
} from '../debugger.js';
import {
  buildArtifactDescriptor,
  buildStoredZip,
  emitArtifact,
  jsonBytes,
} from './artifact_actions.js';

const textEncoder = new TextEncoder();

function traceSessionFor(context, tabId) {
  const session = context.state.traceSessions.get(tabId);
  if (!session) {
    throw new Error('No active tracing session. Start tracing first.');
  }
  return session;
}

function filterEventsSince(items, startedAt) {
  return Array.from(items || []).filter((item) => {
    if (item?.ts) {
      return Number(item.ts || 0) >= startedAt;
    }
    return Number(item?.ended_at || item?.started_at || 0) * 1000 >= startedAt;
  });
}

export function createTraceHandlers(context) {
  return {
    async 'trace-start'(payload) {
      const tab = await context.getManagedTab(payload.tab_id);
      if (context.state.traceSessions.has(payload.tab_id)) {
        throw new Error('Tracing is already active. Stop the current trace first.');
      }
      const consoleState = await context.executeExpression(payload.tab_id, installConsoleCaptureJs());
      await startTraceNetworkCapture(payload.tab_id, 'trace');
      await startTracing(payload.tab_id, {
        screenshots: !!payload.screenshots,
        snapshots: !!payload.snapshots,
        sources: !!payload.sources,
      });
      context.state.traceSessions.set(payload.tab_id, {
        pageId: context.pageIdForTab(payload.tab_id),
        startedAt: Date.now(),
        startedUrl: tab.url || '',
        options: {
          screenshots: !!payload.screenshots,
          snapshots: !!payload.snapshots,
          sources: !!payload.sources,
        },
        markers: [],
        consoleAlreadyInstalled: !!consoleState?.already_installed,
        networkAlreadyInstalled: false,
      });
      return {
        tracing: true,
        screenshots: !!payload.screenshots,
        snapshots: !!payload.snapshots,
        sources: !!payload.sources,
      };
    },
    async 'trace-chunk'(payload) {
      const session = traceSessionFor(context, payload.tab_id);
      const tab = await context.getManagedTab(payload.tab_id);
      session.markers.push({
        title: payload.title || null,
        timestamp: Date.now(),
        url: tab.url || '',
        page_id: context.pageIdForTab(payload.tab_id),
      });
      return { chunk_started: true, title: payload.title || null };
    },
    async 'trace-stop'(payload, meta) {
      const session = traceSessionFor(context, payload.tab_id);
      const tab = await context.getManagedTab(payload.tab_id);
      const traceText = await stopTracing(payload.tab_id);
      const consolePayload = await context.executeExpression(
        payload.tab_id,
        getConsoleMessagesJs({ clear: false }),
      );
      const networkRecords = await stopTraceNetworkCapture(payload.tab_id, 'trace');
      context.state.traceSessions.delete(payload.tab_id);

      const metadata = {
        driver: 'extension',
        page_id: context.pageIdForTab(payload.tab_id),
        current_url: tab.url || '',
        started_url: session.startedUrl,
        started_at: session.startedAt,
        stopped_at: Date.now(),
        options: session.options,
        chunk_markers: session.markers,
        console_already_installed: session.consoleAlreadyInstalled,
        network_already_installed: session.networkAlreadyInstalled,
        resources_available: false,
      };
      const traceBytes = textEncoder.encode(String(traceText || ''));
      const networkBytes = jsonBytes({
        records: filterEventsSince(networkRecords || [], session.startedAt),
      });
      const consoleBytes = jsonBytes({
        messages: filterEventsSince(consolePayload?.messages || [], session.startedAt),
      });
      const zipBytes = buildStoredZip([
        { name: 'trace.trace', bytes: traceBytes },
        { name: 'trace.network', bytes: networkBytes },
        { name: 'trace.console', bytes: consoleBytes },
        { name: 'trace.metadata.json', bytes: jsonBytes(metadata) },
      ]);
      const descriptor = buildArtifactDescriptor({
        artifactKind: 'trace',
        mimeType: 'application/zip',
        filename: `${context.pageIdForTab(payload.tab_id) || 'page'}.zip`,
        pageId: context.pageIdForTab(payload.tab_id),
        metadata: {
          requested_path: payload.path || null,
          options: session.options,
        },
      });
      await emitArtifact(context, meta.requestId, descriptor, zipBytes);
      return {
        path: payload.path || null,
        artifacts: [descriptor],
      };
    },
  };
}
