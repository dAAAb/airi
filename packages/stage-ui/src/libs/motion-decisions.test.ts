import { describe, expect, it, vi } from 'vitest'

import { decisionToAct, LocalMotionDecisionClient, usableMotionAct } from './motion-decisions'

const decision = { source: 'openai-decisions', choice: 'idle', motion: 'idle', confidence: 0.9, elapsed_ms: 15 } as const

describe('optional cloud motion boundary', () => {
  it('sends only one current text and a memory key through the authenticated local manager', async () => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ origin: 'http://127.0.0.1:17900', token: 'synthetic-manager-token' })))
      .mockResolvedValueOnce(new Response(JSON.stringify(decision)))
    const client = new LocalMotionDecisionClient('http://127.0.0.1:17900', request)
    expect(await client.decide('  揮手  ', 'synthetic-test-key', new AbortController().signal)).toEqual(decision)
    expect(request.mock.calls[0][0]).toBe('http://127.0.0.1:17900/api/bootstrap')
    expect(request.mock.calls[1][0]).toBe('http://127.0.0.1:17900/api/motion-decision')
    expect(request.mock.calls[1][1]?.headers).toEqual({ 'Content-Type': 'application/json', 'X-AIRI-Setup-Token': 'synthetic-manager-token' })
    expect(JSON.parse(String(request.mock.calls[1][1]?.body))).toEqual({ cloud_enabled: true, api_key: 'synthetic-test-key', text: '揮手' })
    expect(request.mock.calls.every(([, init]) => init?.redirect === 'error')).toBe(true)
  })

  it('refuses non-manager origins and invalid inputs without sending a key', async () => {
    const request = vi.fn<typeof fetch>()
    for (const origin of ['https://airi.moeru.ai', 'http://127.0.0.1:5174', 'http://127.0.0.1:17900.evil'])
      await expect(new LocalMotionDecisionClient(origin, request).decide('hello', 'key', new AbortController().signal)).rejects.toThrow('local-manager-required')
    const client = new LocalMotionDecisionClient('http://127.0.0.1:17900', request)
    await expect(client.decide('x'.repeat(2001), 'key', new AbortController().signal)).rejects.toThrow('invalid-decision-input')
    await expect(client.decide('hello', '', new AbortController().signal)).rejects.toThrow('invalid-decision-input')
    expect(request).not.toHaveBeenCalled()
  })

  it('never copies backend errors into exceptions', async () => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ origin: 'http://127.0.0.1:17900', token: 'token' })))
      .mockResolvedValueOnce(new Response('synthetic-secret-in-provider-error', { status: 502 }))
    await expect(new LocalMotionDecisionClient('http://127.0.0.1:17900', request).decide('hello', 'key', new AbortController().signal)).rejects.toThrow('decision-http-502')
  })

  it('accepts idle but defers uncertain, refused or missing-confidence results', () => {
    expect(decisionToAct(decision)).toEqual({ motion: 'idle' })
    expect(decisionToAct({ ...decision, confidence: 0.59 })).toBeUndefined()
    expect(decisionToAct({ ...decision, confidence: undefined })).toBeUndefined()
    expect(decisionToAct({ ...decision, refused: true })).toBeUndefined()
    expect(decisionToAct({ ...decision, motion: 'defer' })).toBeUndefined()
    expect(usableMotionAct({ motion: 'generate', motionPrompt: 'A person stretches.' }, false)).toBe(false)
    expect(usableMotionAct({ motion: 'generate', motionPrompt: 'A person stretches.' }, true)).toBe(true)
    expect(usableMotionAct({ motion: 'execute-javascript' }, true)).toBe(false)
  })
})
