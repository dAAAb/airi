// @vitest-environment jsdom
import { useLlmmarkerParser } from '@proj-airi/core-agent'
import { createStreamingControlParser, normalizeActPayload } from '@proj-airi/pipelines-audio'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive, ref } from 'vue'

import { useMotionDecisionsStore } from './motion-decisions'

const settings = reactive({ stageModelRenderer: 'vrm', stageModelSelected: 'avatar-a' })
const motion = reactive({ configured: true, autoGenerate: true })
const providers = reactive<Record<string, { id: string, definitionId: string, config: Record<string, unknown> }>>({})
vi.mock('../settings', () => ({ useSettings: () => settings }))
vi.mock('./motion', () => ({ useMotionStore: () => motion }))
vi.mock('../providers/config', () => ({ useProviderConfigStore: () => ({ providers, getProvider: (id: string) => providers[id] }) }))
vi.mock('@proj-airi/stage-shared/composables', () => ({ useLocalStorageManualReset: (_key: string, value: unknown) => ref(value) }))

const cloud = { source: 'openai-decisions', choice: 'wave', motion: 'wave', confidence: 0.9, elapsed_ms: 20 }
function answer(overrides = {}) {
  return new Response(JSON.stringify({ ...cloud, ...overrides }))
}
function service(result: () => Promise<Response>) {
  const request = vi.fn<typeof fetch>().mockImplementation(async url => String(url).endsWith('/api/bootstrap')
    ? new Response(JSON.stringify({ origin: 'http://127.0.0.1:17900', token: 'synthetic-token' }))
    : result())
  vi.stubGlobal('fetch', request)
  return request
}
function ready() {
  const store = useMotionDecisionsStore()
  store.enabled = true
  store.setSessionKey('synthetic-session-key')
  return store
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('window', { location: { origin: 'http://127.0.0.1:17900' } })
  settings.stageModelRenderer = 'vrm'
  settings.stageModelSelected = 'avatar-a'
  motion.configured = true
  motion.autoGenerate = true
  for (const id of Object.keys(providers)) delete providers[id]
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('per-turn local/cloud motion arbitration', () => {
  it('defaults to local, keeps session keys out of store state, and sends nothing without opt-in/key', async () => {
    const request = service(async () => answer())
    const store = useMotionDecisionsStore()
    expect(store.enabled).toBe(false)
    await store.beginTurn('a', 's', 'hello')
    store.enabled = true
    await store.beginTurn('b', 's', 'hello')
    expect(store.status).toBe('missing-key')
    expect(request).not.toHaveBeenCalled()
    store.setSessionKey('synthetic-private-session-key')
    expect(JSON.stringify(store.$state)).not.toContain('synthetic-private-session-key')
  })

  it('lets local idle win and ignores a late cloud response even if fetch ignores abort', async () => {
    const pending = Promise.withResolvers<Response>()
    const request = service(() => pending.promise)
    const store = ready()
    const result = store.beginTurn('a', 's', '請不要動')
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    expect(store.claimLocal('a', { motion: 'idle' })).toBe(true)
    pending.resolve(answer())
    expect(await result).toBeUndefined()
    expect(store.status).toBe('local-won')
    expect(store.consumeCloudMotion('a')).toBe(false)
    expect(request.mock.calls[1][1]?.signal?.aborted).toBe(true)
  })

  it('lets cloud win once, preventing later local or queued TTS motion replay', async () => {
    service(async () => answer({ motion: 'idle', choice: 'idle' }))
    const store = ready()
    expect(await store.beginTurn('a', 's', '不用動作')).toEqual({ motion: 'idle' })
    expect(store.claimLocal('a', { motion: 'dance' })).toBe(false)
    expect(store.consumeCloudMotion('a')).toBe(true)
    expect(store.consumeCloudMotion('a')).toBe(false)
  })

  it.each(['cancel', 'new-turn', 'disable', 'character'])('rejects cloud delivery after %s between resolution and Stage consumption', async (change) => {
    service(async () => answer())
    const store = ready()
    expect(await store.beginTurn('a', 's', 'hello')).toEqual({ motion: 'wave' })
    if (change === 'cancel')
      store.cancelTurn('a')
    else if (change === 'new-turn')
      await store.beginTurn('b', 's', 'hello')
    else if (change === 'disable')
      store.enabled = false
    else settings.stageModelSelected = 'avatar-b'
    expect(store.consumeCloudMotion('a')).toBe(false)
    expect(store.disposition('a')).toBe('stale')
  })

  it.each([
    { motion: 'defer' },
    { refused: true },
    { confidence: 0.3 },
    { confidence: undefined },
    { motion: 'generate', motion_prompt: 'A person stretches.' },
  ])('preserves local ACT after a deferred cloud result %j', async (result) => {
    service(async () => answer(result))
    const store = ready()
    motion.autoGenerate = false
    expect(await store.beginTurn('a', 's', 'hello')).toBeUndefined()
    expect(store.status).toBe('deferred')
    expect(store.claimLocal('a', { motion: 'wave' })).toBe(true)
  })

  it('falls back after a rejected network request without retaining its secret-bearing exception', async () => {
    service(async () => {
      throw new Error('synthetic-sensitive-error')
    })
    const store = ready()
    expect(await store.beginTurn('a', 's', 'hello')).toBeUndefined()
    expect(store.status).toBe('fallback')
    expect(JSON.stringify(store.$state)).not.toContain('synthetic-sensitive-error')
    expect(store.claimLocal('a', { motion: 'wave' })).toBe(true)
  })

  it('reuses only the selected OpenAI provider key without modifying provider config', async () => {
    providers.official = { id: 'official', definitionId: 'openai', config: { apiKey: 'synthetic-existing-key' } }
    providers.other = { id: 'other', definitionId: 'openrouter', config: { apiKey: 'synthetic-unrelated-key' } }
    const request = service(async () => answer())
    const store = useMotionDecisionsStore()
    store.enabled = true
    store.keySource = 'official'
    expect(store.openAiProviders.map(item => item.id)).toEqual(['official'])
    await store.beginTurn('a', 's', 'only current text')
    expect(JSON.parse(String(request.mock.calls[1][1]?.body))).toEqual({ cloud_enabled: true, api_key: 'synthetic-existing-key', text: 'only current text' })
    expect(providers.official.config).toEqual({ apiKey: 'synthetic-existing-key' })
  })

  it('does not send requests for Live2D', async () => {
    const request = service(async () => answer())
    const store = ready()
    settings.stageModelRenderer = 'live2d'
    await store.beginTurn('a', 's', 'wave')
    expect(request).not.toHaveBeenCalled()
    expect(store.disposition('a')).toBe('local')
  })

  it('dispatches local ACT before TTS and rejects its later queued replay while cloud is off', async () => {
    const request = service(async () => answer())
    const store = useMotionDecisionsStore()
    await store.beginTurn('a', 's', '請伸展')
    const immediate = createStreamingControlParser()
    const apply = vi.fn()
    immediate.onSignal((signal, context) => {
      if (signal.type === 'act' && context.turnId) {
        const act = normalizeActPayload(signal.payload)
        if (store.claimLocal(context.turnId, act))
          apply(act)
      }
    })
    const delayedTts: string[] = []
    const parser = useLlmmarkerParser({
      onSpecial: async (value) => {
        await immediate.dispatchWith(value, { turnId: 'a' })
        delayedTts.push(value)
      },
    })
    const act = { motion: 'generate', motionPrompt: 'A person stretches both arms overhead.' }
    for (const character of `<|ACT ${JSON.stringify(act)}|>來伸展一下。`)
      await parser.consume(character)
    await parser.end()
    expect(apply).toHaveBeenCalledExactlyOnceWith(act)
    expect(request).not.toHaveBeenCalled()
    for (const token of delayedTts)
      await immediate.dispatchWith(token, { turnId: 'a' })
    expect(apply).toHaveBeenCalledTimes(1)
  })

  it('does not consume a generated cloud action after automatic generation is disabled', async () => {
    service(async () => answer({ motion: 'generate', motion_prompt: 'A person stretches.' }))
    const store = ready()
    expect(await store.beginTurn('a', 's', 'stretch')).toBeDefined()
    motion.autoGenerate = false
    expect(store.consumeCloudMotion('a')).toBe(false)
  })

  it('aborts a slow cloud request after five seconds and keeps local ACT available', async () => {
    vi.useFakeTimers()
    const request = vi.fn<typeof fetch>().mockImplementation((url, init) => {
      if (String(url).endsWith('/api/bootstrap'))
        return Promise.resolve(new Response(JSON.stringify({ origin: 'http://127.0.0.1:17900', token: 'token' })))
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
      })
    })
    vi.stubGlobal('fetch', request)
    const store = ready()
    const pending = store.beginTurn('a', 's', 'wave')
    await vi.advanceTimersByTimeAsync(5001)
    expect(await pending).toBeUndefined()
    expect(store.status).toBe('fallback')
    expect(store.claimLocal('a', { motion: 'wave' })).toBe(true)
  })
})
