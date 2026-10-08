import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAiriRuntimePrompt } from './use-airi-runtime-prompt'

const cardsMock = vi.hoisted(() => ({ activeCard: undefined as { metadata: Record<string, unknown>, systemPrompt?: string } | undefined }))
const motionMock = vi.hoisted(() => ({ configured: false, autoGenerate: false }))

vi.mock('../stores/modules/airi-card', () => ({ useAiriCardStore: () => cardsMock }))
vi.mock('../stores/modules/motion', () => ({ useMotionStore: () => motionMock }))

const i18nMock = vi.hoisted(() => ({
  hasTranslation: vi.fn<(key: string, locale: string) => boolean>(),
  locale: { value: 'en' },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    locale: i18nMock.locale,
    t: (key: string) => key,
    te: (key: string, currentLocale: string) => i18nMock.hasTranslation(key, currentLocale),
  }),
}))

describe('useAiriRuntimePrompt', () => {
  beforeEach(() => {
    cardsMock.activeCard = undefined
    motionMock.configured = false
    motionMock.autoGenerate = false
  })

  it('adds the local ACT contract even in combined locales without changing a saved prompt', () => {
    i18nMock.hasTranslation.mockReturnValue(false)
    cardsMock.activeCard = { metadata: { localInstaller: 1 }, systemPrompt: '使用台語短句' }
    const prompt = useAiriRuntimePrompt().value
    expect(prompt).toContain('<|ACT {"emotion":"情緒名稱","motion":"動作名稱"}|>')
    expect(prompt).toContain('遇到難過的消息選 sad 和 idle')
    expect(cardsMock.activeCard.systemPrompt).toBe('使用台語短句')
  })

  it('does not change other imported cards based on a truthy metadata string', () => {
    i18nMock.hasTranslation.mockReturnValue(false)
    cardsMock.activeCard = { metadata: { localInstaller: '1' } }
    expect(useAiriRuntimePrompt().value).toBe('')
  })

  it('returns no prompt for a locale that still uses the combined prompt', () => {
    i18nMock.hasTranslation.mockReturnValue(false)

    expect(useAiriRuntimePrompt().value).toBe('')
  })

  it('assembles the emotion and emoji prompt for a split locale', () => {
    i18nMock.hasTranslation.mockReturnValue(true)

    const prompt = useAiriRuntimePrompt().value

    expect(prompt).toContain('base.prompt.emotion')
    expect(prompt).toContain('base.prompt.suffix')
    expect(prompt).toContain('base.prompt.emoji')
  })

  it('advertises generated motion only after the VRM module and automatic generation are enabled', () => {
    cardsMock.activeCard = { metadata: { localInstaller: 1 } }
    motionMock.configured = true
    expect(useAiriRuntimePrompt().value).not.toContain('motionPrompt')
    motionMock.autoGenerate = true
    expect(useAiriRuntimePrompt().value).toContain('"motion":"generate"')
    expect(useAiriRuntimePrompt().value).toContain('motionPrompt')
    motionMock.configured = false
    expect(useAiriRuntimePrompt().value).not.toContain('motionPrompt')
  })
})
