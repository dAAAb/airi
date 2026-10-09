// @vitest-environment jsdom
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { translateMotionPrompt } from '../../libs/motion-prompt'
import { useMotionPromptStore } from './motion-prompt'

vi.mock('../../libs/motion-prompt', async importOriginal => ({ ...await importOriginal<typeof import('../../libs/motion-prompt')>(), translateMotionPrompt: vi.fn() }))
const consciousness = reactive({ activeProvider: 'local-a', activeModel: 'chosen-a', customModelName: '', getChatProviderInstance: vi.fn() })
const settings = reactive({ stageModelSelected: 'avatar-a', stageModelRenderer: 'vrm' })
const motion = reactive({ configured: true, enabled: true, endpoint: 'http://127.0.0.1:17905', cancel: vi.fn(), generate: vi.fn() })
vi.mock('./consciousness', () => ({ useConsciousnessStore: () => consciousness }))
vi.mock('../settings', () => ({ useSettings: () => settings }))
vi.mock('./motion', () => ({ useMotionStore: () => motion }))

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  consciousness.activeProvider = 'local-a'
  consciousness.activeModel = 'chosen-a'
  consciousness.customModelName = ''
  settings.stageModelSelected = 'avatar-a'
  motion.configured = true
  motion.enabled = true
  consciousness.getChatProviderInstance.mockResolvedValue({ generation: () => ({ protocol: 'chat-completions', config: { baseURL: 'http://127.0.0.1:11434/v1/' } }) })
  vi.mocked(translateMotionPrompt).mockResolvedValue('A person jumps upward and lands on both feet.')
  motion.generate.mockResolvedValue({ fps: 20 })
})
afterEach(() => vi.useRealTimers())

describe('manual motion translation lifecycle', () => {
  it('sends English directly without resolving a language model', async () => {
    const store = useMotionPromptStore()
    await store.generate('A person jumps.')
    expect(consciousness.getChatProviderInstance).not.toHaveBeenCalled()
    expect(translateMotionPrompt).not.toHaveBeenCalled()
    expect(motion.generate).toHaveBeenCalledWith('A person jumps.')
    expect(store.actualPrompt).toBe('A person jumps.')
  })

  it('shows original and translated input before sending only English to MotionGPT', async () => {
    const store = useMotionPromptStore()
    motion.generate.mockImplementation(async (prompt) => {
      expect(store.originalInput).toBe('跳高')
      expect(store.actualPrompt).toBe(prompt)
      return { fps: 20 }
    })
    await store.generate('跳高')
    expect(motion.generate).toHaveBeenCalledWith('A person jumps upward and lands on both feet.')
    expect(store.translatedBy).toBe('chosen-a')
  })

  it('fails clearly when no current model exists and never forwards Chinese', async () => {
    consciousness.activeModel = ''
    const store = useMotionPromptStore()
    expect(await store.generate('跳高')).toBeUndefined()
    expect(store.errorCode).toBe('local-model-required')
    expect(motion.generate).not.toHaveBeenCalled()
  })

  it.each(['cancel', 'model', 'avatar', 'input'])('drops late translations after %s even when the provider ignores abort', async (change) => {
    const pending = Promise.withResolvers<string>()
    vi.mocked(translateMotionPrompt).mockReturnValueOnce(pending.promise)
    const store = useMotionPromptStore()
    const work = store.generate('跳高')
    await vi.waitFor(() => expect(translateMotionPrompt).toHaveBeenCalledTimes(1))
    if (change === 'cancel')
      store.cancel()
    else if (change === 'model')
      consciousness.activeModel = 'chosen-b'
    else if (change === 'avatar')
      settings.stageModelSelected = 'avatar-b'
    else store.clear()
    pending.resolve('A person jumps.')
    expect(await work).toBeUndefined()
    expect(motion.generate).not.toHaveBeenCalled()
    expect(store.actualPrompt).toBe('')
    expect(store.translatedBy).toBe('')
  })

  it('times out even when translation transport ignores abort', async () => {
    vi.useFakeTimers()
    vi.mocked(translateMotionPrompt).mockReturnValueOnce(new Promise(() => {}))
    const store = useMotionPromptStore()
    const work = store.generate('跳高')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(await work).toBeUndefined()
    expect(store.errorCode).toBe('timeout')
    expect(store.translating).toBe(false)
    expect(motion.generate).not.toHaveBeenCalled()
  })

  it('ignores a late generated clip after cancellation', async () => {
    const pending = Promise.withResolvers<unknown>()
    motion.generate.mockReturnValueOnce(pending.promise)
    const store = useMotionPromptStore()
    const work = store.generate('A person jumps.')
    store.cancel()
    pending.resolve({ fps: 20 })
    expect(await work).toBeUndefined()
  })

  it('rechecks delivery after resolution and permits each clip only once', async () => {
    const store = useMotionPromptStore()
    const oldClip = await store.generate('A person jumps.')
    store.cancel()
    expect(store.consumeClip(oldClip!)).toBe(false)
    const clip = await store.generate('A person waves.')
    expect(store.consumeClip(clip!)).toBe(true)
    expect(store.consumeClip(clip!)).toBe(false)
  })
})
