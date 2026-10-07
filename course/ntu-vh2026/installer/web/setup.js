// eslint-disable-next-line no-restricted-syntax -- Native browser modules require the served file extension.
import { createInstallRequest, formatBytes, INSTALLER_ORIGIN, MODEL_PRESETS, safeLaunchUrl, selectedMatchesStatus } from './setup-state.js'

const descriptions = {
  'sarc-taigi': '台灣團隊微調的 Gemma 3。產生台語漢字，再交給台語聲音模型。',
  'gemma4': 'Google 模型。負責華語對話，也先讀圖片，再把描述交給角色。',
  'qwen': '中國阿里巴巴的 0.8B Dense 小模型。華語對話與看圖入門；能力與穩定性需自行比較。',
  'asr26': '聯發科語音辨識的社群 MLX 量化版。聽華語、台語與英語片段。',
  'kokoro': '82M 小型語音合成。以 zf_xiaobei 中文聲線回答。',
  'kaedetai': '社群 GPT-SoVITS 台語模型。漢字經 Taibun 轉音，再以 CPU 發音。',
}
const licenses = {
  'gemma': { title: 'SARC · Gemma 使用條款', url: '/licenses/gemma-terms.txt', official: 'https://ai.google.dev/gemma/terms', note: '包含 Gemma 禁止用途政策與下游散布要求。' },
  'gemma4': { title: 'Gemma 4 · Apache 2.0', url: 'https://ai.google.dev/gemma/apache_2', note: 'Gemma 4 與 SARC 使用的 Gemma 3 授權不同。' },
  'qwen': { title: 'Qwen 3.5 0.8B · Apache 2.0', url: 'https://huggingface.co/Qwen/Qwen3.5-0.8B', note: '文字與視覺模型；本機課堂配置關閉工具呼叫與思考輸出。' },
  'breeze-asr26': { title: 'Breeze ASR-26 MLX · Apache 2.0', url: 'https://huggingface.co/RayyTien/Breeze-ASR-26-mlx-4bit', note: '保留 MediaTek Research 與 MLX 轉換作者來源。' },
  'kokoro': { title: 'Kokoro · Apache 2.0', url: 'https://huggingface.co/hexgrad/Kokoro-82M', note: '聲線、模型與推論套件各自保留授權聲明。' },
  'kaedetai': { title: 'KaedeTai · MIT 與相依資料授權', url: 'https://huggingface.co/KaedeTai/gpt-sovits-tw', note: 'GPT-SoVITS 與 Taibun 程式為 MIT，Taibun 字典為 CC BY-SA 4.0。' },
}
const stateLabels = { idle: '等待選擇', installing: '下載與驗證中', ready: '模型已驗證', starting: '啟動本機服務', running: '本機服務已啟動', error: '需要處理', canceled: '已停止下載' }
const selected = new Set()
const accepted = new Set()
const elements = Object.fromEntries(['models', 'licenses', 'size-summary', 'disk-summary', 'status-title', 'status-message', 'progress', 'error', 'install', 'start', 'cancel', 'open-airi', 'runtime-options', 'scope', 'license-dialog', 'license-dialog-title', 'license-dialog-text', 'license-dialog-close'].map(id => [id, document.getElementById(id)]))
let current
let token
let pending = false
let launchRequested = false

function mode() {
  return document.querySelector('input[name="ollama-mode"]:checked').value
}

function selectPreset(preset) {
  if (!current || MODEL_PRESETS[preset].some(id => !current.catalog.some(row => row.id === id)))
    return
  selected.clear()
  for (const id of MODEL_PRESETS[preset])
    selected.add(id)
  renderModels()
  renderLicenses()
  renderStatus()
}

function errorMessage(error) {
  return String(error?.message ?? error)
}

function showError(message = '') {
  elements.error.textContent = message
  elements.error.hidden = !message
}

async function request(path, body) {
  const response = await fetch(path, {
    cache: 'no-store',
    signal: AbortSignal.timeout(15_000),
    ...(body === undefined
      ? {}
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-AIRI-Setup-Token': token },
          body: JSON.stringify(body),
        }),
  })
  const result = await response.json()
  if (!response.ok)
    throw new Error(result.error || `HTTP ${response.status}`)
  return result
}

