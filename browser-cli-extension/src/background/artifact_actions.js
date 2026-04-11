import { ARTIFACT_CHUNK_SIZE } from '../protocol.js';
import { captureScreenshot, printToPdf } from '../debugger.js';

const textEncoder = new TextEncoder();

function toLittleEndian(value, width) {
  const bytes = new Uint8Array(width);
  let current = Number(value >>> 0);
  for (let index = 0; index < width; index += 1) {
    bytes[index] = current & 0xff;
    current >>>= 8;
  }
  return bytes;
}

function concatBytes(parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function crc32(bytes) {
  let crc = 0 ^ (-1);
  for (let index = 0; index < bytes.length; index += 1) {
    crc ^= bytes[index];
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ (-1)) >>> 0;
}

function utf8Bytes(value) {
  return textEncoder.encode(String(value));
}

export function jsonBytes(payload) {
  return utf8Bytes(JSON.stringify(payload, null, 2));
}

export function decodeBase64Bytes(value) {
  return Uint8Array.from(atob(String(value || '')), (char) => char.charCodeAt(0));
}

export function bytesToBase64(bytes) {
  let text = '';
  for (let index = 0; index < bytes.length; index += 0x8000) {
    text += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(text);
}

export function buildStoredZip(entries) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = utf8Bytes(entry.name);
    const dataBytes = entry.bytes instanceof Uint8Array ? entry.bytes : new Uint8Array(entry.bytes);
    const crc = crc32(dataBytes);
    const localHeader = concatBytes([
      toLittleEndian(0x04034b50, 4),
      toLittleEndian(20, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(crc, 4),
      toLittleEndian(dataBytes.length, 4),
      toLittleEndian(dataBytes.length, 4),
      toLittleEndian(nameBytes.length, 2),
      toLittleEndian(0, 2),
      nameBytes,
      dataBytes,
    ]);
    localParts.push(localHeader);

    const centralHeader = concatBytes([
      toLittleEndian(0x02014b50, 4),
      toLittleEndian(20, 2),
      toLittleEndian(20, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(crc, 4),
      toLittleEndian(dataBytes.length, 4),
      toLittleEndian(dataBytes.length, 4),
      toLittleEndian(nameBytes.length, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 2),
      toLittleEndian(0, 4),
      toLittleEndian(offset, 4),
      nameBytes,
    ]);
    centralParts.push(centralHeader);
    offset += localHeader.length;
  }

  const centralDirectory = concatBytes(centralParts);
  const localDirectory = concatBytes(localParts);
  const endRecord = concatBytes([
    toLittleEndian(0x06054b50, 4),
    toLittleEndian(0, 2),
    toLittleEndian(0, 2),
    toLittleEndian(entries.length, 2),
    toLittleEndian(entries.length, 2),
    toLittleEndian(centralDirectory.length, 4),
    toLittleEndian(localDirectory.length, 4),
    toLittleEndian(0, 2),
  ]);
  return concatBytes([localDirectory, centralDirectory, endRecord]);
}

export function buildArtifactDescriptor({
  artifactKind,
  mimeType,
  filename,
  pageId = null,
  metadata = {},
}) {
  return {
    artifact_id: `${artifactKind}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    artifact_kind: artifactKind,
    mime_type: mimeType,
    filename,
    page_id: pageId,
    metadata,
  };
}

export async function emitArtifact(context, requestId, descriptor, bytes) {
  const socket = context.state.ws;
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error('Extension socket is not connected.');
  }
  const base64 = bytesToBase64(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes));
  socket.send(JSON.stringify({
    type: 'artifact-begin',
    request_id: requestId,
    artifact_id: descriptor.artifact_id,
    artifact_kind: descriptor.artifact_kind,
    mime_type: descriptor.mime_type,
    encoding: 'base64',
    filename: descriptor.filename,
    page_id: descriptor.page_id,
    metadata: descriptor.metadata || {},
  }));
  let index = 0;
  for (let offset = 0; offset < base64.length; offset += ARTIFACT_CHUNK_SIZE) {
    socket.send(JSON.stringify({
      type: 'artifact-chunk',
      request_id: requestId,
      artifact_id: descriptor.artifact_id,
      artifact_kind: descriptor.artifact_kind,
      mime_type: descriptor.mime_type,
      encoding: 'base64',
      index,
      final: offset + ARTIFACT_CHUNK_SIZE >= base64.length,
      chunk: base64.slice(offset, offset + ARTIFACT_CHUNK_SIZE),
    }));
    index += 1;
  }
  socket.send(JSON.stringify({
    type: 'artifact-end',
    request_id: requestId,
    artifact_id: descriptor.artifact_id,
    size_bytes: bytes.length,
  }));
  return descriptor;
}

export async function emitBase64Artifact(context, requestId, descriptor, dataBase64) {
  return await emitArtifact(context, requestId, descriptor, decodeBase64Bytes(dataBase64));
}

export function createArtifactHandlers(context) {
  return {
    async screenshot(payload, meta) {
      await context.getManagedTab(payload.tab_id);
      const dataBase64 = await captureScreenshot(payload.tab_id, { fullPage: !!payload.full_page });
      const descriptor = buildArtifactDescriptor({
        artifactKind: 'screenshot',
        mimeType: 'image/png',
        filename: `${context.pageIdForTab(payload.tab_id) || 'page'}.png`,
        pageId: context.pageIdForTab(payload.tab_id),
        metadata: { full_page: !!payload.full_page },
      });
      await emitBase64Artifact(context, meta.requestId, descriptor, dataBase64);
      return { artifacts: [descriptor], full_page: !!payload.full_page };
    },
    async pdf(payload, meta) {
      await context.getManagedTab(payload.tab_id);
      const dataBase64 = await printToPdf(payload.tab_id);
      const descriptor = buildArtifactDescriptor({
        artifactKind: 'pdf',
        mimeType: 'application/pdf',
        filename: `${context.pageIdForTab(payload.tab_id) || 'page'}.pdf`,
        pageId: context.pageIdForTab(payload.tab_id),
      });
      await emitBase64Artifact(context, meta.requestId, descriptor, dataBase64);
      return { artifacts: [descriptor] };
    },
  };
}
