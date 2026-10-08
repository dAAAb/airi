import type { GeneratedMotionClip } from '@proj-airi/stage-ui-three/composables/vrm'

import * as v from 'valibot'

const coordinate = v.pipe(v.number(), v.finite(), v.minValue(-100), v.maxValue(100))
const clipSchema = v.object({
  format: v.literal('humanml3d-22'),
  fps: v.literal(20),
  coordinate_system: v.literal('right-handed-y-up'),
  joints: v.pipe(v.array(v.pipe(v.array(v.tuple([coordinate, coordinate, coordinate])), v.length(22))), v.minLength(2), v.maxLength(196)),
})
const runtimeDeviceSchema = v.picklist(['auto', 'cpu', 'mps', 'mlx'])
const healthSchema = v.object({
  ready: v.boolean(),
  model: v.string(),
  device: v.picklist(['cpu', 'mps', 'mlx']),
  selected_device: runtimeDeviceSchema,
  available_devices: v.array(v.picklist(['cpu', 'mps', 'mlx'])),
  fps: v.literal(20),
  max_frames: v.literal(196),
  load_seconds: v.pipe(v.number(), v.finite(), v.minValue(0)),
  busy: v.boolean(),
  auto_fallback_reason: v.nullable(v.string()),
})

export type MotionRuntimeDevice = v.InferOutput<typeof runtimeDeviceSchema>
export type MotionServiceHealth = v.InferOutput<typeof healthSchema>

export function motionServiceEndpoint(value: string) {
  const url = new URL(value)
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
    || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Motion service requires a loopback HTTP origin.')
  }
  return url.origin
}

export function parseGeneratedMotion(value: unknown): GeneratedMotionClip {
  return v.parse(clipSchema, value)
}

export class LocalMotionClient {
  constructor(private readonly endpoint: string, private readonly request: typeof fetch = (input, init) => globalThis.fetch(input, init)) {}

  async health(signal?: AbortSignal) {
    const response = await this.request(`${motionServiceEndpoint(this.endpoint)}/health`, { signal, redirect: 'error' })
    if (!response.ok)
      throw new Error(`Motion service HTTP ${response.status}`)
    return v.parse(healthSchema, await response.json())
  }

  async setRuntime(device: MotionRuntimeDevice, signal?: AbortSignal): Promise<MotionServiceHealth> {
    v.parse(runtimeDeviceSchema, device)
    const response = await this.request(`${motionServiceEndpoint(this.endpoint)}/v1/runtime`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device }),
      signal,
      redirect: 'error',
    })
    if (!response.ok)
      throw new Error(`Motion runtime switch HTTP ${response.status}`)
    return v.parse(healthSchema, await response.json())
  }

  async generate(prompt: string, signal?: AbortSignal): Promise<GeneratedMotionClip> {
    const text = prompt.trim()
    if (!text || text.length > 500)
      throw new Error('Motion description must contain 1–500 characters.')
    const response = await this.request(`${motionServiceEndpoint(this.endpoint)}/v1/motions/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: text, seed: 42 }),
      signal,
      redirect: 'error',
    })
    if (!response.ok)
      throw new Error(`Motion generation HTTP ${response.status}`)
    const body = await response.text()
    if (body.length > 2_000_000)
      throw new Error('Motion response exceeds the size limit.')
    return parseGeneratedMotion(JSON.parse(body))
  }
}