function renderModels() {
  elements.models.replaceChildren()
  for (const row of current.catalog) {
    const label = document.createElement('label')
    label.className = 'model'
    const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'
    checkbox.value = row.id
    checkbox.checked = selected.has(row.id)
    checkbox.addEventListener('change', () => {
      checkbox.checked ? selected.add(row.id) : selected.delete(row.id)
      renderLicenses()
      renderStatus()
    })
    const content = document.createElement('div')
    const title = document.createElement('strong')
    title.textContent = row.title
    const description = document.createElement('p')
    description.textContent = descriptions[row.id] || row.id
    const meta = document.createElement('div')
    meta.className = 'meta'
    const size = document.createElement('span')
    size.textContent = `權重約 ${formatBytes(row.bytes)}`
    const availability = document.createElement('span')
    availability.dataset.statusId = row.id
    meta.append(size, availability)
    content.append(title, description, meta)
    label.append(checkbox, content)
    elements.models.append(label)
  }
}

async function showLocalLicense(title, url) {
  elements['license-dialog-title'].textContent = title
  elements['license-dialog-text'].textContent = '正在讀取隨附條款…'
  elements['license-dialog'].showModal()
  try {
    const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(15_000) })
    if (!response.ok)
      throw new Error(`HTTP ${response.status}`)
    elements['license-dialog-text'].textContent = await response.text()
  }
  catch (error) {
    elements['license-dialog-text'].textContent = `無法讀取隨附條款：${errorMessage(error)}。關閉後可開啟官方來源。`
  }
}

function createLicenseLink(title, url) {
  if (url.startsWith('/licenses/')) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'license-link'
    button.textContent = title
    button.addEventListener('click', (event) => {
      event.preventDefault()
      event.stopPropagation()
      void showLocalLicense(title, url)
    })
    return button
  }
  const link = document.createElement('a')
  link.href = url
  link.target = '_blank'
  link.rel = 'noopener noreferrer'
  link.textContent = title
  return link
}

function renderLicenses() {
  elements.licenses.replaceChildren()
  const required = new Set(current.catalog.filter(row => selected.has(row.id)).map(row => row.license))
  for (const id of required) {
    const license = licenses[id]
    if (!license)
      throw new Error(`未提供授權資訊：${id}`)
    const label = document.createElement(id === 'gemma' ? 'label' : 'div')
    label.className = 'license'
    if (id === 'gemma') {
      const checkbox = document.createElement('input')
      checkbox.type = 'checkbox'
      checkbox.value = id
      checkbox.checked = accepted.has(id)
      checkbox.addEventListener('change', () => {
        checkbox.checked ? accepted.add(id) : accepted.delete(id)
        renderStatus()
      })
      label.append(checkbox)
    }
    const content = document.createElement('span')
    if (id === 'gemma')
      content.append('我已閱讀並同意 ')
    const link = createLicenseLink(license.title, license.url)
    const note = document.createElement('small')
    note.textContent = license.note
    content.append(link, note)
    if (id === 'gemma') {
      for (const [title, url] of [['禁止用途政策（離線）', '/licenses/gemma-prohibited-use-policy.txt'], ['官方來源', license.official]]) {
        const source = createLicenseLink(title, url)
        content.append(' · ', source)
      }
    }
    label.append(content)
    elements.licenses.append(label)
  }
}

