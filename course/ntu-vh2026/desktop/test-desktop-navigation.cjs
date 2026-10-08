const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

const { ORIGIN } = require('./policy.cjs')

function createController() {
  const states = []
  const preferences = { version: 1, mode: 'pet', alwaysOnTop: true }
  const display = { id: 1, workArea: { x: 0, y: 24, width: 1440, height: 876 } }
  const screen = Object.assign(new EventEmitter(), {
    getPrimaryDisplay: () => display,
    getAllDisplays: () => [display],
  })
  const window = new EventEmitter()
  let currentUrl = `${ORIGIN}/setup/`
  let bounds = { x: 0, y: 24, width: 1280, height: 876 }
  window.webContents = Object.assign(new EventEmitter(), { getURL: () => currentUrl })
  window.getNormalBounds = () => ({ ...bounds })
  window.setBounds = next => bounds = { ...next }
  window.isDestroyed = window.isMinimized = window.isMaximized = () => false
  for (const name of ['setIgnoreMouseEvents', 'setFocusable', 'setMinimumSize', 'setResizable', 'setMaximizable', 'setFullScreenable', 'setBackgroundColor', 'setHasShadow', 'setAlwaysOnTop', 'setWindowButtonVisibility', 'setVisibleOnAllWorkspaces', 'blur', 'show', 'focus'])
    window[name] = () => {}

  const electron = {
    app: { setName() {}, setPath() {}, getPath: () => '/virtual-airi-test', requestSingleInstanceLock: () => false, quit() {} },
    ipcMain: {},
    Menu: { buildFromTemplate: value => value, setApplicationMenu() {} },
    screen,
  }
  const context = {
    module: { exports: {} },
    console,
    setTimeout,
    clearTimeout,
    require(name) {
      if (name === 'electron')
        return electron
      if (name === 'node:fs')
        return { readFileSync: () => JSON.stringify(preferences), mkdirSync() {}, writeFileSync() {}, renameSync() {} }
      if (name === './desktop-ipc.mjs') {
        return { bindDesktopIpc: () => ({
          publish(state) {
            states.push({ ...state })
            return Promise.resolve()
          },
          dispose() {},
        }) }
      }
      return require(name)
    },
  }
  const source = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf8')
  vm.runInNewContext(`${source}\nmodule.exports = DesktopWindowController`, context)
  const Controller = context.module.exports
  const controller = new Controller(window)
  function navigate(url, { mainFrame = true, updateUrl = true } = {}) {
    if (updateUrl)
      currentUrl = url
    window.webContents.emit('did-navigate-in-page', {}, url, mainFrame)
  }
  return { controller, navigate, states, window }
}

test('settings stays open through Vue Router replacing the current home history entry', () => {
  const { controller, navigate, states } = createController()
  navigate(`${ORIGIN}/`)
  assert.equal(controller.getState().mode, 'pet')
  states.length = 0
  controller.openSettings()
  assert.equal(controller.getState().mode, 'window')

  // Vue Router writes the current entry before pushing the settings destination.
  navigate(`${ORIGIN}/`)
  navigate(`${ORIGIN}/settings`)
  navigate(`${ORIGIN}/settings/modules/motion`)
  assert.equal(controller.getState().mode, 'window')
  assert.ok(states.every(state => state.mode === 'window'))
  assert.equal(controller.preferences.mode, 'pet')

  navigate(`${ORIGIN}/`)
  assert.equal(controller.getState().mode, 'pet')
})

test('main-frame event URL controls mode even when getURL still contains the preceding route', () => {
  const { controller, navigate } = createController()
  navigate(`${ORIGIN}/`, { updateUrl: false })
  assert.equal(controller.getState().mode, 'pet')
  navigate(`${ORIGIN}/settings`, { updateUrl: false })
  assert.equal(controller.getState().mode, 'window')
  assert.throws(() => controller.setMode('pet'), /角色主畫面/)
  navigate(`${ORIGIN}/`, { mainFrame: false, updateUrl: false })
  assert.equal(controller.getState().mode, 'window')
  navigate(`${ORIGIN}/`, { updateUrl: false })
  assert.equal(controller.getState().mode, 'pet')
})

test('home query changes do not restore pet and an explicit window preference survives a round trip', () => {
  const { controller, navigate } = createController()
  navigate(`${ORIGIN}/`)
  controller.openSettings()
  navigate(`${ORIGIN}/?localSetup=1`)
  navigate(`${ORIGIN}/#stage`)
  assert.equal(controller.getState().mode, 'window')
  controller.setMode('window')
  navigate(`${ORIGIN}/settings`)
  navigate(`${ORIGIN}/`)
  assert.equal(controller.getState().mode, 'window')
  assert.equal(controller.preferences.mode, 'window')
})
