import { RESPONSE_CHUNK_SIZE } from '../protocol.js';

/**
 * Send a protocol message, chunking oversized JSON so the daemon WebSocket
 * receiver never hits its default 1 MiB frame limit.
 */
export function sendFramedMessage(socket, message, chunkSize = RESPONSE_CHUNK_SIZE) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error('Extension socket is not connected.');
  }
  const encoded = JSON.stringify(message);
  const size = Number(chunkSize) > 0 ? Number(chunkSize) : RESPONSE_CHUNK_SIZE;
  if (encoded.length <= size) {
    socket.send(encoded);
    return 1;
  }
  const id = String(message.id || '');
  let index = 0;
  for (let offset = 0; offset < encoded.length; offset += size) {
    const chunk = encoded.slice(offset, offset + size);
    socket.send(JSON.stringify({
      type: 'response-chunk',
      id,
      index,
      final: offset + size >= encoded.length,
      chunk,
    }));
    index += 1;
  }
  return index;
}
