const { spawn } = require('node:child_process')
const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const process = require('node:process')

const { app, BrowserWindow, dialog, globalShortcut, ipcMain, Menu, screen, session, shell, systemPreferences } = require('electron')

const { bindDesktopIpc } = require('./desktop-ipc.mjs')
const { clampBounds, isStageHome, modeForRouteChange, sanitizePreferences } = require('./desktop-state.cjs')
const { ORIGIN, isLocalPage, microphoneAllowed, isExternalWebLink, isOfflineRequestAllowed } = require('./policy.cjs')

app.setName('AIRI Local')
app.setPath('userData', path.join(app.getPath('appData'), 'AIRI Local Classroom'))
const ownsInstance = app.requestSingleInstanceLock()
let window
let manager
let closing = false
let cleanupDone = false
let offline = false
let desktop
const RECOVER_SHORTCUT = 'CommandOrControl+Alt+P'

async function verifyFreePort() {
  await new Promise((resolve, reject) => {
    const probe = net.createServer()
    probe.once('error', () => reject(new Error('本機連接埠 17900 已被使用。AIRI Local 不會接管或關閉其他服務。')))
    probe.listen(17900, '127.0.0.1', () => probe.close(resolve))
  })
}

async function startManager() {
  // Manual Electron distributions can report isPackaged=false before rebranding.
  // The build's own identifier is the authority for its fixed Resources directory.
  const buildInfoPath = path.join(process.resourcesPath, 'build-info.json')
  const packagedCourse = fs.existsSync(buildInfoPath)
    && JSON.parse(fs.readFileSync(buildInfoPath, 'utf8')).app_id === 'ai.daaaab.airi-local-classroom'
  const resources = packagedCourse ? process.resourcesPath : (!app.isPackaged && process.env.AIRI_LOCAL_RESOURCES)
  if (!resources)
    throw new Error('開發模式需要 AIRI_LOCAL_RESOURCES 指向完整的本機資源目錄。')
  const python = path.join(resources, 'runtimes/python/bin/python3')
  const entry = path.join(resources, 'installer/manager.py')
  for (const required of [python, entry, path.join(resources, 'web/index.html'), path.join(resources, 'payload-manifest.json')]) {
    if (!fs.existsSync(required))
      throw new Error(`App 缺少必要檔案：${path.relative(resources, required)}`)
  }
  offline = JSON.parse(fs.readFileSync(path.join(resources, 'payload-manifest.json'), 'utf8')).offline === true
  await verifyFreePort()
  const dataDir = path.join(app.getPath('userData'), 'local')
  fs.mkdirSync(path.join(dataDir, 'logs'), { recursive: true })
  const log = fs.openSync(path.join(dataDir, 'logs/manager.log'), 'a')
  const env = { ...process.env, PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1', PYTHONUNBUFFERED: '1' }
  delete env.PYTHONHOME
  delete env.PYTHONPATH
  manager = spawn(python, [entry, '--resources', resources, '--data-dir', dataDir], {
    stdio: ['ignore', log, log],
    env,
    cwd: resources,
  })
  fs.closeSync(log)
  let spawnError
  manager.once('error', (error) => {
    spawnError = error
  })
  manager.once('exit', () => {
    if (!closing && window) {
      dialog.showErrorBox('本機服務已停止', 'AIRI Local 的管理服務已停止。請重新開啟 App；詳細原因在本機 manager.log。')
      app.quit()
    }
  })
  for (let attempt = 0; attempt < 100; attempt++) {
    if (spawnError)
      throw spawnError
    if (manager.exitCode !== null || manager.signalCode !== null)
      throw new Error('本機 Python 管理服務無法啟動，請查看 App 資料目錄內的 manager.log。')
    try {
      const response = await fetch(`${ORIGIN}/api/bootstrap`, { signal: AbortSignal.timeout(800) })
      const bootstrap = await response.json()
      if (response.ok && bootstrap.origin === ORIGIN && typeof bootstrap.token === 'string')
        return
    }
    catch { /* The owned child is still starting. */ }
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  throw new Error('本機管理服務啟動逾時，請查看 manager.log。')
}

async function stopManager() {
  if (!manager || manager.exitCode !== null || manager.signalCode !== null)
    return
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      // Signal only this ChildProcess. Never discover a PID from a port or name.
      if (manager.exitCode === null && manager.signalCode === null)
        manager.kill('SIGKILL')
      resolve()
    }, 60000)
    manager.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
    manager.kill('SIGTERM')
  })
}

