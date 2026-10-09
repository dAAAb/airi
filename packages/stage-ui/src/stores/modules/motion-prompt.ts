import type { GeneratedMotionClip } from '@proj-airi/stage-ui-three/composables/vrm'

import type { MotionPromptErrorCode } from '../../libs/motion-prompt'

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import { builtinMotionPrompt, isEnglishMotionPrompt, MotionPromptError, motionPromptInput, translateMotionPrompt } from '../../libs/motion-prompt'
import { useSettings } from '../settings'
import { useConsciousnessStore } from './consciousness'
import { useMotionStore } from './motion'

async function waitForTranslation<T>(work: Promise<T>, signal: AbortSignal): Promise<T> {
  signal.throwIfAborted()
  let onAbort: () => void = () => {}
  const cancellation = new Promise<never>((_resolve, reject) => {
    onAbort = () => reject(signal.reason)
    signal.addEventListener('abort', onAbort, { once: true })
  })
  try {
    return await Promise.race([work, cancellation])
  }
  finally { signal.removeEventListener('abort', onAbort) }
}

export const useMotionPromptStore = defineStore('motion-prompt', () => {
  const consciousness = useConsciousnessStore()
  const motion = useMotionStore()
  const settings = useSettings()
  const translating = ref(false)
  const originalInput = ref('')
  const actualPrompt = ref('')
  const translatedBy = ref('')
  const normalizationSource = ref<'direct' | 'builtin' | 'local-model'>('direct')
  const errorCode = ref<MotionPromptErrorCode>()
  let operation = 0
  let controller: AbortController | undefined
  let readyClip: GeneratedMotionClip | undefined

  function cancel() {
    operation++
    controller?.abort()
    controller = undefined
    readyClip = undefined
    translating.value = false
    motion.cancel()
  }

  function consumeClip(clip: GeneratedMotionClip) {
    if (readyClip !== clip)
      return false
    readyClip = undefined
    return true
  }

  function clear() {
    cancel()
    originalInput.value = ''
    actualPrompt.value = ''
    translatedBy.value = ''
    normalizationSource.value = 'direct'
    errorCode.value = undefined
  }

  async function generate(input: string) {
    clear()
    if (!motion.configured)
      return
    const id = operation
    const model = consciousness.activeModel || consciousness.customModelName
    const providerId = consciousness.activeProvider
    const avatar = settings.stageModelSelected
    const currentController = new AbortController()
    controller = currentController
    let timeout: ReturnType<typeof setTimeout> | undefined
    try {
      const text = motionPromptInput(input)
      originalInput.value = text
      const builtin = builtinMotionPrompt(text)
      const needsTranslation = !builtin && !isEnglishMotionPrompt(text)
      let prompt = builtin ?? text
      if (needsTranslation) {
        if (!model || !providerId)
          throw new MotionPromptError('local-model-required')
        translating.value = true
        timeout = setTimeout(() => currentController.abort(new MotionPromptError('timeout')), 60_000)
        const provider = await waitForTranslation(consciousness.getChatProviderInstance(providerId), currentController.signal)
        currentController.signal.throwIfAborted()
        prompt = await waitForTranslation(translateMotionPrompt(text, provider, model, currentController.signal), currentController.signal)
      }
      if (id !== operation || currentController.signal.aborted || avatar !== settings.stageModelSelected)
        return
      clearTimeout(timeout)
      translating.value = false
      translatedBy.value = needsTranslation ? model : ''
      normalizationSource.value = builtin ? 'builtin' : needsTranslation ? 'local-model' : 'direct'
      actualPrompt.value = prompt
      const clip = await motion.generate(prompt)
      if (id === operation && !currentController.signal.aborted && avatar === settings.stageModelSelected) {
        readyClip = clip
        return clip
      }
    }
    catch (error) {
      if (id === operation) {
        const failure = currentController.signal.aborted ? currentController.signal.reason : error
        errorCode.value = failure instanceof MotionPromptError ? failure.code : 'failed'
      }
    }
    finally {
      clearTimeout(timeout)
      if (id === operation)
        translating.value = false
    }
  }

  watch([() => consciousness.activeProvider, () => consciousness.activeModel, () => consciousness.customModelName, () => settings.stageModelSelected, () => settings.stageModelRenderer, () => motion.enabled, () => motion.endpoint], clear, { flush: 'sync' })

  return { translating, originalInput, actualPrompt, translatedBy, normalizationSource, errorCode, generate, consumeClip, cancel, clear }
})
