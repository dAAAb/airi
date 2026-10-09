<script setup lang="ts">
import type { MotionRuntimeDevice } from '@proj-airi/stage-ui/libs/motion-generation'

import { WidgetStage } from '@proj-airi/stage-ui/components/scenes'
import { useMotionStore } from '@proj-airi/stage-ui/stores/modules/motion'
import { useMotionDecisionsStore } from '@proj-airi/stage-ui/stores/modules/motion-decisions'
import { useMotionPromptStore } from '@proj-airi/stage-ui/stores/modules/motion-prompt'
import { Button, FieldCheckbox, FieldInput, FieldSelect } from '@proj-airi/ui'
import { storeToRefs } from 'pinia'
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const motion = useMotionStore()
const decisions = useMotionDecisionsStore()
const manualPrompt = useMotionPromptStore()
const { translating, originalInput, actualPrompt, translatedBy, normalizationSource, errorCode: promptError } = storeToRefs(manualPrompt)
const { enabled: decisionsEnabled, keySource, hasSessionKey, openAiProviders, managerAvailable, status: decisionStatus, elapsedMs, confidence } = storeToRefs(decisions)
const sessionKeyInput = ref('')
const keyOptions = computed(() => [
  { value: 'session', label: t('settings.pages.modules.motion.decisions.session-key') },
  ...openAiProviders.value.map(provider => ({ value: provider.id, label: provider.label })),
])
const { enabled, autoGenerate, endpoint, runtimePreference, available, configured, busy: motionBusy, status, lastError, healthDetails, lastClip } = storeToRefs(motion)
const busy = computed(() => translating.value || motionBusy.value)
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
  decisions.cancelTurn()
  manualPrompt.cancel()
  preview.value?.stopGeneratedMotion()
}

function applySessionKey() {
  decisions.setSessionKey(sessionKeyInput.value)
  sessionKeyInput.value = ''
}

function play() {
  if (lastClip.value)
    playbackRejected.value = !preview.value?.playGeneratedMotion(lastClip.value)
}

async function generate() {
  playbackRejected.value = false
  preview.value?.stopGeneratedMotion()
  const clip = await manualPrompt.generate(prompt.value)
  if (clip && manualPrompt.consumeClip(clip))
    playbackRejected.value = !preview.value?.playGeneratedMotion(clip)
}

watch(prompt, () => manualPrompt.clear(), { flush: 'sync' })
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
    <p v-if="translating" role="status" aria-live="polite">
      {{ t('settings.pages.modules.motion.prompt-normalization.translating') }}
    </p>
    <p v-if="promptError" role="alert" :class="['rounded-lg', 'bg-red-100', 'p-3', 'text-sm', 'text-red-800', 'dark:bg-red-950', 'dark:text-red-200']">
      {{ t(`settings.pages.modules.motion.prompt-normalization.errors.${promptError}`) }}
    </p>
    <div v-if="actualPrompt" :class="['flex', 'flex-col', 'gap-2', 'rounded-lg', 'bg-neutral-100', 'p-3', 'text-sm', 'dark:bg-neutral-800']">
      <p>{{ t('settings.pages.modules.motion.prompt-normalization.original') }} {{ originalInput }}</p>
      <p :class="['font-medium']">
        {{ t('settings.pages.modules.motion.prompt-normalization.actual') }}
      </p>
      <p :class="['whitespace-pre-wrap', 'break-words']">
        {{ actualPrompt }}
      </p>
      <p v-if="normalizationSource === 'builtin'">
        {{ t('settings.pages.modules.motion.prompt-normalization.builtin') }}
      </p>
      <p v-else-if="translatedBy">
        {{ t('settings.pages.modules.motion.prompt-normalization.model', { model: translatedBy }) }}
      </p>
    </div>
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
    <section :class="['flex', 'flex-col', 'gap-4', 'border-t', 'border-neutral-200', 'pt-6', 'dark:border-neutral-700']">
      <FieldCheckbox
        v-model="decisionsEnabled" :disabled="!available || !managerAvailable"
        :label="t('settings.pages.modules.motion.decisions.enable')"
        :description="t('settings.pages.modules.motion.decisions.description')"
      />
      <p :class="['text-sm', 'text-neutral-500', 'dark:text-neutral-400']">
        {{ t('settings.pages.modules.motion.decisions.privacy') }}
      </p>
      <p v-if="!managerAvailable" role="status">
        {{ t('settings.pages.modules.motion.decisions.manager-required') }}
      </p>
      <template v-if="decisionsEnabled && managerAvailable">
        <FieldSelect
          v-model="keySource" :options="keyOptions"
          :label="t('settings.pages.modules.motion.decisions.key-source')"
          :description="t('settings.pages.modules.motion.decisions.key-description')"
        />
        <template v-if="keySource === 'session'">
          <FieldInput
            v-model="sessionKeyInput" type="password" autocomplete="off"
            :label="t('settings.pages.modules.motion.decisions.api-key')"
            :description="t('settings.pages.modules.motion.decisions.session-description')"
          />
          <div :class="['flex', 'flex-wrap', 'gap-3']">
            <Button :disabled="!sessionKeyInput.trim()" @click="applySessionKey">
              {{ t('settings.pages.modules.motion.decisions.use-key') }}
            </Button>
            <Button :disabled="!hasSessionKey" @click="decisions.setSessionKey('')">
              {{ t('settings.pages.modules.motion.decisions.clear-key') }}
            </Button>
            <span v-if="hasSessionKey">{{ t('settings.pages.modules.motion.decisions.key-ready') }}</span>
          </div>
        </template>
        <p role="status" aria-live="polite">
          {{ t(`settings.pages.modules.motion.decisions.status.${decisionStatus}`) }}
          <span v-if="elapsedMs !== undefined"> · {{ elapsedMs.toFixed(0) }} ms</span>
          <span v-if="confidence !== undefined"> · {{ t('settings.pages.modules.motion.decisions.confidence', { value: confidence.toFixed(2) }) }}</span>
        </p>
        <p :class="['text-sm', 'text-neutral-500', 'dark:text-neutral-400']">
          {{ t('settings.pages.modules.motion.decisions.race') }}
        </p>
      </template>
    </section>
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