async function configureSession() {
  const localSession = session.fromPartition('persist:airi-local-classroom')
  // A desktop update owns its web assets. Remove only stale PWA caches for
  // this origin; character cards, conversations and settings stay in storage.
  await localSession.clearStorageData({ origin: ORIGIN, storages: ['serviceworkers', 'cachestorage'] })
  if (offline) {
    localSession.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*'] }, (details, callback) => {
      callback({ cancel: !isOfflineRequestAllowed(details.url) })
    })
  }
  localSession.setPermissionCheckHandler((webContents, permission, requestingOrigin, details) =>
    microphoneAllowed(webContents?.getURL(), permission, requestingOrigin, [details.mediaType]))
  localSession.setPermissionRequestHandler(async (webContents, permission, callback, details) => {
    const allowed = microphoneAllowed(webContents.getURL(), permission, details.requestingUrl, details.mediaTypes)
    if (!allowed)
      return callback(false)
    if (process.platform === 'darwin') {
      try {
        return callback(await systemPreferences.askForMediaAccess('microphone'))
      }
      catch {
        return callback(false)
      }
    }
    callback(true)
  })
  return localSession
}

class DesktopWindowController {
  constructor(target) {
    this.window = target
    this.mode = 'window'
    this.routeUrl = target.webContents.getURL()
    this.clickThrough = false
    this.switching = false
    this.file = path.join(app.getPath('userData'), 'desktop-window.json')
    try {
      this.preferences = sanitizePreferences(JSON.parse(fs.readFileSync(this.file, 'utf8')))
    }
    catch {
      this.preferences = sanitizePreferences(undefined)
    }
    this.bridge = bindDesktopIpc(ipcMain, target, this)
    this.displayChanged = () => this.clampToDisplay()
    for (const event of ['display-added', 'display-removed', 'display-metrics-changed'])
      screen.on(event, this.displayChanged)
    target.on('move', () => this.queueSave())
    target.on('resize', () => this.queueSave())
    target.webContents.on('did-navigate', (_event, url) => this.syncRoute(url))
    target.webContents.on('did-navigate-in-page', (_event, url, isMainFrame) => {
      if (isMainFrame)
        this.syncRoute(url)
    })
    target.on('closed', () => {
      clearTimeout(this.saveTimer)
      for (const event of ['display-added', 'display-removed', 'display-metrics-changed'])
        screen.off(event, this.displayChanged)
      this.bridge.dispose()
    })
    this.applyWindowMode()
  }

  workAreas() {
    const primary = screen.getPrimaryDisplay()
    return [primary, ...screen.getAllDisplays().filter(display => display.id !== primary.id)].map(display => display.workArea)
  }

  getState() {
    return {
      mode: this.mode,
      alwaysOnTop: this.mode === 'pet' && this.preferences.alwaysOnTop,
      clickThrough: this.clickThrough,
    }
  }

  publish() {
    this.updateMenu()
    this.bridge.publish(this.getState()).catch(error => console.error('Desktop state delivery failed:', error))
    return this.getState()
  }

  recordBounds() {
    if (!this.window.isDestroyed() && !this.window.isMinimized())
      this.preferences[this.mode === 'pet' ? 'petBounds' : 'windowBounds'] = this.window.getNormalBounds()
  }

