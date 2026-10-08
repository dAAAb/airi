import type { NormalizedActPayload } from '@proj-airi/pipelines-audio'
import type { GeneratedMotionClip } from '@proj-airi/stage-ui-three/composables/vrm'

import type { MotionRuntimeDevice, MotionServiceHealth } from '../../libs/motion-generation'

import { errorMessageFrom } from '@moeru/std'
import { useLocalStorageManualReset } from '@proj-airi/stage-shared/composables'
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'

import { LocalMotionClient, motionServiceEndpoint } from '../../libs/motion-generation'
import { useSettings } from '../settings'

export const useMotionStore = defineStore('motion', () => {
  const enabled = useLocalStorageManualReset('settings/motion/enabled', false)
  const autoGenerate = useLocalStorageManualReset('settings/motion/auto-generate', false)
  const endpoint = useLocalStorageManualReset('settings/motion/endpoint', 'http://127.0.0.1:17905')
  const runtimePreference = useLocalStorageManualReset<MotionRuntimeDevice>('settings/motion/runtime', 'auto')
  const status = ref<'idle' | 'checking' | 'switching' | 'ready' | 'generating' | 'generated' | 'error'>('idle')
  const busy = computed(() => ['checking', 'switching', 'generating'].includes(status.value))
  const lastError = ref('')
  const healthDetails = shallowRef<MotionServiceHealth>()
  const lastClip = shallowRef<GeneratedMotionClip>()
  const settings = useSettings()
  let operation = 0
  let activePrompt = ''
  let controller: AbortController | undefined
  const available = computed(() => settings.stageModelRenderer === 'vrm')
  const configured = computed(() => {
    try {
      return enabled.value && available.value && !!motionServiceEndpoint(endpoint.value)
    }
    catch { return false }
  })

  function cancel() {
    operation++
    controller?.abort()
    controller = undefined
    if (busy.value)
      status.value = 'idle'
  }

  async function synchronizeRuntime(client: LocalMotionClient, signal: AbortSignal, id: number) {
    let details = await client.health(AbortSignal.any([signal, AbortSignal.timeout(5000)]))
    if (id !== operation)
      return
    healthDetails.value = details
    if (!details.ready)
      throw new Error('Motion model is not ready.')
    if (details.busy)
      throw new Error('Motion service is busy. Wait, then test the service again.')
    if (runtimePreference.value !== 'auto' && !details.available_devices.includes(runtimePreference.value))
      throw new Error(`Motion runtime is unavailable: ${runtimePreference.value}`)
    if (details.selected_device !== runtimePreference.value) {
      status.value = 'switching'
      details = await client.setRuntime(runtimePreference.value, signal)
      if (id !== operation)
        return
      healthDetails.value = details
      if (!details.ready || details.busy || details.selected_device !== runtimePreference.value)
        throw new Error('Motion runtime switch did not finish. Test the service again.')
    }
    return details
  }

  async function checkHealth() {
    cancel()
    const id = operation
    controller = new AbortController()
    const currentController = controller
    const timeout = setTimeout(() => currentController.abort(), 180_000)
    status.value = 'checking'
    lastError.value = ''
    try {
      const details = await synchronizeRuntime(new LocalMotionClient(endpoint.value), currentController.signal, id)
      if (!details)
        return
      status.value = 'ready'
    }
    catch (error) {
      if (id === operation) {
        lastError.value = errorMessageFrom(error) ?? 'Motion service unavailable.'
        status.value = 'error'
      }
    }
    finally { clearTimeout(timeout) }
  }

  async function setRuntimePreference(device: MotionRuntimeDevice) {
    if (busy.value)
      return
    runtimePreference.value = device
    await checkHealth()
  }

  async function generate(prompt: string) {
    if (!configured.value || (busy.value && activePrompt === prompt.trim()))
      return
    cancel()
    activePrompt = prompt.trim()
    const id = operation
    const model = settings.stageModelSelected
    controller = new AbortController()
    const currentController = controller
    const timeout = setTimeout(() => currentController.abort(), 180_000)
    status.value = 'checking'
    lastError.value = ''
    try {
      const client = new LocalMotionClient(endpoint.value)
      const details = await synchronizeRuntime(client, currentController.signal, id)
      if (!details)
        return
      status.value = 'generating'
      const clip = await client.generate(prompt, currentController.signal)
      if (id !== operation || !configured.value || settings.stageModelSelected !== model)
        return
      lastClip.value = clip
      status.value = 'generated'
      return clip
    }
    catch (error) {
      if (id === operation) {
        lastError.value = errorMessageFrom(error) ?? 'Motion generation failed.'
        status.value = 'error'
      }
    }
    finally { clearTimeout(timeout) }
  }

  function generateFromAct(act: NormalizedActPayload) {
    if (!autoGenerate.value || act.motion !== 'generate' || !act.motionPrompt)
      return Promise.resolve(undefined)
    return generate(act.motionPrompt)
  }

  watch([enabled, autoGenerate, endpoint, () => settings.stageModelSelected, () => settings.stageModelRenderer], cancel)
  watch(endpoint, () => {
    healthDetails.value = undefined
  })

  return { enabled, autoGenerate, endpoint, runtimePreference, available, configured, busy, status, lastError, healthDetails, lastClip, checkHealth, setRuntimePreference, generate, generateFromAct, cancel }
})
