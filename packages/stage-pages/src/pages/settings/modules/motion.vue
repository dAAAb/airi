<script setup lang="ts">
import type { MotionRuntimeDevice } from '@proj-airi/stage-ui/libs/motion-generation'

import { WidgetStage } from '@proj-airi/stage-ui/components/scenes'
import { useMotionStore } from '@proj-airi/stage-ui/stores/modules/motion'
import { Button, FieldCheckbox, FieldInput, FieldSelect } from '@proj-airi/ui'
import { storeToRefs } from 'pinia'
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const motion = useMotionStore()
const { enabled, autoGenerate, endpoint, runtimePreference, available, configured, busy, status, lastError, healthDetails, lastClip } = storeToRefs(motion)
const preview = ref<InstanceType<typeof WidgetStage>>()
const previewState = ref<'pending' | 'loading' | 'mounted'>('pending')
const prompt = ref('A person raises their right hand and waves hello.')
const playbackRejected = ref(false)
const runtimeOptions = computed(() => (['auto', ...(healthDetails.value?.available_devices ?? [])] as MotionRuntimeDevice[]).map(value => ({
  value,
  label: t(`settings.pages.modules.motion.runtime-devices.${value}`),
})))
const selectedRuntime = computed({
  get: () => runtimePreference.value,
  set: (value: MotionRuntimeDevice) => { void motion.setRuntimePreference(value) },
})

function stop() {
  motion.cancel()
  preview.value?.stopGeneratedMotion()
}

function play() {
  if (lastClip.value)
    playbackRejected.value = !preview.value?.playGeneratedMotion(lastClip.value)
}

async function generate() {
  playbackRejected.value = false
  preview.value?.stopGeneratedMotion()
  const clip = await motion.generate(prompt.value)
  if (clip)
    play()
}

watch(enabled, (value) => {
  if (!value)
    stop()
})
onUnmounted(stop)
</script>

<template>
  <div :class="['flex', 'flex-col', 'gap-6', 'pb-8']">
    <p :class="['text-sm', 'text-neutral-500', 'dark:text-neutral-400']">
      {{ t('settings.pages.modules.motion.intro') }}
    </p>
    <p v-if="!available" role="status" :class="['rounded-xl', 'bg-neutral-100', 'p-4', 'dark:bg-neutral-800']">
      {{ t('settings.pages.modules.motion.vrm-only') }}
    </p>
    <FieldCheckbox
      v-model="enabled" :disabled="!available"
      :label="t('settings.pages.modules.motion.enable')"
      :description="t('settings.pages.modules.motion.enable-description')"
    />
    <FieldCheckbox
      v-model="autoGenerate" :disabled="!available || !enabled"
      :label="t('settings.pages.modules.motion.auto')"
      :description="t('settings.pages.modules.motion.auto-description')"
    />
    <FieldInput
      v-model="endpoint" :disabled="busy"
      :label="t('settings.pages.modules.motion.endpoint')"
      :description="t('settings.pages.modules.motion.endpoint-description')"
    />
    <div :class="['flex', 'flex-wrap', 'items-center', 'gap-3']">
      <Button :disabled="busy || !available" @click="motion.checkHealth()">
        {{ t('settings.pages.modules.motion.check') }}
      </Button>
      <span role="status" aria-live="polite">{{ t(`settings.pages.modules.motion.status.${status}`) }}</span>
    </div>
    <p v-if="healthDetails" :class="['text-sm', 'text-neutral-500']">
      {{ healthDetails.model }} · {{ healthDetails.device }} · {{ healthDetails.fps }} fps
      · {{ t('settings.pages.modules.motion.load-time', { seconds: healthDetails.load_seconds.toFixed(2) }) }}
    </p>
    <FieldSelect
      v-model="selectedRuntime" :options="runtimeOptions" :disabled="busy || !available || !healthDetails"
      :label="t('settings.pages.modules.motion.runtime')"
      :description="t('settings.pages.modules.motion.runtime-description')"
    />
    <p v-if="healthDetails?.auto_fallback_reason" role="status" :class="['text-sm', 'text-amber-700', 'dark:text-amber-300']">
      {{ t('settings.pages.modules.motion.runtime-fallback') }} {{ healthDetails.auto_fallback_reason }}
    </p>
    <p v-if="lastError" role="alert" :class="['rounded-lg', 'bg-red-100', 'p-3', 'text-sm', 'text-red-800', 'dark:bg-red-950', 'dark:text-red-200']">
      {{ t('settings.pages.modules.motion.service-error') }} {{ lastError }}
    </p>
    <FieldInput
      v-model="prompt" :single-line="false" :disabled="busy || !available"
      :label="t('settings.pages.modules.motion.prompt')"
      :description="t('settings.pages.modules.motion.prompt-description')"
    />
    <div :class="['flex', 'flex-wrap', 'gap-3']">
      <Button color="primary" variant="primary" :disabled="busy || !configured || previewState !== 'mounted' || !prompt.trim()" @click="generate">
        {{ t('settings.pages.modules.motion.generate') }}
      </Button>
      <Button :disabled="busy || !configured || !lastClip || previewState !== 'mounted'" @click="play">
        {{ t('settings.pages.modules.motion.replay') }}
      </Button>
      <Button :disabled="!available" @click="stop">
        {{ t('settings.pages.modules.motion.stop') }}
      </Button>
    </div>
    <p v-if="playbackRejected" role="alert">
      {{ t('settings.pages.modules.motion.playback-rejected') }}
    </p>
    <div v-if="available" :class="['relative', 'h-110', 'overflow-hidden', 'rounded-xl', 'border', 'border-neutral-200', 'dark:border-neutral-700']">
      <WidgetStage ref="preview" v-model:state="previewState" />
    </div>
    <p :class="['text-sm', 'text-neutral-500', 'dark:text-neutral-400']">
      {{ t('settings.pages.modules.motion.limits') }}
    </p>
  </div>
</template>

<route lang="yaml">
meta:
  layout: settings
  titleKey: settings.pages.modules.motion.title
  subtitleKey: settings.title
  stageTransition:
    name: slide
    pageSpecificAvailable: true
</route>
