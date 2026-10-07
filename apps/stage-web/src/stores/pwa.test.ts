import type { App } from 'vue'

import { createPinia, disposePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h } from 'vue'

import { usePWAStore } from './pwa'

const registerSW = vi.hoisted(() => vi.fn(() => vi.fn()))

vi.mock('../modules/pwa', () => ({ registerSW }))
vi.mock('@proj-airi/stage-ui/components', () => ({ ToasterPWAUpdateReady: {} }))

describe('pwa registration', () => {
  let app: App | undefined
  let pinia: ReturnType<typeof createPinia>
  let container: HTMLDivElement

  beforeEach(() => {
    registerSW.mockClear()
    vi.stubEnv('SSR', false)
    vi.stubEnv('VITE_APP_TARGET_HUGGINGFACE_SPACE', 'false')
    pinia = createPinia()
    container = document.createElement('div')
    document.body.append(container)
  })

  afterEach(() => {
    app?.unmount()
    app = undefined
    disposePinia(pinia)
    container.remove()
    vi.unstubAllEnvs()
  })

  async function mountStore() {
    app = createApp(defineComponent({
      setup() {
        usePWAStore()
        return () => h('div')
      },
    }))
    app.use(pinia).mount(container)
    await vi.dynamicImportSettled()
  }

  it('never registers a service worker in the local Mac build', async () => {
    vi.stubEnv('VITE_AIRI_LOCAL_INSTALLER', 'true')
    await mountStore()
    expect(registerSW).not.toHaveBeenCalled()
  })

  it('keeps service worker registration for the normal web build', async () => {
    vi.stubEnv('VITE_AIRI_LOCAL_INSTALLER', 'false')
    await mountStore()
    expect(registerSW).toHaveBeenCalledOnce()
  })
})
