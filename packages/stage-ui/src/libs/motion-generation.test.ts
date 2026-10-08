import { describe, expect, it, vi } from 'vitest'

import { LocalMotionClient, motionServiceEndpoint, parseGeneratedMotion } from './motion-generation'

function health() {
  return { ready: true, model: 'MotionGPT', device: 'cpu', selected_device: 'auto', available_devices: ['cpu', 'mps'], fps: 20, max_frames: 196, load_seconds: 0.1, busy: false, auto_fallback_reason: null }
}

function clip() {
  return { format: 'humanml3d-22', coordinate_system: 'right-handed-y-up', fps: 20, joints: Array.from({ length: 80 }, () => Array.from({ length: 22 }, () => [0, 1, 0])) }
}

describe('local motion API boundary', () => {
  it('calls native fetch with the global receiver for health and generation', async () => {
    const request = vi.fn(function (this: unknown, input: RequestInfo | URL) {
      if (this !== globalThis)
        throw new TypeError('Illegal invocation')
      return Promise.resolve(new Response(JSON.stringify(String(input).endsWith('/health') ? health() : clip())))
    })
    vi.stubGlobal('fetch', request)
    try {
      const client = new LocalMotionClient('http://127.0.0.1:17905')
      expect(await client.health()).toEqual(health())
      expect((await client.generate('wave')).joints).toHaveLength(80)
      expect(request).toHaveBeenCalledTimes(2)
    }
    finally {
      vi.unstubAllGlobals()
    }
  })

  it.each(['http://127.0.0.1:17905', 'http://localhost:17905/', 'http://[::1]:17905'])('accepts loopback origin %s', (url) => {
    expect(motionServiceEndpoint(url)).toBe(new URL(url).origin)
  })

  it.each(['https://localhost:17905', 'http://127.0.0.1.evil.test:17905', 'http://user:pass@localhost', 'http://192.168.1.2:17905', 'file:///tmp/model', 'http://localhost/path', 'http://localhost/?q=x'])('rejects non-loopback or ambiguous endpoint %s', (url) => {
    expect(() => motionServiceEndpoint(url)).toThrow()
  })

  it('validates frame count, coordinates and representation before exposing model data', () => {
    expect(parseGeneratedMotion(clip()).joints).toHaveLength(80)
    expect(() => parseGeneratedMotion({ ...clip(), fps: 60 })).toThrow()
    expect(() => parseGeneratedMotion({ ...clip(), coordinate_system: 'left-handed' })).toThrow()
    expect(() => parseGeneratedMotion({ ...clip(), joints: [[[1, 2, 3]]] })).toThrow()
    const invalid = clip()
    invalid.joints[1][2][1] = Infinity
    expect(() => parseGeneratedMotion(invalid)).toThrow()
    expect(() => parseGeneratedMotion({ ...clip(), joints: Array.from({ length: 197 }, () => clip().joints[0]) })).toThrow()
  })

  it('sends only the bounded prompt and seed to the local endpoint and refuses redirects', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(clip())))
    const controller = new AbortController()
    const client = new LocalMotionClient('http://127.0.0.1:17905', request)
    const result = await client.generate(' Raise the right arm. ', controller.signal)
    expect(request).toHaveBeenCalledWith('http://127.0.0.1:17905/v1/motions/generate', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ prompt: 'Raise the right arm.', seed: 42 }),
      redirect: 'error',
      signal: controller.signal,
    }))
    expect(result.joints).toHaveLength(80)
  })

  it('does not fetch invalid prompts and exposes service failures', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('', { status: 503 }))
    const client = new LocalMotionClient('http://localhost:17905', request)
    await expect(client.generate('x'.repeat(501))).rejects.toThrow()
    await expect(client.generate(' ')).rejects.toThrow()
    expect(request).not.toHaveBeenCalled()
    await expect(client.generate('walk')).rejects.toThrow('503')
  })

  it('switches only to a supported runtime value and validates the returned health', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(health())))
    const client = new LocalMotionClient('http://127.0.0.1:17905', request)
    expect(await client.setRuntime('auto')).toEqual(health())
    expect(request).toHaveBeenCalledWith('http://127.0.0.1:17905/v1/runtime', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ device: 'auto' }),
      redirect: 'error',
    }))
    request.mockResolvedValueOnce(new Response('{}', { status: 409 }))
    await expect(client.setRuntime('cpu')).rejects.toThrow('409')
    request.mockResolvedValueOnce(new Response('{}', { status: 422 }))
    await expect(client.setRuntime('mlx')).rejects.toThrow('422')
    request.mockResolvedValueOnce(new Response(JSON.stringify({ ready: true })))
    await expect(client.health()).rejects.toThrow()
  })
})
