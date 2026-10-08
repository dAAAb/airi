import type { NormalizedActPayload } from '@proj-airi/pipelines-audio'

import * as v from 'valibot'

const authoredMotions = new Set(['idle', 'nod', 'shake', 'wave', 'bow', 'celebrate', 'dance', 'sway', 'stop'])
const decisionSchema = v.object({
  source: v.literal('openai-decisions'),
  choice: v.string(),
  motion: v.picklist(['idle', 'nod', 'shake', 'wave', 'bow', 'celebrate', 'dance', 'sway', 'stop', 'generate', 'defer']),
  motion_prompt: v.optional(v.pipe(v.string(), v.minLength(1), v.maxLength(500))),
  confidence: v.optional(v.pipe(v.number(), v.finite(), v.minValue(0), v.maxValue(1))),
  elapsed_ms: v.pipe(v.number(), v.finite(), v.minValue(0)),
  refused: v.optional(v.boolean()),
})

export type MotionDecisionResult = v.InferOutput<typeof decisionSchema>

export function usableMotionAct(act: NormalizedActPayload, canGenerate: boolean) {
  return !!act.motion && (authoredMotions.has(act.motion)
    || (canGenerate && act.motion === 'generate' && typeof act.motionPrompt === 'string'
      && act.motionPrompt.trim().length > 0 && act.motionPrompt.length <= 500))
}

export function decisionToAct(result: MotionDecisionResult): NormalizedActPayload | undefined {
  if (result.refused || result.motion === 'defer' || result.confidence === undefined || result.confidence < 0.6)
    return
  return { motion: result.motion, ...(result.motion_prompt && { motionPrompt: result.motion_prompt }) }
}

/** Cloud credentials only cross the same-origin, authenticated local manager boundary. */
export class LocalMotionDecisionClient {
  constructor(private readonly origin: string, private readonly request: typeof fetch = (input, init) => globalThis.fetch(input, init)) {}

  async decide(text: string, apiKey: string, signal: AbortSignal): Promise<MotionDecisionResult> {
    if (this.origin !== 'http://127.0.0.1:17900')
      throw new Error('local-manager-required')
    const input = text.trim()
    if (!input || input.length > 2000 || !apiKey.trim())
      throw new Error('invalid-decision-input')
    const bootstrap = await this.request(`${this.origin}/api/bootstrap`, { signal, cache: 'no-store', redirect: 'error' })
    if (!bootstrap.ok)
      throw new Error('local-manager-unavailable')
    const session = v.parse(v.object({ token: v.pipe(v.string(), v.minLength(1)), origin: v.literal('http://127.0.0.1:17900') }), await bootstrap.json())
    const response = await this.request(`${this.origin}/api/motion-decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AIRI-Setup-Token': session.token },
      body: JSON.stringify({ cloud_enabled: true, api_key: apiKey.trim(), text: input }),
      signal,
      cache: 'no-store',
      redirect: 'error',
    })
    if (!response.ok)
      throw new Error(`decision-http-${response.status}`)
    return v.parse(decisionSchema, await response.json())
  }
}
