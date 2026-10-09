import type { GenerationProvider } from '@proj-airi/provider-inference'

import { streamFrom } from '@proj-airi/core-agent'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { builtinMotionPrompt, isEnglishMotionPrompt, localMotionPromptProvider, motionPromptInput, parseMotionPromptResponse, translateMotionPrompt } from './motion-prompt'

vi.mock('@proj-airi/core-agent', () => ({ chatMessagesToTurns: (messages: unknown) => messages, streamFrom: vi.fn() }))

function provider(baseURL = 'http://127.0.0.1:11434/v1/'): GenerationProvider {
  return { generation: model => ({ protocol: 'chat-completions', config: { baseURL, model, apiKey: '' } }) }
}

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('manual body-motion prompt normalization', () => {
  it('bounds input and detects Chinese or mixed input', () => {
    expect(motionPromptInput('  跳起來然後雙腳落地。  ')).toBe('跳起來然後雙腳落地。')
    expect(() => motionPromptInput('')).toThrow('empty')
    expect(() => motionPromptInput('x'.repeat(501))).toThrow('too-long')
    expect(isEnglishMotionPrompt('A person jumps and lands on both feet.')).toBe(true)
    expect(isEnglishMotionPrompt('jump 然後落地')).toBe(false)
    expect(isEnglishMotionPrompt('跤手攏伸直')).toBe(false)
  })

  it.each([
    ['跪地上', 'A person kneels on the ground.'],
    ['趴下來', 'A person lies down on their stomach on the floor.'],
    ['跌倒', 'A person falls to the ground.'],
  ])('matches only the complete built-in phrase %s with optional final punctuation', (input, expected) => {
    for (const suffix of ['', '。', '！', '？', '.', '!', '?', '！？'])
      expect(builtinMotionPrompt(`  ${input}${suffix}  `)).toBe(expected)
  })

  it.each(['不要跪地上', '跪地上再站起來', '用右膝跪地上', '請跪地上', '跪在地上', '跪地上，', '跪地上。然後站起來', '左手趴下來', '不要跌倒', '跌倒後爬起來', '跌 倒', 'kneel', ''])('does not match modified or compound descriptions: %s', (input) => {
    expect(builtinMotionPrompt(input)).toBeUndefined()
  })

  it('accepts only bounded English JSON and preserves direction without inventing translations', () => {
    expect(parseMotionPromptResponse('```json\n{"prompt":"A person waves their left hand."}\n```')).toBe('A person waves their left hand.')
    for (const raw of ['{"prompt":"一個人跳高。"}', 'Hello, here is your translation.', '{"prompt":""}', '{"prompt":"https://example.com"}', JSON.stringify({ prompt: 'x'.repeat(501) })])
      expect(() => parseMotionPromptResponse(raw)).toThrow('invalid-output')
    expect(() => parseMotionPromptResponse('{"prompt":null}')).toThrow('not-motion')
  })

  it('rejects cloud endpoints before streaming and blocks transport redirects or changed origins', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', request)
    for (const url of ['https://api.openai.com/v1/', 'http://127.0.0.1.evil.test/v1/', 'https://user:secret@localhost/v1/'])
      expect(() => localMotionPromptProvider(provider(url), 'same-model')).toThrow('local-model-required')
    const config = localMotionPromptProvider(provider(), 'same-model').generation('other-model').config
    expect(config.model).toBe('same-model')
    await config.fetch?.(new URL('http://127.0.0.1:11434/v1/chat/completions'), { method: 'POST' })
    expect(request.mock.calls[0][1]?.redirect).toBe('error')
    expect(() => config.fetch?.(new URL('https://api.openai.com/v1/chat/completions'), {})).toThrow('local-model-required')
    expect(request).toHaveBeenCalledTimes(1)
    expect(streamFrom).not.toHaveBeenCalled()
  })

  it('reuses the selected model, disables tools, and retries malformed translation once', async () => {
    vi.mocked(streamFrom)
      .mockImplementationOnce(async ({ options }) => { await options?.onStreamEvent?.({ type: 'text-delta', text: '跳高' }) })
      .mockImplementationOnce(async ({ options }) => { await options?.onStreamEvent?.({ type: 'text-delta', text: '{"prompt":"A person jumps upward and lands on both feet."}' }) })
    const controller = new AbortController()
    expect(await translateMotionPrompt('跳起來然後雙腳落地。', provider(), 'selected-model', controller.signal)).toContain('both feet')
    expect(streamFrom).toHaveBeenCalledTimes(2)
    expect(vi.mocked(streamFrom).mock.calls[0][0]).toMatchObject({ model: 'selected-model', options: { supportsTools: false, supportsContentArray: false, abortSignal: controller.signal } })
  })

  it('never sends untranslated output after two invalid replies or a canceled request', async () => {
    vi.mocked(streamFrom).mockImplementation(async ({ options }) => {
      await options?.onStreamEvent?.({ type: 'text-delta', text: '{"prompt":"跳高"}' })
    })
    await expect(translateMotionPrompt('跳高', provider(), 'chosen', new AbortController().signal)).rejects.toThrow('invalid-output')
    expect(streamFrom).toHaveBeenCalledTimes(2)
    const controller = new AbortController()
    controller.abort()
    await expect(translateMotionPrompt('跳高', provider(), 'chosen', controller.signal)).rejects.toThrow()
    expect(streamFrom).toHaveBeenCalledTimes(2)
  })
})
