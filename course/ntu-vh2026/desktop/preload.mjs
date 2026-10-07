import { defineInvoke } from '@moeru/eventa'
import { createContext } from '@moeru/eventa/adapters/electron/renderer'
import { contextBridge, ipcRenderer } from 'electron'

// eslint-disable-next-line no-restricted-syntax -- Native ESM modules use explicit .mjs and .cjs runtime extensions.
import { desktopAdapterOptions, desktopGetState, desktopOpenSettings, desktopSetAlwaysOnTop, desktopSetClickThrough, desktopSetMode, desktopStateChanged } from './desktop-events.mjs'

const adapter = createContext(ipcRenderer, desktopAdapterOptions)
const getState = defineInvoke(adapter.context, desktopGetState)
const setMode = defineInvoke(adapter.context, desktopSetMode)
const setAlwaysOnTop = defineInvoke(adapter.context, desktopSetAlwaysOnTop)
const setClickThrough = defineInvoke(adapter.context, desktopSetClickThrough)
const openSettings = defineInvoke(adapter.context, desktopOpenSettings)

function invoke(method, value) {
  return method(value, { signal: AbortSignal.timeout(5000) })
}

contextBridge.exposeInMainWorld('airiDesktop', Object.freeze({
  getState: () => invoke(getState),
  setMode: mode => invoke(setMode, mode),
  setAlwaysOnTop: flag => invoke(setAlwaysOnTop, flag),
  setClickThrough: flag => invoke(setClickThrough, flag),
  openSettings: () => invoke(openSettings),
  onStateChanged: (callback) => {
    if (typeof callback !== 'function')
      throw new TypeError('State listener must be a function')
    return adapter.context.on(desktopStateChanged, event => callback(event.body))
  },
}))

window.addEventListener('unload', () => adapter.dispose(), { once: true })
