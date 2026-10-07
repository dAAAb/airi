import { defineInvokeHandler } from '@moeru/eventa'
import { createContext } from '@moeru/eventa/adapters/electron/main'

// eslint-disable-next-line no-restricted-syntax -- Native ESM modules use explicit .mjs and .cjs runtime extensions.
import stateHelpers from './desktop-state.cjs'

// eslint-disable-next-line no-restricted-syntax -- Native ESM modules use explicit .mjs and .cjs runtime extensions.
import { desktopAdapterOptions, desktopGetState, desktopOpenSettings, desktopSetAlwaysOnTop, desktopSetClickThrough, desktopSetMode, desktopStateChanged } from './desktop-events.mjs'

const { isTrustedDesktopSender, parseFlag, parseMode } = stateHelpers

export function bindDesktopIpc(ipcMain, window, controller) {
  const adapter = createContext(ipcMain, window, { ...desktopAdapterOptions, onlySameWindow: true })
  const handlers = []
  function bind(contract, callback) {
    handlers.push(defineInvokeHandler(adapter.context, contract, (payload, options) => {
      if (!isTrustedDesktopSender(options?.raw?.ipcMainEvent, window.webContents))
        throw new Error('Desktop commands require the local AIRI main frame')
      return callback(payload)
    }))
  }
  bind(desktopGetState, () => controller.getState())
  bind(desktopSetMode, mode => controller.setMode(parseMode(mode)))
  bind(desktopSetAlwaysOnTop, flag => controller.setAlwaysOnTop(parseFlag(flag)))
  bind(desktopSetClickThrough, flag => controller.setClickThrough(parseFlag(flag)))
  bind(desktopOpenSettings, () => controller.openSettings())
  return {
    publish(state) {
      return adapter.context.emit(desktopStateChanged, state)
    },
    dispose() {
      for (const off of handlers)
        off()
      adapter.dispose()
    },
  }
}
