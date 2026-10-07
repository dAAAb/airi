const assert = require('node:assert/strict')
const { test } = require('node:test')

const { ORIGIN, isLocalPage, microphoneAllowed, isExternalWebLink, isOfflineRequestAllowed } = require('./policy.cjs')

test('only exact manager origin can stay inside the app', () => {
  assert.equal(isLocalPage(`${ORIGIN}/setup/`), true)
  for (const url of ['http://127.0.0.1:5174/', 'http://localhost:17900/', 'https://127.0.0.1:17900/', 'file:///tmp/x', 'http://127.0.0.1:17900.evil.test/', 'http://u:p@127.0.0.1:17900/'])
    assert.equal(isLocalPage(url), false, url)
})
test('microphone permission needs both local page and requesting frame', () => {
  assert.equal(microphoneAllowed(ORIGIN, 'media', `${ORIGIN}/`, ['audio']), true)
  assert.equal(microphoneAllowed(ORIGIN, 'media', 'https://example.com', ['audio']), false)
  assert.equal(microphoneAllowed('https://example.com', 'media', ORIGIN, ['audio']), false)
  assert.equal(microphoneAllowed(ORIGIN, 'media', ORIGIN, ['video']), false)
  assert.equal(microphoneAllowed(ORIGIN, 'media', ORIGIN, ['audio', 'video']), false)
  assert.equal(microphoneAllowed(ORIGIN, 'media', ORIGIN, []), false)
  assert.equal(microphoneAllowed(ORIGIN, 'media', ORIGIN, ['unknown']), false)
  assert.equal(microphoneAllowed(ORIGIN, 'geolocation', ORIGIN, ['audio']), false)
})
test('external navigation does not open local files or native schemes', () => {
  assert.equal(isExternalWebLink('https://github.com/dAAAb/airi'), true)
  for (const url of ['file:///etc/passwd', 'javascript:alert(1)', 'http://example.com', 'https://u:p@example.com', 'mailto:user@example.com'])
    assert.equal(isExternalWebLink(url), false)
})
test('offline HTTP requests stay on loopback', () => {
  for (const url of [ORIGIN, 'http://127.0.0.1:12434/v1/', 'http://localhost:18001/', 'http://[::1]:18884/', 'blob:http://127.0.0.1:17900/abc'])
    assert.equal(isOfflineRequestAllowed(url), true)
  for (const url of ['https://huggingface.co/model', 'https://fonts.googleapis.com/css', 'https://localhost.evil.test/', 'http://192.168.1.1/', 'https://api.openai.com/'])
    assert.equal(isOfflineRequestAllowed(url), false)
})
