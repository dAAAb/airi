import { useAiriCardStore } from '@proj-airi/stage-ui/stores/modules/airi-card'
import { useConsciousnessSettingsStore } from '@proj-airi/stage-ui/stores/modules/consciousness-settings'
import { useHearingStore } from '@proj-airi/stage-ui/stores/modules/hearing'
import { useVisionStore } from '@proj-airi/stage-ui/stores/modules/vision'
import { useOnboardingStore } from '@proj-airi/stage-ui/stores/onboarding'
import { useProviderConfigStore } from '@proj-airi/stage-ui/stores/providers/config'
import { cloneDeep } from 'es-toolkit'
import { nanoid } from 'nanoid'
import { literal, object, optional, parse, pipe, regex, string } from 'valibot'

import { createLocalInstallerCards, isLocalInstallerLaunch, parseLocalInstallerConfig } from './local-installer-config'

const markerKey = 'airi-local-installer-v1'
const ownedProviderId = pipe(string(), regex(/^local-installer-[\w-]+$/))
const markerSchema = object({
  version: literal(1),
  providers: object({ ollama: ownedProviderId, asr: ownedProviderId, speech: ownedProviderId }),
  cards: object({ mandarin: optional(string()), taigi: optional(string()), qwen: optional(string()) }),
})

class LocalInstallerSession {
  async readConfig() {
    const response = await fetch('/api/airi-config', { cache: 'no-store', signal: AbortSignal.timeout(10_000) })
    if (!response.ok)
      throw new Error(`Local installer configuration failed: HTTP ${response.status}`)
    return parseLocalInstallerConfig(await response.json())
  }

  readMarker() {
    const saved = localStorage.getItem(markerKey)
    return saved
      ? parse(markerSchema, JSON.parse(saved))
      : parse(markerSchema, {
          version: 1,
          providers: {
            ollama: `local-installer-ollama-${nanoid()}`,
            asr: `local-installer-asr-${nanoid()}`,
            speech: `local-installer-speech-${nanoid()}`,
          },
          cards: {},
        })
  }

  saveMarker(marker: ReturnType<LocalInstallerSession['readMarker']>) {
    localStorage.setItem(markerKey, JSON.stringify(marker))
  }
}

/** Bind stores during component setup, before startup awaits leave the i18n context. */
export function useLocalInstaller() {
  const providers = useProviderConfigStore()
  const cards = useAiriCardStore()
  const hearing = useHearingStore()
  const vision = useVisionStore()
  const settings = useConsciousnessSettingsStore()
  const onboarding = useOnboardingStore()

  async function applyLocalInstallerConfiguration() {
    if (!isLocalInstallerLaunch(import.meta.env.VITE_AIRI_LOCAL_INSTALLER, location.origin, location.search))
      return

    const session = new LocalInstallerSession()
    const config = await session.readConfig()
    const marker = session.readMarker()
    const definitions = {
      ollama: 'ollama',
      asr: 'openai-compatible-audio-transcription',
      speech: 'openai-compatible-audio-speech',
    } as const

    // Validate every owned identity before changing any persisted provider.
    for (const key of ['ollama', 'asr', 'speech'] as const) {
      const existing = providers.getProvider(marker.providers[key])
      if (existing && existing.definitionId !== definitions[key])
        throw new Error('Local installer provider identity changed. Existing settings were preserved.')
    }
    session.saveMarker(marker)
    for (const key of ['ollama', 'asr', 'speech'] as const) {
      const id = marker.providers[key]
      providers.ensureProvider(id, definitions[key])
      await providers.updateProviderConfig(id, {
        apiKey: 'local',
        baseUrl: config[key],
        ...(key === 'asr' ? { model: 'breeze-asr-26-mlx', language: 'zh' } : {}),
      }, 'configured')
      providers.markProviderAdded(id)
    }

    const plannedCards = createLocalInstallerCards(config, marker.providers)
    for (const { key, card } of plannedCards) {
      const existingId = marker.cards[key]
      const existing = existingId ? cards.getCard(existingId) : undefined
      if (!existing || existing.metadata?.localInstaller !== 1 || existing.metadata?.localInstallerRole !== key) {
        marker.cards[key] = await cards.addCard(card, 'import')
        session.saveMarker(marker)
      }
      else if (existingId) {
        // Reconnect owned roles to the selected services. Keep their name, prompt, and body.
        const updated = cloneDeep(existing)
        Object.assign(updated.extensions.airi.modules, {
          consciousness: card.extensions.airi.modules.consciousness,
          speech: card.extensions.airi.modules.speech,
          vision: card.extensions.airi.modules.vision,
        })
        await cards.updateCard(existingId, updated)
      }
    }

    if (config.models.includes('asr26')) {
      hearing.activeTranscriptionProvider = marker.providers.asr
      hearing.activeTranscriptionModel = 'breeze-asr-26-mlx'
      hearing.autoSendEnabled = true
    }
    if (config.models.includes('gemma4') || config.models.includes('qwen')) {
      vision.useForChat = true
      vision.ollamaThinkingEnabled = false
    }
    await settings.setReasoning(false)
    const preferred = plannedCards.find(row => row.key === 'mandarin')
      ?? plannedCards.find(row => row.key === 'qwen')
      ?? plannedCards[0]
    if (preferred) {
      const id = marker.cards[preferred.key]
      if (id)
        await cards.activateCard(id)
      onboarding.markSetupCompleted()
    }
    const url = new URL(location.href)
    url.searchParams.delete('localSetup')
    history.replaceState(history.state, '', url)
  }

  return { applyLocalInstallerConfiguration }
}
