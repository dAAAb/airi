const { spawn } = require('node:child_process')
const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const process = require('node:process')

const { app, BrowserWindow, dialog, Menu, session, shell, systemPreferences } = require('electron')

const { ORIGIN, isLocalPage, microphoneAllowed, isExternalWebLink, isOfflineRequestAllowed } = require('./policy.cjs')

app.setName('AIRI Local')
app.setPath('userData', path.join(app.getPath('appData'), 'AIRI Local Classroom'))
const ownsInstance = app.requestSingleInstanceLock()
let window
let manager
let closing = false
let cleanupDone = false
let offline = false

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

async function createWindow() {
  const localSession = await configureSession()
  window = new BrowserWindow({
    title: 'AIRI Local',
    width: 1280,
    height: 900,
    minWidth: 800,
    minHeight: 600,
    show: false,
    backgroundColor: '#101217',
    webPreferences: {
      session: localSession,
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      nodeIntegrationInWorker: false,
      webviewTag: false,
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
  window.once('ready-to-show', () => window.show())
  window.on('closed', () => {
    window = undefined
  })
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'AIRI Local', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'quit' }] },
    { role: 'editMenu' },
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }] },
  ]))
  window.loadURL(`${ORIGIN}/setup/`)
}

if (!ownsInstance) {
  app.quit()
}
else {
  app.on('second-instance', () => {
    if (window) {
      window.restore()
      window.focus()
    }
  })
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', (event) => {
    if (cleanupDone)
      return
    event.preventDefault()
    if (closing)
      return
    closing = true
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
