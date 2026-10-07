import en from '@proj-airi/i18n/locales/en'

import { PiniaColada } from '@pinia/colada'
import { MotionPlugin } from '@vueuse/motion'
import { createPinia, disposePinia } from 'pinia'
import { expect, it, vi } from 'vitest'
import { createApp, h, nextTick, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

import CardEditor from '../../../../stage-pages/src/pages/settings/airi-card/components/CardEditor.vue'

import { getAiriCardEditorModuleSettings } from '../../services/airi-card-editor'
import { useProviderConfigStore } from '../providers/config'
import { useAiriCardStore } from './airi-card'
import { useSpeechStore } from './speech'

it.each(['openai-compatible-audio-speech', 'local-speech-hub-instance'])('saves custom speech IDs without catalog entries for %s', async (providerId) => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json({ data: [], voices: [] })))
  const pinia = createPinia()
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const cardId = ref('')
  const container = document.createElement('div')
  document.body.append(container)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/',
      component: {
        setup() {
          useSpeechStore()
          return () => h(CardEditor, { cardId: cardId.value, initialSection: 'modules' })
        },
      },
    }],
  })
  const app = createApp({ render: () => h(RouterView) })
  app.use(pinia).use(PiniaColada).use(MotionPlugin).use(i18n).use(router).mount(container)
  try {
    await router.push('/')
    await router.isReady()
    await useProviderConfigStore(pinia).ensureProvider(providerId, 'openai-compatible-audio-speech', {
      apiKey: '',
      baseUrl: 'http://127.0.0.1:8884/v1/',
    })
    const cards = useAiriCardStore(pinia)
    cardId.value = await cards.addCard({
      name: 'Local speech test',
      version: '1.0',
      description: '',
      extensions: { airi: { modules: { speech: { provider: providerId, model: 'tts-1', voice_id: 'alloy' } } } },
    }, 'scratch')
    const field = (key: 'model' | 'voice') => container.querySelector<HTMLInputElement>(`input[aria-label="${i18n.global.t(`settings.pages.card.speech.${key}`)}"]`)
    await vi.waitFor(() => expect(field('model')?.value).toBe('tts-1'))

    async function fill(key: 'model' | 'voice', value: string) {
      const input = field(key)
      expect(input).toBeTruthy()
      input!.value = value
      input!.dispatchEvent(new Event('input', { bubbles: true }))
      await nextTick()
    }

    // No catalog item and no Enter key are needed. Saving preserves each raw ID.
    for (const [model, voice] of [['kokoro', 'zf_xiaobei'], ['taigi-hanzi', 'taigi-demo-reference'], ['', '']]) {
      await fill('model', model)
      expect(field('voice')?.value).toBe('')
      await fill('voice', voice)
      const save = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.trim() === i18n.global.t('settings.pages.card.save'))
      expect(save).toBeTruthy()
      save!.click()
      await vi.waitFor(() => {
        const saved = cards.getCard(cardId.value)
        expect(saved).toBeDefined()
        expect(getAiriCardEditorModuleSettings(saved!).speech).toEqual({ provider: providerId, model, voice_id: voice })
      })
    }
  }
  finally {
    app.unmount()
    disposePinia(pinia)
    container.remove()
    vi.unstubAllGlobals()
    localStorage.clear()
  }
})
