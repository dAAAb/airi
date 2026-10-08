import { describe, expect, it } from 'vitest'

import { createLocalInstallerCards, GEMMA_MODEL, isLocalInstallerLaunch, parseLocalInstallerConfig, QWEN_MODEL, SARC_MODEL } from './local-installer-config'

const config = {
  models: ['sarc-taigi', 'gemma4', 'asr26', 'kokoro', 'kaedetai'],
  ollama: 'http://127.0.0.1:12434/v1/',
  asr: 'http://127.0.0.1:18001/v1/',
  speech: 'http://127.0.0.1:18884/v1/',
}

describe('explicit local installer boundary', () => {
  it('requires the build flag, exact origin, and explicit launch marker', () => {
    expect(isLocalInstallerLaunch('true', 'http://127.0.0.1:17900', '?localSetup=1')).toBe(true)
    expect(isLocalInstallerLaunch(undefined, 'http://127.0.0.1:17900', '?localSetup=1')).toBe(false)
    expect(isLocalInstallerLaunch('true', 'https://airi.moeru.ai', '?localSetup=1')).toBe(false)
    expect(isLocalInstallerLaunch('true', 'http://localhost:17900', '?localSetup=1')).toBe(false)
    expect(isLocalInstallerLaunch('true', 'http://127.0.0.1:17900', '')).toBe(false)
  })

  it('rejects remote or unexpected inference endpoints before importing', () => {
    for (const key of ['ollama', 'asr', 'speech', 'motion']) {
      expect(() => parseLocalInstallerConfig({ ...config, [key]: 'https://example.com/v1/' })).toThrow()
    }
    expect(() => parseLocalInstallerConfig({ ...config, models: ['unknown'] })).toThrow()
    expect(parseLocalInstallerConfig({ ...config, ollama: 'http://127.0.0.1:11434/v1/' }).ollama).toContain('11434')
  })

  it('requires the fixed local motion endpoint only when MotionGPT is selected', () => {
    expect(() => parseLocalInstallerConfig({ ...config, models: [...config.models, 'motiongpt'] })).toThrow()
    expect(() => parseLocalInstallerConfig({ ...config, motion: 'http://127.0.0.1:17905' })).toThrow()
    expect(parseLocalInstallerConfig({ ...config, models: [...config.models, 'motiongpt'], motion: 'http://127.0.0.1:17905' }).motion)
      .toBe('http://127.0.0.1:17905')
  })

  it('routes two roles to their own model and voice while sharing vision', () => {
    const cards = createLocalInstallerCards(parseLocalInstallerConfig(config), { ollama: 'brain', speech: 'mouth' })
    expect(cards.map(row => row.key)).toEqual(['mandarin', 'taigi'])
    expect(cards[0].card.extensions.airi.modules.consciousness.model).toBe(GEMMA_MODEL)
    expect(cards[1].card.extensions.airi.modules.consciousness.model).toBe(SARC_MODEL)
    expect(cards[0].card.extensions.airi.modules.speech).toEqual({ provider: 'mouth', model: 'kokoro', voice_id: 'zf_xiaobei' })
    expect(cards[1].card.extensions.airi.modules.speech).toEqual({ provider: 'mouth', model: 'taigi-hanzi', voice_id: 'taigi-demo-reference' })
    expect(cards[1].card.extensions.airi.modules.vision.model).toBe(GEMMA_MODEL)
    expect(cards.every(row => row.card.extensions.airi.modules.displayModelId === 'preset-vrm-1')).toBe(true)
  })

  it('never routes a partial selection to an absent speech or vision model', () => {
    const cards = createLocalInstallerCards(parseLocalInstallerConfig({ ...config, models: ['sarc-taigi'] }), { ollama: 'brain', speech: 'mouth' })
    expect(cards).toHaveLength(1)
    expect(cards[0].card.extensions.airi.modules.speech.provider).toBe('speech-noop')
    expect(cards[0].card.extensions.airi.modules.vision).toEqual({ provider: '', model: '' })
    expect(createLocalInstallerCards(parseLocalInstallerConfig({ ...config, models: ['asr26'] }), { ollama: 'brain', speech: 'mouth' })).toEqual([])
  })

  it('uses Qwen for lightweight conversation and vision with the same Kokoro voice', () => {
    const cards = createLocalInstallerCards(parseLocalInstallerConfig({ ...config, models: ['qwen', 'asr26', 'kokoro'] }), { ollama: 'brain', speech: 'mouth' })
    expect(cards.map(row => row.key)).toEqual(['qwen'])
    expect(cards[0].card.extensions.airi.modules.consciousness.model).toBe(QWEN_MODEL)
    expect(cards[0].card.extensions.airi.modules.vision.model).toBe(QWEN_MODEL)
    expect(cards[0].card.extensions.airi.modules.speech).toEqual({ provider: 'mouth', model: 'kokoro', voice_id: 'zf_xiaobei' })
  })

  it('prefers Gemma vision when both local vision models are selected', () => {
    const cards = createLocalInstallerCards(parseLocalInstallerConfig({ ...config, models: [...config.models, 'qwen'] }), { ollama: 'brain', speech: 'mouth' })
    expect(cards.find(row => row.key === 'qwen')?.card.extensions.airi.modules.consciousness.model).toBe(QWEN_MODEL)
    expect(cards.every(row => row.card.extensions.airi.modules.vision.model === GEMMA_MODEL)).toBe(true)
  })
})
