const ORIGIN = 'http://127.0.0.1:17900'

function isLocalPage(value) {
  try {
    const url = new URL(value)
    return url.origin === ORIGIN && !url.username && !url.password
  }
  catch { return false }
}

function microphoneAllowed(pageURL, permission, requestURL, mediaTypes) {
  return permission === 'media'
    && isLocalPage(pageURL)
    && isLocalPage(requestURL)
    && Array.isArray(mediaTypes)
    && mediaTypes.length === 1
    && mediaTypes[0] === 'audio'
}

function isExternalWebLink(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password
  }
  catch { return false }
}

function isOfflineRequestAllowed(value) {
  try {
    const url = new URL(value)
    return !['http:', 'https:'].includes(url.protocol)
      || ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
  }
  catch { return false }
}

module.exports = { ORIGIN, isLocalPage, microphoneAllowed, isExternalWebLink, isOfflineRequestAllowed }
