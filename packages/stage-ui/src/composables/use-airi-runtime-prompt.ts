import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { EMOTION_EmotionMotionName_value, EMOTION_VALUES } from '../constants/emotions'
import { localCharacterMotionPrompt } from '../constants/local-character-motion'
import { useAiriCardStore } from '../stores/modules/airi-card'

const RUNTIME_PROMPT_KEYS = [
  'base.prompt.emotion',
  'base.prompt.emoji',
  'base.prompt.suffix',
]

/** Returns the localized emotion and emoji prompt for each model request. */
export function useAiriRuntimePrompt() {
  const { locale, t, te } = useI18n()
  const cards = useAiriCardStore()

  return computed(() => {
    // Keep saved character identities unchanged; this is a capability of the local stage.
    if (cards.activeCard?.metadata?.localInstaller === 1)
      return localCharacterMotionPrompt
    if (!RUNTIME_PROMPT_KEYS.every(key => te(key, locale.value)))
      return ''

    return [
      t('base.prompt.emotion'),
      EMOTION_VALUES
        .map(emotion => `- ${emotion} (Emotion for feeling ${EMOTION_EmotionMotionName_value[emotion]})`)
        .join('\n'),
      t('base.prompt.suffix'),
      t('base.prompt.emoji'),
    ].join('\n\n')
  })
}
