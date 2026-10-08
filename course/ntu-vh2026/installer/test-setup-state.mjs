import assert from 'node:assert/strict'
import test from 'node:test'

// eslint-disable-next-line no-restricted-syntax -- The Node ESM runtime requires the source file extension.
import { createInstallRequest, initialModelSelection, MODEL_PRESETS, safeLaunchUrl, selectedMatchesStatus, selectionNeedsDownload } from './web/setup-state.js'

const catalog = [{ id: 'sarc-taigi', license: 'gemma' }, { id: 'kokoro', license: 'kokoro' }]

test('requires Gemma terms for SARC without adding consent gates to Apache models', () => {
  assert.throws(() => createInstallRequest(catalog, new Set(['sarc-taigi']), new Set(), 'bundled'))
  assert.throws(() => createInstallRequest(catalog, new Set(['sarc-taigi', 'kokoro']), new Set(['kokoro']), 'bundled'))
  assert.deepEqual(createInstallRequest(catalog, new Set(['sarc-taigi']), new Set(['gemma']), 'bundled'), {
    models: ['sarc-taigi'],
    ollama_mode: 'bundled',
    accepted_licenses: ['gemma'],
  })
  assert.deepEqual(createInstallRequest(catalog, new Set(['kokoro']), new Set(), 'bundled'), {
    models: ['kokoro'],
    ollama_mode: 'bundled',
    accepted_licenses: [],
  })
})

test('rejects unknown models, empty selections, and unknown runtimes', () => {
  assert.throws(() => createInstallRequest(catalog, new Set(['other']), new Set(['gemma']), 'bundled'))
  assert.throws(() => createInstallRequest(catalog, new Set(), new Set(), 'bundled'))
  assert.throws(() => createInstallRequest(catalog, new Set(['sarc-taigi']), new Set(['gemma']), 'remote'))
})

test('a changed selection cannot start an old verified plan', () => {
  const status = { selected: ['sarc-taigi'], ollama_mode: 'bundled' }
  assert.equal(selectedMatchesStatus(new Set(['sarc-taigi']), 'bundled', status), true)
  assert.equal(selectedMatchesStatus(new Set(['kokoro']), 'bundled', status), false)
  assert.equal(selectedMatchesStatus(new Set(['sarc-taigi']), 'existing', status), false)
})

test('launch links cannot navigate to an external app or endpoint', () => {
  assert.equal(safeLaunchUrl('/?localSetup=1'), 'http://127.0.0.1:17900/?localSetup=1')
  for (const url of ['https://example.com/?localSetup=1', '//example.com', '/api/start', '/?localSetup=0', '/?localSetup=1#remote'])
    assert.throws(() => safeLaunchUrl(url))
})

test('lightweight and full presets form valid plans with distinct language capabilities', () => {
  const modelIds = new Set(Object.values(MODEL_PRESETS).flat())
  const available = [...modelIds].map(id => ({ id, license: id === 'sarc-taigi' ? 'gemma' : id }))
  const lite = createInstallRequest(available, new Set(MODEL_PRESETS.lite), new Set(), 'bundled')
  expectModels(lite.models, ['qwen', 'asr26', 'kokoro'])
  assert.equal(lite.models.includes('kaedetai'), false)
  const full = createInstallRequest(available, new Set(MODEL_PRESETS.full), new Set(['gemma']), 'bundled')
  assert.equal(full.models.includes('sarc-taigi'), true)
  assert.equal(full.models.includes('kaedetai'), true)
  assert.equal(full.models.includes('qwen'), false)
})

function expectModels(actual, expected) {
  assert.deepEqual(new Set(actual), new Set(expected))
}

test('MotionGPT is opt-in and an offline package labels its first download correctly', () => {
  for (const preset of Object.values(MODEL_PRESETS))
    assert.equal(preset.includes('motiongpt'), false)
  const status = { offline: true, catalog: [
    { id: 'kokoro', installed: true },
    { id: 'motiongpt', installed: false, download_only: true },
  ] }
  assert.equal(selectionNeedsDownload(status, new Set(['kokoro'])), false)
  assert.equal(selectionNeedsDownload(status, new Set(['kokoro', 'motiongpt'])), true)
  status.catalog[1].installed = true
  assert.equal(selectionNeedsDownload(status, new Set(['motiongpt'])), false)
})

test('first launch uses the package defaults without selecting optional MotionGPT', () => {
  const status = {
    catalog: [...MODEL_PRESETS.full, 'motiongpt'].map(id => ({ id })),
    selected: [],
    default_models: MODEL_PRESETS.full,
  }
  assert.deepEqual(initialModelSelection(status), MODEL_PRESETS.full)
  assert.equal(initialModelSelection(status).includes('motiongpt'), false)
})

test('reopening restores a saved MotionGPT choice without adding default models', () => {
  const status = {
    catalog: [...MODEL_PRESETS.full, 'motiongpt'].map(id => ({ id })),
    selected: ['kokoro', 'motiongpt'],
    default_models: MODEL_PRESETS.full,
  }
  assert.deepEqual(initialModelSelection(status), ['kokoro', 'motiongpt'])
  assert.deepEqual(status.selected, ['kokoro', 'motiongpt'])
})

test('switching packages filters saved choices and falls back only when none remain', () => {
  const status = {
    catalog: MODEL_PRESETS.lite.map(id => ({ id })),
    selected: ['sarc-taigi', 'kokoro', 'motiongpt'],
    default_models: MODEL_PRESETS.lite,
  }
  assert.deepEqual(initialModelSelection(status), ['kokoro'])
  status.selected = ['sarc-taigi', 'motiongpt']
  assert.deepEqual(initialModelSelection(status), MODEL_PRESETS.lite)
  status.default_models = [...MODEL_PRESETS.lite, 'unavailable']
  assert.deepEqual(initialModelSelection(status), MODEL_PRESETS.lite)
})

test('restoring saved SARC still requires explicit license acceptance', () => {
  const restored = new Set(initialModelSelection({
    catalog,
    selected: ['sarc-taigi'],
    default_models: ['kokoro'],
  }))
  const accepted = new Set()
  assert.throws(() => createInstallRequest(catalog, restored, accepted, 'bundled'), /授權/)
  assert.equal(accepted.size, 0)
})
