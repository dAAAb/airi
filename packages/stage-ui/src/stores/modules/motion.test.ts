// @vitest-environment jsdom
import type { TextToken } from '@proj-airi/pipelines-audio'

import { useLlmmarkerParser } from '@proj-airi/core-agent'
import { createPushStream, createStreamingControlParser, createTtsSegmentStream, normalizeActPayload, readStream } from '@proj-airi/pipelines-audio'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive, ref } from 'vue'

import { useMotionStore } from './motion'

const settings = reactive({ stageModelRenderer: 'vrm', stageModelSelected: 'avatar-a' })
vi.mock('../settings', () => ({ useSettings: () => settings }))
vi.mock('@proj-airi/stage-shared/composables', () => ({ useLocalStorageManualReset: (_key: string, value: unknown) => ref(value) }))

function health(overrides = {}) {
  return { ready: true, model: 'MotionGPT', device: 'cpu', selected_device: 'auto', available_devices: ['cpu', 'mps', 'mlx'], fps: 20, max_frames: 196, load_seconds: 0.1, busy: false, auto_fallback_reason: null, ...overrides }
}

function mockService(generate: typeof fetch = async () => response()) {
  return vi.fn<typeof fetch>().mockImplementation((input, init) => String(input).endsWith('/health')
    ? Promise.resolve(new Response(JSON.stringify(health())))
    : generate(input, init))
}

function response() {
  return new Response(JSON.stringify({ format: 'humanml3d-22', fps: 20, coordinate_system: 'right-handed-y-up', joints: Array.from({ length: 40 }, () => Array.from({ length: 22 }, () => [0, 1, 0])) }))
}

beforeEach(() => {
  setActivePinia(createPinia())
  settings.stageModelRenderer = 'vrm'
  settings.stageModelSelected = 'avatar-a'
})
afterEach(() => vi.unstubAllGlobals())

