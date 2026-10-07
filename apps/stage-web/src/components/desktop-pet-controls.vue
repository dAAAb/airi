<script setup lang="ts">
import { errorMessageFrom } from '@moeru/std'
import { useSettingsAudioDevice } from '@proj-airi/stage-ui/stores/settings'
import { GhostButton } from '@proj-airi/ui'
import { storeToRefs } from 'pinia'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useDesktopPet } from '../composables/desktop-pet'

const chatOpen = defineModel<boolean>('chatOpen', { default: false })
const viewOpen = defineModel<boolean>('viewOpen', { default: false })
const { t } = useI18n()
const router = useRouter()
const desktop = useDesktopPet()
const { state, busy, error } = desktop
const audioDevice = useSettingsAudioDevice()
const { enabled, error: audioError } = storeToRefs(audioDevice)
const microphonePending = ref(false)
const microphoneError = ref<string>()

async function toggleMicrophone() {
  microphoneError.value = undefined
  if (enabled.value) {
    enabled.value = false
    return
  }

  microphonePending.value = true
  try {
    await audioDevice.askPermission()
    enabled.value = true
  }
  catch (cause) {
    microphoneError.value = errorMessageFrom(cause)
  }
  finally {
    microphonePending.value = false
  }
}

async function openSettings() {
  await desktop.openSettings()
  if (!error.value)
    await router.push('/settings')
}
</script>

<template>
  <div class="desktop-pet-controls pointer-events-none absolute inset-0 z-30 flex flex-col justify-between p-2">
    <div class="desktop-pet-toolbar pointer-events-auto flex items-center self-end gap-1 rounded-xl bg-neutral-50/90 p-1 text-neutral-900 shadow-sm backdrop-blur-md dark:bg-neutral-900/90 dark:text-neutral-100">
      <div class="desktop-pet-drag-handle h-8 flex flex-1 items-center justify-center gap-1 px-2 text-xs" :title="t('stage.desktop-pet.move')">
        <span class="i-lucide:grip" aria-hidden="true" />
        <span>AIRI</span>
      </div>
      <GhostButton
        size="sm" icon="i-lucide:pin" :active="state.alwaysOnTop" :disabled="busy"
        :aria-pressed="state.alwaysOnTop" :aria-label="t('stage.desktop-pet.always-on-top')" :title="t('stage.desktop-pet.always-on-top')"
        @click="desktop.setAlwaysOnTop(!state.alwaysOnTop)"
      />
      <GhostButton
        size="sm" icon="i-lucide:mouse-pointer-2-off" :disabled="busy"
        :aria-label="t('stage.desktop-pet.click-through')" :title="t('stage.desktop-pet.click-through-hint')"
        @click="desktop.setClickThrough(true)"
      />
      <GhostButton
        size="sm" icon="i-lucide:maximize-2" :disabled="busy"
        :aria-label="t('stage.desktop-pet.window')" :title="t('stage.desktop-pet.window')"
        @click="desktop.setMode('window')"
      />
    </div>

    <div class="flex flex-col items-center gap-2">
      <p v-if="error || microphoneError || audioError" role="alert" class="pointer-events-auto max-w-full rounded-xl bg-neutral-50/95 p-3 text-sm text-red-700 dark:bg-neutral-900/95 dark:text-red-300">
        {{ error || microphoneError || audioError }}
      </p>
      <div class="desktop-pet-toolbar pointer-events-auto flex items-center gap-1 rounded-xl bg-neutral-50/90 p-1 text-neutral-900 shadow-sm backdrop-blur-md dark:bg-neutral-900/90 dark:text-neutral-100">
        <GhostButton
          size="md" :icon="enabled ? 'i-lucide:mic' : 'i-lucide:mic-off'" :active="enabled" :loading="microphonePending"
          :aria-pressed="enabled" :aria-label="t(enabled ? 'stage.desktop-pet.mic-off' : 'stage.desktop-pet.mic-on')"
          :title="t(enabled ? 'stage.desktop-pet.listening' : 'stage.desktop-pet.mic-on')"
          @click="toggleMicrophone"
        />
        <GhostButton
          size="md" icon="i-lucide:messages-square" :active="chatOpen" :aria-pressed="chatOpen"
          :aria-label="t('stage.desktop-pet.chat')" :title="t('stage.desktop-pet.chat')"
          @click="chatOpen = !chatOpen"
        />
        <GhostButton
          size="md" icon="i-lucide:move" :active="viewOpen" :aria-pressed="viewOpen"
          :aria-label="t('stage.desktop-pet.adjust-view')" :title="t('stage.desktop-pet.adjust-view')"
          @click="viewOpen = !viewOpen"
        />
        <GhostButton
          size="md" icon="i-lucide:settings" :disabled="busy"
          :aria-label="t('stage.desktop-pet.settings')" :title="t('stage.desktop-pet.settings')"
          @click="openSettings"
        />
      </div>
      <span v-if="enabled" class="pointer-events-none rounded-full bg-neutral-50/90 px-2 py-0.5 text-xs text-neutral-900 dark:bg-neutral-900/90 dark:text-neutral-100">
        {{ t('stage.desktop-pet.listening') }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.desktop-pet-toolbar {
  opacity: 0.55;
  transition: opacity 160ms ease;
}

.desktop-pet-controls:hover .desktop-pet-toolbar,
.desktop-pet-controls:focus-within .desktop-pet-toolbar {
  opacity: 1;
}

.desktop-pet-drag-handle {
  -webkit-app-region: drag;
  user-select: none;
}

button {
  -webkit-app-region: no-drag;
}

@media (prefers-reduced-motion: reduce) {
  .desktop-pet-toolbar {
    transition: none;
  }
}
</style>
