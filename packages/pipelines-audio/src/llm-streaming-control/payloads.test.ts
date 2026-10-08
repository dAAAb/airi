import { describe, expect, it } from 'vitest'

import { normalizeActPayload } from './payloads'

describe('normalizeActPayload', () => {
  /**
   * @example
   * normalizeActPayload({ emotion: { name: 'happy', intensity: 0.8 }, motion: 'nod' })
   * // -> { emotion: { name: 'happy', intensity: 0.8 }, motion: 'nod' }
   */
  it('normalizes object emotion and motion from ACT payloads', () => {
    expect(normalizeActPayload({
      emotion: { name: 'happy', intensity: 0.8 },
      motion: 'nod',
    })).toEqual({
      emotion: { name: 'happy', intensity: 0.8 },
      motion: 'nod',
    })
  })

  /**
   * @example
   * normalizeActPayload({ emotion: 'surprised', motion: ' lean forward ' })
   * // -> { emotion: { name: 'surprised', intensity: 1 }, motion: 'lean forward' }
   */
  it('normalizes string emotion and trims motion cues', () => {
    expect(normalizeActPayload({
      emotion: 'surprised',
      motion: ' lean forward ',
    })).toEqual({
      emotion: { name: 'surprised', intensity: 1 },
      motion: 'lean forward',
    })
  })

  /**
   * @example
   * normalizeActPayload({ emotion: { name: 'happy', intensity: 2 } })
   * // -> { emotion: { name: 'happy', intensity: 1 } }
   */
  it('clamps emotion intensity into the supported range', () => {
    expect(normalizeActPayload({
      emotion: { name: 'happy', intensity: 2 },
    })).toEqual({
      emotion: { name: 'happy', intensity: 1 },
    })
  })
})

describe('optional generated motion description', () => {
  it('keeps bounded text only for the generate action', () => {
    expect(normalizeActPayload({ motion: 'generate', motionPrompt: ' Raise the right arm. ' })).toEqual({ motion: 'generate', motionPrompt: 'Raise the right arm.' })
    expect(normalizeActPayload({ motion: 'wave', motionPrompt: 'walk' })).toEqual({ motion: 'wave' })
    expect(normalizeActPayload({ motion: 'generate', motionPrompt: 'x'.repeat(501) })).toEqual({ motion: 'generate' })
    expect(normalizeActPayload({ motion: 'generate', motionPrompt: { script: 'run()' } })).toEqual({ motion: 'generate' })
  })
})