  save() {
    clearTimeout(this.saveTimer)
    this.recordBounds()
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true })
      const temporary = `${this.file}.tmp`
      fs.writeFileSync(temporary, JSON.stringify(this.preferences, null, 2), { mode: 0o600 })
      fs.renameSync(temporary, this.file)
    }
    catch (error) {
      console.error('Desktop preferences were not saved:', error)
    }
  }

  queueSave() {
    if (this.switching || closing)
      return
    clearTimeout(this.saveTimer)
    this.saveTimer = setTimeout(() => this.save(), 250)
  }

  applyWindowMode() {
    const pet = this.mode === 'pet'
    const bounds = clampBounds(this.preferences[pet ? 'petBounds' : 'windowBounds'], this.mode, this.workAreas())
    this.switching = true
    this.window.setIgnoreMouseEvents(false)
    this.window.setFocusable(true)
    this.clickThrough = false
    this.window.setMinimumSize(1, 1)
    this.window.setResizable(!pet)
    this.window.setMaximizable(!pet)
    this.window.setFullScreenable(false)
    if (this.window.isMaximized())
      this.window.unmaximize()
    this.window.setBounds(bounds)
    this.window.setMinimumSize(Math.min(bounds.width, pet ? 300 : 800), Math.min(bounds.height, pet ? 400 : 600))
    this.window.setBackgroundColor(pet ? '#00000000' : '#101217')
    this.window.setHasShadow(!pet)
    this.window.setAlwaysOnTop(pet && this.preferences.alwaysOnTop, 'floating')
    if (process.platform === 'darwin') {
      this.window.setWindowButtonVisibility(!pet)
      this.window.setVisibleOnAllWorkspaces(pet, { visibleOnFullScreen: false })
    }
    this.switching = false
  }

  setMode(mode, remember = true) {
    if (mode === 'pet' && !isStageHome(this.routeUrl))
      throw new Error('請先回到角色主畫面，再開啟桌寵模式。')
    if (remember)
      this.preferences.mode = mode
    if (this.mode !== mode) {
      this.recordBounds()
      this.mode = mode
      this.applyWindowMode()
    }
    else if (this.clickThrough) {
      this.setClickThrough(false)
    }
    this.save()
    return this.publish()
  }

  setAlwaysOnTop(flag) {
    this.preferences.alwaysOnTop = flag
    this.window.setAlwaysOnTop(this.mode === 'pet' && flag, 'floating')
    this.save()
    return this.publish()
  }

  setClickThrough(flag) {
    if (flag && this.mode !== 'pet')
      throw new Error('滑鼠穿透只適用於桌寵模式。')
    this.clickThrough = flag
    if (flag) {
      this.window.blur()
      this.window.setFocusable(false)
      this.window.setIgnoreMouseEvents(true, { forward: true })
    }
    else {
      this.window.setIgnoreMouseEvents(false)
      this.window.setFocusable(true)
    }
    return this.publish()
  }

  openSettings() {
    this.setMode('window', false)
    this.recover()
    return this.getState()
  }

  syncRoute(url) {
    // History updates on the same home route must not undo opening settings.
    const next = modeForRouteChange(this.mode, this.preferences.mode, this.routeUrl, url)
    this.routeUrl = url
    if (next !== this.mode)
      this.setMode(next, false)
    else
      this.publish()
  }

  clampToDisplay() {
    if (this.window.isDestroyed())
      return
    const current = this.window.getNormalBounds()
    const bounds = clampBounds(current, this.mode, this.workAreas())
    this.switching = true
    this.window.setMinimumSize(1, 1)
    this.window.setBounds(bounds)
    this.window.setMinimumSize(Math.min(bounds.width, this.mode === 'pet' ? 300 : 800), Math.min(bounds.height, this.mode === 'pet' ? 400 : 600))
    this.switching = false
    this.save()
  }

  recover() {
    if (this.window.isDestroyed())
      return
    this.setClickThrough(false)
    if (this.window.isMinimized())
      this.window.restore()
    this.clampToDisplay()
    this.window.show()
    this.window.focus()
  }

  updateMenu() {
    const home = isStageHome(this.routeUrl)
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { label: 'AIRI Local', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'quit' }] },
      { role: 'editMenu' },
      { label: '桌寵', submenu: [
        { label: '桌寵模式', type: 'checkbox', checked: this.mode === 'pet', enabled: home, click: () => this.setMode(this.mode === 'pet' ? 'window' : 'pet') },
        { label: '保持在最上層', type: 'checkbox', checked: this.preferences.alwaysOnTop, enabled: this.mode === 'pet', click: item => this.setAlwaysOnTop(item.checked) },
        { label: '滑鼠穿透', type: 'checkbox', checked: this.clickThrough, enabled: this.mode === 'pet', click: item => this.setClickThrough(item.checked) },
        { type: 'separator' },
        { label: '恢復操作／找回角色', accelerator: RECOVER_SHORTCUT, click: () => this.recover() },
        { label: '回到一般視窗', click: () => {
          this.setMode('window')
          this.recover()
        } },
      ] },
      { label: 'View', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }] },
    ]))
  }
}

async function createWindow() {
  const localSession = await configureSession()
  window = new BrowserWindow({
    title: 'AIRI Local',
    width: 1280,
    height: 900,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    transparent: true,
    backgroundColor: '#101217',
    webPreferences: {
      session: localSession,
      preload: path.join(__dirname, 'preload.cjs'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      nodeIntegrationInWorker: false,
      webviewTag: false,
      backgroundThrottling: false,
    },
  })
  window.webContents.on('will-navigate', (event, url) => {
    if (!isLocalPage(url)) {
      event.preventDefault()
      if (isExternalWebLink(url))
        shell.openExternal(url).catch(() => {})
    }
  })
  window.webContents.on('will-attach-webview', event => event.preventDefault())
  window.webContents.on('will-redirect', (event, url) => {
    if (!isLocalPage(url))
      event.preventDefault()
  })
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isExternalWebLink(url))
      shell.openExternal(url).catch(() => {})
    return { action: 'deny' }
  })
  desktop = new DesktopWindowController(window)
  desktop.updateMenu()
  window.once('ready-to-show', () => window.show())
  window.on('close', () => desktop.save())
  window.on('closed', () => {
    window = undefined
    desktop = undefined
  })
  const shortcutRegistered = globalShortcut.register(RECOVER_SHORTCUT, () => desktop?.recover())
  if (!shortcutRegistered)
    console.warn('Desktop recovery shortcut is already in use. Use the AIRI Dock icon or desktop menu to recover interaction.')
  window.loadURL(`${ORIGIN}/setup/`)
}

if (!ownsInstance) {
  app.quit()
}
else {
  app.on('second-instance', () => {
    desktop?.recover()
  })
  app.on('activate', () => desktop?.recover())
  app.on('will-quit', () => globalShortcut.unregisterAll())
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', (event) => {
    if (cleanupDone)
      return
    event.preventDefault()
    if (closing)
      return
    closing = true
    desktop?.save()
    stopManager().finally(() => {
      cleanupDone = true
      app.quit()
    })
  })
  app.whenReady().then(async () => {
    try {
      await startManager()
      await createWindow()
    }
    catch (error) {
      dialog.showErrorBox('AIRI Local 無法啟動', String(error.message || error))
      app.quit()
    }
  })
}