function renderStatus() {
  if (!current)
    return
  const busy = pending || ['installing', 'starting'].includes(current.job.state)
  const installLabel = current.offline ? '驗證內建模型' : '下載並驗證'
  elements.install.textContent = installLabel
  elements.cancel.textContent = current.offline ? '停止驗證' : '停止下載'
  elements.scope.textContent = current.offline
    ? '模型已隨安裝包內建，無須再下載。這組推論服務只連到本機；麥克風需由您在瀏覽器授權。'
    : '模型首次下載需要網路。這組推論服務只連到本機；麥克風需由您在瀏覽器授權。'
  const rows = current.catalog.filter(row => selected.has(row.id))
  elements['size-summary'].textContent = `${rows.length} 個模型 · 權重約 ${formatBytes(rows.reduce((sum, row) => sum + row.bytes, 0))}`
  elements['disk-summary'].textContent = current.offline
    ? `可用空間 ${formatBytes(current.free_bytes)}。內建模型將驗證完整性，無須再下載；請保留推論快取與紀錄的空間。`
    : `可用空間 ${formatBytes(current.free_bytes)}。另需執行環境、下載暫存與安全餘裕；已存在的檔案仍會驗證。`
  for (const row of current.catalog) {
    const label = elements.models.querySelector(`[data-status-id="${row.id}"]`)
    label.textContent = row.verified ? '已驗證' : row.installed ? '檔案已存在 · 待驗證' : '尚未安裝'
  }
  for (const input of document.querySelectorAll('input'))
    input.disabled = busy
  for (const button of document.querySelectorAll('[data-preset]')) {
    const preset = MODEL_PRESETS[button.dataset.preset]
    const unavailable = preset.some(id => !current.catalog.some(row => row.id === id))
    button.disabled = busy || unavailable
    button.title = unavailable ? '此安裝包未提供這個組合。' : ''
    button.setAttribute('aria-pressed', String(preset.length === selected.size && preset.every(id => selected.has(id))))
  }
  let validSelection = false
  try {
    createInstallRequest(current.catalog, selected, accepted, mode())
    validSelection = true
  }
  catch {}
  elements.install.disabled = busy || !token || !validSelection || !current.packaged
  elements.start.disabled = busy || !validSelection || !['ready', 'running'].includes(current.job.state) || !selectedMatchesStatus(selected, mode(), current)
  elements.cancel.hidden = current.job.state !== 'installing'
  elements.cancel.disabled = pending
  elements['status-title'].textContent = current.offline && current.job.state === 'installing'
    ? '驗證內建模型中'
    : current.offline && current.job.state === 'canceled' ? '已停止驗證' : stateLabels[current.job.state] || current.job.state
  elements['status-message'].textContent = !current.packaged
    ? '這是原始碼預覽，尚未附執行環境。請使用包含 runtime 的 AIRI Local 安裝包。'
    : current.job.message || (validSelection ? `準備完成。按下「${installLabel}」開始。` : '請選擇模型；選用 SARC 時，需先閱讀並確認 Gemma 條款。')
  elements.progress.hidden = !['installing', 'starting'].includes(current.job.state)
  if (current.job.total > 0) {
    elements.progress.max = current.job.total
    elements.progress.value = Math.min(current.job.total, Math.max(0, current.job.completed))
  }
  else {
    elements.progress.removeAttribute('value')
  }
  elements['open-airi'].hidden = current.job.state !== 'running'
  if (current.job.state === 'running') {
    elements['open-airi'].href = safeLaunchUrl(current.job.url || '/?localSetup=1')
    if (launchRequested) {
      launchRequested = false
      location.assign(elements['open-airi'].href)
    }
  }
  if (current.job.state === 'error') {
    launchRequested = false
    showError(current.job.message)
  }
}

async function action(path, body, launch = false) {
  pending = true
  showError()
  renderStatus()
  try {
    await request(path, body)
    launchRequested = launch
    current = await request('/api/status')
    renderStatus()
  }
  catch (error) {
    launchRequested = false
    showError(errorMessage(error))
  }
  finally {
    pending = false
    renderStatus()
  }
}

elements['license-dialog-close'].addEventListener('click', () => elements['license-dialog'].close())

elements.install.addEventListener('click', () => {
  try {
    void action('/api/install', createInstallRequest(current.catalog, selected, accepted, mode()))
  }
  catch (error) {
    showError(errorMessage(error))
  }
})
elements.start.addEventListener('click', () => void action('/api/start', {}, true))
elements.cancel.addEventListener('click', () => void action('/api/cancel', {}))
elements['runtime-options'].addEventListener('change', renderStatus)
for (const button of document.querySelectorAll('[data-preset]'))
  button.addEventListener('click', () => selectPreset(button.dataset.preset))

async function poll() {
  try {
    current = await request('/api/jobs')
    renderStatus()
  }
  catch (error) {
    elements.install.disabled = true
    elements.start.disabled = true
    showError(`本機服務連線中斷：${errorMessage(error)}。請確認 AIRI Local 仍在執行。`)
  }
  finally {
    setTimeout(poll, 1500)
  }
}

async function initialize() {
  try {
    if (location.origin !== INSTALLER_ORIGIN)
      throw new Error('請透過 AIRI Local 開啟本機安裝頁。')
    const bootstrap = await request('/api/bootstrap')
    if (bootstrap.origin !== INSTALLER_ORIGIN || typeof bootstrap.token !== 'string' || !bootstrap.token)
      throw new Error('本機安裝服務驗證失敗。')
    token = bootstrap.token
    current = await request('/api/status')
    for (const id of current.default_models)
      selected.add(id)
    renderModels()
    renderLicenses()
    renderStatus()
    void poll()
  }
  catch (error) {
    showError(errorMessage(error))
    elements['status-message'].textContent = '無法載入本機安裝設定。重新開啟 AIRI Local 後再試。'
  }
}

void initialize()
