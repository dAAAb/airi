export const INSTALLER_ORIGIN = 'http://127.0.0.1:17900'
export const MODEL_PRESETS = {
  lite: ['qwen', 'asr26', 'kokoro'],
  full: ['sarc-taigi', 'gemma4', 'asr26', 'kokoro', 'kaedetai'],
}

export function formatBytes(bytes) {
  return `${(Math.max(0, Number(bytes) || 0) / 1e9).toFixed(2)} GB`
}

export function createInstallRequest(catalog, selected, accepted, mode) {
  if (!['bundled', 'existing'].includes(mode))
    throw new Error('請選擇 Ollama 執行方式。')
  const rows = catalog.filter(row => selected.has(row.id))
  if (!rows.length || rows.length !== selected.size)
    throw new Error('請至少選擇一個已列出的模型。')
  const required = rows.some(row => row.license === 'gemma') ? ['gemma'] : []
  if (required.some(id => !accepted.has(id)))
    throw new Error('請先閱讀並確認所選模型的授權。')
  return { models: rows.map(row => row.id), ollama_mode: mode, accepted_licenses: required }
}

export function selectedMatchesStatus(selected, mode, status) {
  return mode === status.ollama_mode
    && selected.size === status.selected.length
    && status.selected.every(id => selected.has(id))
}

export function safeLaunchUrl(value) {
  const url = new URL(value, INSTALLER_ORIGIN)
  if (url.origin !== INSTALLER_ORIGIN || url.pathname !== '/' || url.search !== '?localSetup=1' || url.hash)
    throw new Error('啟動連結與本機設定不符。')
  return url.href
}
