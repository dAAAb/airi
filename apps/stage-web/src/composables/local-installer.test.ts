import type { AiriCard } from '@proj-airi/stage-ui/types/airiCard'

import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  providerRows: new Map<string, { definitionId: string, config?: Record<string, unknown> }>(),
  cardRows: new Map<string, AiriCard>(),
  hearing: { activeTranscriptionProvider: '', activeTranscriptionModel: '', autoSendEnabled: false },
  motion: { enabled: false, autoGenerate: false, endpoint: '' },
  vision: { useForChat: false, ollamaThinkingEnabled: true },
  markSetupCompleted: vi.fn(),
  activateCard: vi.fn(),
  setReasoning: vi.fn(),
}))

vi.mock('@proj-airi/stage-ui/stores/providers/config', () => ({
  useProviderConfigStore: () => ({
    getProvider: (id: string) => mocks.providerRows.get(id),
    ensureProvider: (id: string, definitionId: string) => {
      if (!mocks.providerRows.has(id))
        mocks.providerRows.set(id, { definitionId })
    },
    updateProviderConfig: async (id: string, config: Record<string, unknown>) => {
      const row = mocks.providerRows.get(id)
      if (row)
        row.config = config
    },
    markProviderAdded: vi.fn(),
  }),
}))
vi.mock('@proj-airi/stage-ui/stores/modules/airi-card', () => ({
  useAiriCardStore: () => ({
    getCard: (id: string) => mocks.cardRows.get(id),
    addCard: async (card: AiriCard) => {
      const id = `generated-${mocks.cardRows.size}`
      mocks.cardRows.set(id, card)
      return id
    },
    activateCard: mocks.activateCard,
    updateCard: async (id: string, card: AiriCard) => mocks.cardRows.set(id, card),
  }),
}))
vi.mock('@proj-airi/stage-ui/stores/modules/hearing', () => ({ useHearingStore: () => mocks.hearing }))
vi.mock('@proj-airi/stage-ui/stores/modules/motion', () => ({ useMotionStore: () => mocks.motion }))
vi.mock('@proj-airi/stage-ui/stores/modules/vision', () => ({ useVisionStore: () => mocks.vision }))
vi.mock('@proj-airi/stage-ui/stores/modules/consciousness-settings', () => ({ useConsciousnessSettingsStore: () => ({ setReasoning: mocks.setReasoning }) }))
vi.mock('@proj-airi/stage-ui/stores/onboarding', () => ({ useOnboardingStore: () => ({ markSetupCompleted: mocks.markSetupCompleted }) }))

const config = {
  models: ['gemma4', 'sarc-taigi', 'asr26', 'kokoro', 'kaedetai'],
  ollama: 'http://127.0.0.1:12434/v1/',
  asr: 'http://127.0.0.1:18001/v1/',
  speech: 'http://127.0.0.1:18884/v1/',
}

describe('local installer store integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    const storage = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    })
    mocks.providerRows.clear()
    mocks.cardRows.clear()
    Object.assign(mocks.motion, { enabled: false, autoGenerate: false, endpoint: '' })
    vi.stubEnv('VITE_AIRI_LOCAL_INSTALLER', 'true')
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:17900', search: '?localSetup=1', href: 'http://127.0.0.1:17900/?localSetup=1' })
    vi.stubGlobal('history', { state: null, replaceState: vi.fn() })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => config })))
  })

  it('preserves unrelated user data and reuses its own edited cards', async () => {
    mocks.providerRows.set('user-provider', { definitionId: 'ollama', config: { baseUrl: 'http://localhost:11434/v1/' } })
    mocks.cardRows.set('default', { name: 'My existing character', version: '1', extensions: { airi: { modules: { consciousness: { provider: '', model: '' }, vision: { provider: '', model: '' }, speech: { provider: '', model: '', voice_id: '' } }, agents: {} } } })
    const { useLocalInstaller } = await import('./local-installer')
    await useLocalInstaller().applyLocalInstallerConfiguration()
    expect(mocks.cardRows.size).toBe(3)
    expect(mocks.providerRows.size).toBe(4)
    const taigi = [...mocks.cardRows.values()].find(card => card.metadata?.localInstallerRole === 'taigi')
    expect(taigi).toBeDefined()
    if (taigi)
      taigi.name = 'My edited Taigi'
    await useLocalInstaller().applyLocalInstallerConfiguration()
    expect(mocks.cardRows.size).toBe(3)
    expect(taigi?.name).toBe('My edited Taigi')
    expect(mocks.cardRows.get('default')?.name).toBe('My existing character')
    expect(mocks.providerRows.get('user-provider')?.config?.baseUrl).toBe('http://localhost:11434/v1/')
    expect(mocks.hearing.activeTranscriptionModel).toBe('breeze-asr-26-mlx')
    expect(mocks.hearing.autoSendEnabled).toBe(true)
    expect(mocks.vision.useForChat).toBe(true)
    expect(mocks.vision.ollamaThinkingEnabled).toBe(false)
    expect(mocks.markSetupCompleted).toHaveBeenCalledTimes(2)
  })

  it('does not fetch or write on an ordinary app visit', async () => {
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:17900', search: '' })
    const { useLocalInstaller } = await import('./local-installer')
    await useLocalInstaller().applyLocalInstallerConfiguration()
    expect(fetch).not.toHaveBeenCalled()
    expect(mocks.providerRows.size).toBe(0)
    expect(mocks.cardRows.size).toBe(0)
  })

  it('rejects invalid server configuration before creating providers', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ...config, speech: 'https://remote.test/v1/' }) })))
    const { useLocalInstaller } = await import('./local-installer')
    await expect(useLocalInstaller().applyLocalInstallerConfiguration()).rejects.toThrow()
    expect(mocks.providerRows.size).toBe(0)
    expect(mocks.cardRows.size).toBe(0)
    expect(mocks.markSetupCompleted).not.toHaveBeenCalled()
  })

  it('disconnects unselected services when reconfiguring its own role', async () => {
    const { useLocalInstaller } = await import('./local-installer')
    await useLocalInstaller().applyLocalInstallerConfiguration()
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ...config, models: ['sarc-taigi'] }) })))
    await useLocalInstaller().applyLocalInstallerConfiguration()
    const taigi = [...mocks.cardRows.values()].find(card => card.metadata?.localInstallerRole === 'taigi')
    expect(taigi?.extensions.airi.modules.speech.provider).toBe('speech-noop')
    expect(taigi?.extensions.airi.modules.vision.provider).toBe('')
  })

  it('enables the selected MotionGPT service without opting into automatic generation', async () => {
    const { useLocalInstaller } = await import('./local-installer')
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ...config, models: [...config.models, 'motiongpt'], motion: 'http://127.0.0.1:17905' }) })))
    await useLocalInstaller().applyLocalInstallerConfiguration()
    expect(mocks.motion).toEqual({ enabled: true, autoGenerate: false, endpoint: 'http://127.0.0.1:17905' })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => config })))
    await useLocalInstaller().applyLocalInstallerConfiguration()
    expect(mocks.motion.enabled).toBe(false)
  })
})
