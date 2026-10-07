const v = require('valibot')

const { isLocalPage } = require('./policy.cjs')

const modeSchema = v.picklist(['window', 'pet'])
const coordinate = v.pipe(v.number(), v.finite())
const dimension = v.pipe(coordinate, v.minValue(1), v.maxValue(32768))
const boundsSchema = v.object({ x: coordinate, y: coordinate, width: dimension, height: dimension })
const preferencesSchema = v.object({
  version: v.literal(1),
  mode: modeSchema,
  alwaysOnTop: v.boolean(),
  windowBounds: v.optional(boundsSchema),
  petBounds: v.optional(boundsSchema),
})

function defaultPreferences() {
  return { version: 1, mode: 'window', alwaysOnTop: true }
}

function sanitizePreferences(value) {
  const result = v.safeParse(preferencesSchema, value)
  return result.success ? result.output : defaultPreferences()
}

function parseMode(value) {
  return v.parse(modeSchema, value)
}

function parseFlag(value) {
  return v.parse(v.boolean(), value)
}

function isStageHome(value) {
  if (!isLocalPage(value))
    return false
  return new URL(value).pathname === '/'
}

function isTrustedDesktopSender(event, contents) {
  return Boolean(event && contents
    && event.sender === contents
    && event.senderFrame === contents.mainFrame
    && event.senderFrame
    && isLocalPage(event.senderFrame.url)
    && isLocalPage(contents.getURL()))
}

function overlapArea(a, b) {
  return Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x))
    * Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y))
}

function clampBounds(value, mode, workAreas) {
  const validAreas = workAreas.map(area => v.safeParse(boundsSchema, area)).filter(result => result.success).map(result => result.output)
  if (!validAreas.length)
    throw new Error('No usable display work area')
  const parsed = v.safeParse(boundsSchema, value)
  const candidate = parsed.success ? parsed.output : undefined
  const area = candidate
    ? validAreas.reduce((best, current) => overlapArea(candidate, current) > overlapArea(candidate, best) ? current : best)
    : validAreas[0]
  const size = mode === 'pet' ? { width: 420, height: 640, minWidth: 300, minHeight: 400 } : { width: 1280, height: 900, minWidth: 800, minHeight: 600 }
  const width = Math.round(Math.min(area.width, Math.max(size.minWidth, candidate?.width ?? size.width)))
  const height = Math.round(Math.min(area.height, Math.max(size.minHeight, candidate?.height ?? size.height)))
  const defaultX = mode === 'pet' ? area.x + area.width - width - 24 : area.x + (area.width - width) / 2
  const defaultY = mode === 'pet' ? area.y + area.height - height - 24 : area.y + (area.height - height) / 2
  return {
    x: Math.round(Math.max(area.x, Math.min(candidate?.x ?? defaultX, area.x + area.width - width))),
    y: Math.round(Math.max(area.y, Math.min(candidate?.y ?? defaultY, area.y + area.height - height))),
    width,
    height,
  }
}

module.exports = { defaultPreferences, sanitizePreferences, parseMode, parseFlag, isStageHome, isTrustedDesktopSender, clampBounds }
