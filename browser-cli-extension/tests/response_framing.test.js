import test from 'node:test'
import assert from 'node:assert/strict'

import { RESPONSE_CHUNK_SIZE } from '../src/protocol.js'
import { sendFramedMessage } from '../src/background/response_framing.js'

function installSocketStub() {
  const sent = []
  return {
    sent,
    socket: {
      readyState: 1,
      send(payload) {
        sent.push(payload)
      },
    },
  }
}

test('sendFramedMessage sends small responses as a single frame', () => {
  const { sent, socket } = installSocketStub()
  const message = { type: 'response', id: 'req-1', ok: true, data: { html: '<p>hi</p>' } }
  assert.equal(sendFramedMessage(socket, message), 1)
  assert.equal(sent.length, 1)
  assert.deepEqual(JSON.parse(sent[0]), message)
})

test('sendFramedMessage chunks oversized responses under the frame limit', () => {
  const { sent, socket } = installSocketStub()
  const html = 'x'.repeat(RESPONSE_CHUNK_SIZE + 128)
  const message = { type: 'response', id: 'req-2', ok: true, data: { html } }
  const frameCount = sendFramedMessage(socket, message, 1024)
  assert.ok(frameCount > 1)
  assert.equal(sent.length, frameCount)

  const chunks = sent.map((raw) => JSON.parse(raw))
  for (const chunk of chunks) {
    assert.equal(chunk.type, 'response-chunk')
    assert.equal(chunk.id, 'req-2')
    assert.ok(JSON.stringify(chunk).length < RESPONSE_CHUNK_SIZE)
  }
  assert.equal(chunks.at(-1)?.final, true)
  const assembled = chunks
    .sort((left, right) => left.index - right.index)
    .map((chunk) => chunk.chunk)
    .join('')
  assert.deepEqual(JSON.parse(assembled), message)
})

test('sendFramedMessage rejects a closed socket', () => {
  assert.throws(
    () => sendFramedMessage({ readyState: 3, send() {} }, { type: 'response', id: 'x' }),
    /not connected/,
  )
})
