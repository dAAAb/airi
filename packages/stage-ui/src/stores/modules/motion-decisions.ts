import type { NormalizedActPayload } from '@proj-airi/pipelines-audio'

import { useLocalStorageManualReset } from '@proj-airi/stage-shared/composables'
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { decisionToAct, LocalMotionDecisionClient, usableMotionAct } from '../../libs/motion-decisions'
import { useProviderConfigStore } from '../providers/config'
import { useSettings } from '../settings'
import { useMotionStore } from './motion'

interface DecisionTurn {
  turnId: string
  sessionId: string
  active: boolean
  racing: boolean
  winner?: 'local' | 'cloud'
  cloudConsumed?: boolean
  controller?: AbortController
}

export const useMotionDecisionsStore = defineStore('motion-decisions', () => {
  const enabled = useLocalStorageManualReset('settings/motion/decisions/enabled', false)
  const keySource = useLocalStorageManualReset('settings/motion/decisions/key-source', 'session')
  const hasSessionKey = ref(false)
  const status = ref<'idle' | 'pending' | 'local-won' | 'cloud-won' | 'deferred' | 'fallback' | 'missing-key' | 'unavailable'>('idle')
  const elapsedMs = ref<number>()
  const confidence = ref<number>()
  const cancellationEpoch = ref(0)
  const providers = useProviderConfigStore()
  const settings = useSettings()
  const motion = useMotionStore()
  let sessionKey = ''
  let current: DecisionTurn | undefined
  const managerAvailable = computed(() => typeof window !== 'undefined' && window.location.origin === 'http://127.0.0.1:17900')
  const openAiProviders = computed(() => Object.values(providers.providers)
    .filter(provider => provider.definitionId === 'openai' && typeof provider.config.apiKey === 'string' && provider.config.apiKey.trim())
    .map(provider => ({ id: provider.id, label: typeof provider.config.name === 'string' ? provider.config.name : `OpenAI · ${provider.id.slice(0, 8)}` })))

  function resolveApiKey() {
    if (keySource.value === 'session')
      return sessionKey
    const provider = providers.getProvider(keySource.value)
    return provider?.definitionId === 'openai' && typeof provider.config.apiKey === 'string' ? provider.config.apiKey : ''
  }

  function cancelTurn(turnId?: string) {
    if (!current || (turnId && current.turnId !== turnId))
      return
    current.active = false
    current.controller?.abort()
    cancellationEpoch.value++
    if (status.value === 'pending')
      status.value = 'idle'
  }

  function cancelSession(sessionId?: string) {
    if (!sessionId || current?.sessionId === sessionId)
      cancelTurn()
  }

  function setSessionKey(value: string) {
    cancelTurn()
    sessionKey = value.trim()
    hasSessionKey.value = sessionKey.length > 0
  }

  function disposition(turnId?: string): 'local' | 'race' | 'stale' | 'external' {
    if (!current || !turnId)
      return 'external'
    if (!current.active || current.turnId !== turnId)
      return 'stale'
    return current.racing ? 'race' : 'local'
  }

  function claimLocal(turnId: string, act: NormalizedActPayload) {
    if (!current || disposition(turnId) === 'stale' || current.winner
      || !usableMotionAct(act, motion.configured && motion.autoGenerate)) {
      return false
    }
    current.winner = 'local'
    current.controller?.abort()
    if (current.racing)
      status.value = 'local-won'
    return true
  }

  function consumeCloudMotion(turnId: string) {
    if (!current || current.turnId !== turnId || !current.active || current.winner !== 'cloud' || current.cloudConsumed)
      return false
    current.cloudConsumed = true
    return true
  }

  async function beginTurn(turnId: string, sessionId: string, text: string): Promise<NormalizedActPayload | undefined> {
    current?.controller?.abort()
    const turn: DecisionTurn = { turnId, sessionId, active: true, racing: enabled.value && settings.stageModelRenderer === 'vrm' }
    current = turn
    elapsedMs.value = undefined
    confidence.value = undefined
    status.value = 'idle'
    if (!turn.racing)
      return
    if (!managerAvailable.value) {
      status.value = 'unavailable'
      return
    }
    const apiKey = resolveApiKey()
    if (!apiKey) {
      status.value = 'missing-key'
      return
    }
    turn.controller = new AbortController()
    const controller = turn.controller
    const timeout = setTimeout(() => controller.abort(), 5000)
    status.value = 'pending'
    try {
      const result = await new LocalMotionDecisionClient(window.location.origin).decide(text, apiKey, controller.signal)
      if (current !== turn || !turn.active || turn.winner || controller.signal.aborted)
        return
      elapsedMs.value = result.elapsed_ms
      confidence.value = result.confidence
      const act = decisionToAct(result)
      if (!act || !usableMotionAct(act, motion.configured && motion.autoGenerate)) {
        status.value = 'deferred'
        return
      }
      turn.winner = 'cloud'
      status.value = 'cloud-won'
      return act
    }
    catch {
      // Never retain transport exceptions: provider errors can contain credential-bearing request details.
      if (current === turn && turn.active && !turn.winner)
        status.value = 'fallback'
    }
    finally { clearTimeout(timeout) }
  }

  watch([enabled, keySource, () => settings.stageModelRenderer, () => settings.stageModelSelected, () => keySource.value === 'session' ? '' : resolveApiKey(), () => motion.configured, () => motion.autoGenerate], () => cancelTurn(), { flush: 'sync' })

  return { enabled, keySource, hasSessionKey, openAiProviders, managerAvailable, status, elapsedMs, confidence, cancellationEpoch, setSessionKey, beginTurn, disposition, claimLocal, consumeCloudMotion, cancelTurn, cancelSession }
})
