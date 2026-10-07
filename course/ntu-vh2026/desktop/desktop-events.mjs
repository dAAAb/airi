import { defineEventa, defineInvokeEventa } from '@moeru/eventa'

export const desktopGetState = defineInvokeEventa('airi-local:desktop:get-state')
export const desktopSetMode = defineInvokeEventa('airi-local:desktop:set-mode')
export const desktopSetAlwaysOnTop = defineInvokeEventa('airi-local:desktop:set-always-on-top')
export const desktopSetClickThrough = defineInvokeEventa('airi-local:desktop:set-click-through')
export const desktopOpenSettings = defineInvokeEventa('airi-local:desktop:open-settings')
export const desktopStateChanged = defineEventa('airi-local:desktop:state-changed')
export const desktopAdapterOptions = Object.freeze({
  messageEventName: 'airi-local-desktop-eventa',
  errorEventName: 'airi-local-desktop-eventa-error',
})
