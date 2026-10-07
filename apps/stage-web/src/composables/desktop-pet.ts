import { errorMessageFrom } from '@moeru/std'
import { createSharedComposable } from '@vueuse/core'
import { computed, onScopeDispose, readonly, ref, watch } from 'vue'

export interface DesktopPetState {
  mode: 'window' | 'pet'
  alwaysOnTop: boolean
  clickThrough: boolean
}

export interface AiriDesktopBridge {
  getState: () => Promise<DesktopPetState>
  setMode: (mode: DesktopPetState['mode']) => Promise<void>
  setAlwaysOnTop: (enabled: boolean) => Promise<void>
  setClickThrough: (enabled: boolean) => Promise<void>
  openSettings: () => Promise<void>
  onStateChanged: (callback: (state: DesktopPetState) => void) => () => void
}

declare global {
  interface Window {
    airiDesktop?: AiriDesktopBridge
  }
}

export const useDesktopPet = createSharedComposable(() => {
  const bridge = window.airiDesktop
  const available = Boolean(bridge)
  const state = ref<DesktopPetState>({
    mode: available && new URLSearchParams(window.location.search).get('desktopPet') === '1' ? 'pet' : 'window',
    alwaysOnTop: false,
    clickThrough: false,
  })
  const busy = ref(false)
  const error = ref<string>()
  const isDesktopPet = computed(() => available && state.value.mode === 'pet')

  watch(isDesktopPet, (enabled) => {
    document.documentElement.classList.toggle('airi-desktop-pet', enabled)
    document.documentElement.classList.toggle('airi-desktop-window', available && !enabled)
  }, { immediate: true })
  onScopeDispose(() => {
    document.documentElement.classList.remove('airi-desktop-pet', 'airi-desktop-window')
  })

  if (bridge) {
    const unsubscribe = bridge.onStateChanged(next => state.value = next)
    void bridge.getState().then(next => state.value = next).catch((cause) => {
      error.value = errorMessageFrom(cause)
    })
    onScopeDispose(unsubscribe)
  }

  async function run(action: (desktop: AiriDesktopBridge) => Promise<void>) {
    if (!bridge || busy.value)
      return

    busy.value = true
    error.value = undefined
    try {
      await action(bridge)
      state.value = await bridge.getState()
    }
    catch (cause) {
      error.value = errorMessageFrom(cause)
    }
    finally {
      busy.value = false
    }
  }

  return {
    available,
    isDesktopPet,
    state: readonly(state),
    busy: readonly(busy),
    error: readonly(error),
    setMode: (mode: DesktopPetState['mode']) => run(desktop => desktop.setMode(mode)),
    setAlwaysOnTop: (enabled: boolean) => run(desktop => desktop.setAlwaysOnTop(enabled)),
    setClickThrough: (enabled: boolean) => run(desktop => desktop.setClickThrough(enabled)),
    openSettings: () => run(desktop => desktop.openSettings()),
  }
})