describe('optional motion generation lifecycle', () => {
  it('defaults off and never calls the service while disabled or on Live2D', async () => {
    const request = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    expect(store.enabled).toBe(false)
    expect(store.autoGenerate).toBe(false)
    await store.generate('wave')
    store.enabled = true
    settings.stageModelRenderer = 'live2d'
    await nextTick()
    expect(store.available).toBe(false)
    await store.generate('wave')
    expect(request).not.toHaveBeenCalled()
  })

  it('drops responses after model change even when transport ignores abort', async () => {
    const pending = Promise.withResolvers<Response>()
    const request = mockService(() => pending.promise)
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    await nextTick()
    const generation = store.generate('raise right hand')
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    settings.stageModelSelected = 'avatar-b'
    await nextTick()
    pending.resolve(response())
    expect(await generation).toBeUndefined()
    expect(store.lastClip).toBeUndefined()
    expect(store.status).toBe('idle')
    expect(request.mock.calls[1][1]?.signal?.aborted).toBe(true)
  })

  it('lets only the latest request produce a clip', async () => {
    const first = Promise.withResolvers<Response>()
    const second = Promise.withResolvers<Response>()
    const generate = vi.fn<typeof fetch>().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    vi.stubGlobal('fetch', mockService(generate))
    const store = useMotionStore()
    store.enabled = true
    await nextTick()
    const oldGeneration = store.generate('wave')
    await vi.waitFor(() => expect(generate).toHaveBeenCalledTimes(1))
    const newGeneration = store.generate('bow')
    await vi.waitFor(() => expect(generate).toHaveBeenCalledTimes(2))
    first.resolve(response())
    expect(await oldGeneration).toBeUndefined()
    expect(store.status).toBe('generating')
    second.resolve(response())
    expect(await newGeneration).toBeDefined()
    expect(store.status).toBe('generated')
  })

  it('does not restart identical pending ACT requests', async () => {
    const pending = Promise.withResolvers<Response>()
    const request = mockService(() => pending.promise)
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    await nextTick()
    const generation = store.generate('wave')
    await store.generate(' wave ')
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    pending.resolve(response())
    expect(await generation).toBeDefined()
  })

  it('does not label a reachable but unready model as ready', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(health({ ready: false })))))
    const store = useMotionStore()
    await store.checkHealth()
    expect(store.status).toBe('error')
    expect(store.lastError).toContain('not ready')
  })

  it('routes streamed generated ACT text through the real speech pipeline into a local generation request', async () => {
    const request = mockService()
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    store.autoGenerate = true
    await nextTick()

    const prompt = 'A person raises both arms overhead and stretches their body.'
    const spoken = '好，來伸展一下。'
    const control = createStreamingControlParser()
    control.onSignal(async (signal) => {
      if (signal.type === 'act')
        await store.generateFromAct(normalizeActPayload(signal.payload))
    })
    const tokens = createPushStream<TextToken>()
    const meta = { streamId: 'generated-motion-test', intentId: 'generated-motion-test' }
    const speech: string[] = []
    const completed = readStream(createTtsSegmentStream(tokens.stream, meta), async (segment) => {
      if (segment.text)
        speech.push(segment.text)
      if (segment.special)
        await control.dispatchWith(segment.special)
    })
    let sequence = 0
    const write = (type: TextToken['type'], value: string) => tokens.write({ ...meta, type, value, sequence: sequence++, createdAt: Date.now() })
    const parser = useLlmmarkerParser({
      onLiteral: value => write('literal', value),
      onSpecial: value => write('special', value),
    })
    const modelOutput = `<|ACT ${JSON.stringify({ emotion: 'happy', motion: 'generate', motionPrompt: prompt })}|>${spoken}`
    for (const chunk of modelOutput)
      await parser.consume(chunk)
    await parser.end()
    tokens.close()
    await completed

    expect(speech.join('')).toBe(spoken)
    expect(request).toHaveBeenCalledTimes(2)
    expect(request.mock.calls[1][0]).toBe('http://127.0.0.1:17905/v1/motions/generate')
    expect(JSON.parse(String(request.mock.calls[1][1]?.body))).toEqual({ prompt, seed: 42 })
    expect(store.status).toBe('generated')
    expect(store.lastClip?.joints).toHaveLength(40)
  })

  it('keeps conversational generation opt-in independently of manual generation', async () => {
    const request = mockService()
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    await nextTick()
    const act = { motion: 'generate', motionPrompt: 'A person stretches.' }
    await store.generateFromAct(act)
    expect(request).not.toHaveBeenCalled()
    store.autoGenerate = true
    await nextTick()
    await store.generateFromAct({ motion: 'wave', motionPrompt: act.motionPrompt })
    expect(request).not.toHaveBeenCalled()
    await store.generateFromAct(act)
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('restores the saved runtime preference before generating after a server restart', async () => {
    const switched = Promise.withResolvers<Response>()
    const request = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      if (String(input).endsWith('/health'))
        return new Response(JSON.stringify(health()))
      if (String(input).endsWith('/v1/runtime'))
        return switched.promise
      return response()
    })
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    store.runtimePreference = 'mlx'
    await nextTick()
    const generation = store.generate('stretch')
    await vi.waitFor(() => expect(store.status).toBe('switching'))
    expect(store.busy).toBe(true)
    expect(request).toHaveBeenCalledTimes(2)
    expect(JSON.parse(String(request.mock.calls[1][1]?.body))).toEqual({ device: 'mlx' })
    switched.resolve(new Response(JSON.stringify(health({ device: 'mlx', selected_device: 'mlx', load_seconds: 1.5 }))))
    expect(await generation).toBeDefined()
    expect(request.mock.calls.map(([url]) => String(url))).toEqual([
      'http://127.0.0.1:17905/health',
      'http://127.0.0.1:17905/v1/runtime',
      'http://127.0.0.1:17905/v1/motions/generate',
    ])
    expect(store.healthDetails?.device).toBe('mlx')
  })

  it('reports unavailable saved devices without silently selecting another one', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(health({ available_devices: ['cpu'] }))))
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    store.runtimePreference = 'mlx'
    await nextTick()
    expect(await store.generate('stretch')).toBeUndefined()
    expect(request).toHaveBeenCalledTimes(1)
    expect(store.status).toBe('error')
    expect(store.lastError).toContain('unavailable: mlx')
    expect(store.healthDetails?.available_devices).toEqual(['cpu'])
  })

  it('keeps the last working device visible after a failed switch and prevents generation', async () => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(health())))
      .mockResolvedValueOnce(new Response('{}', { status: 422 }))
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    await store.setRuntimePreference('mlx')
    expect(store.runtimePreference).toBe('mlx')
    expect(store.healthDetails?.device).toBe('cpu')
    expect(store.status).toBe('error')
    expect(store.lastError).toContain('422')
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('does not generate after cancelling a device load, even if the server finishes it', async () => {
    const pending = Promise.withResolvers<Response>()
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(health())))
      .mockReturnValueOnce(pending.promise)
    vi.stubGlobal('fetch', request)
    const store = useMotionStore()
    store.enabled = true
    store.runtimePreference = 'mps'
    await nextTick()
    const generation = store.generate('bow')
    await vi.waitFor(() => expect(store.status).toBe('switching'))
    store.cancel()
    pending.resolve(new Response(JSON.stringify(health({ device: 'mps', selected_device: 'mps' }))))
    expect(await generation).toBeUndefined()
    expect(request).toHaveBeenCalledTimes(2)
    expect(store.status).toBe('idle')
    expect(store.healthDetails?.device).toBe('cpu')
  })
})
