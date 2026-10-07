const assert = require('node:assert/strict')
const { test } = require('node:test')

const { clampBounds, defaultPreferences, isStageHome, isTrustedDesktopSender, parseFlag, parseMode, sanitizePreferences } = require('./desktop-state.cjs')
const { ORIGIN } = require('./policy.cjs')

const primary = { x: 0, y: 25, width: 1440, height: 875 }
const secondary = { x: -1920, y: 0, width: 1920, height: 1080 }

test('desktop preferences exclude click-through and reject corrupt records', () => {
  assert.deepEqual(sanitizePreferences(null), defaultPreferences())
  assert.deepEqual(sanitizePreferences({ version: 1, mode: 'pet', alwaysOnTop: false, clickThrough: true }), { version: 1, mode: 'pet', alwaysOnTop: false })
  for (const invalid of [{ version: 1, mode: 'background', alwaysOnTop: true }, { version: 1, mode: 'pet', alwaysOnTop: 'false' }, { version: 1, mode: 'pet', alwaysOnTop: true, petBounds: { x: Infinity, y: 0, width: 400, height: 600 } }])
    assert.deepEqual(sanitizePreferences(invalid), defaultPreferences())
})

test('mode and flags reject coercion from untrusted renderer data', () => {
  assert.equal(parseMode('pet'), 'pet')
  assert.equal(parseMode('window'), 'window')
  assert.equal(parseFlag(false), false)
  for (const invalid of ['fullscreen', null, {}, true])
    assert.throws(() => parseMode(invalid))
  for (const invalid of ['false', 0, null, {}])
    assert.throws(() => parseFlag(invalid))
})

test('only the trusted main frame can issue native commands', () => {
  const frame = { url: `${ORIGIN}/` }
  const contents = { mainFrame: frame, getURL: () => `${ORIGIN}/` }
  assert.equal(isTrustedDesktopSender({ sender: contents, senderFrame: frame }, contents), true)
  assert.equal(isTrustedDesktopSender({ sender: {}, senderFrame: frame }, contents), false)
  assert.equal(isTrustedDesktopSender({ sender: contents, senderFrame: { url: `${ORIGIN}/` } }, contents), false)
  assert.equal(isTrustedDesktopSender({ sender: contents, senderFrame: null }, contents), false)
  frame.url = 'https://example.com/'
  assert.equal(isTrustedDesktopSender({ sender: contents, senderFrame: frame }, contents), false)
})

test('pet mode is limited to the local stage home', () => {
  assert.equal(isStageHome(`${ORIGIN}/?test=1`), true)
  for (const url of [`${ORIGIN}/setup/`, `${ORIGIN}/settings`, 'https://example.com/', 'http://localhost:17900/'])
    assert.equal(isStageHome(url), false)
})

test('bounds stay in the selected display, including negative monitor coordinates', () => {
  const original = { x: -1700, y: 100, width: 420, height: 640 }
  assert.deepEqual(clampBounds(original, 'pet', [primary, secondary]), original)
  assert.deepEqual(clampBounds({ x: 99999, y: -500, width: 420, height: 640 }, 'pet', [primary]), { x: 1020, y: 25, width: 420, height: 640 })
  assert.deepEqual(clampBounds(original, 'pet', [primary]), { x: 0, y: 100, width: 420, height: 640 })
})

test('bounds fit small work areas and recover malformed saved geometry', () => {
  const small = { x: 0, y: 24, width: 640, height: 456 }
  assert.deepEqual(clampBounds({ x: 100, y: 200, width: 1600, height: 1200 }, 'window', [small]), small)
  const restored = clampBounds({ x: Number.NaN, y: 0, width: -1, height: 1 }, 'pet', [primary])
  assert.deepEqual(restored, { x: 996, y: 236, width: 420, height: 640 })
  assert.throws(() => clampBounds(undefined, 'pet', []))
})
