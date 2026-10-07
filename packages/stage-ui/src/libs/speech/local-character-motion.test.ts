import type { TextSegment, TextToken } from '@proj-airi/pipelines-audio'

import { useLlmmarkerParser } from '@proj-airi/core-agent'
import { createPushStream, createStreamingControlParser, createTtsSegmentStream, normalizeActPayload, readStream } from '@proj-airi/pipelines-audio'
import { describe, expect, it } from 'vitest'

/** Use the real streaming marker parser and REST TTS segmenter, including split JSON tokens. */
describe('local character ACT speech separation', () => {
  it.each([
    { spokenText: '真替你高興！', emotion: 'happy', motion: 'dance', spaced: false },
    { spokenText: '真歡喜，咱做伙慶祝！', emotion: 'happy', motion: 'dance', spaced: false },
    { spokenText: '恭喜你通過期中考，替你跳舞慶祝！', emotion: 'happy', motion: 'dance', spaced: true },
    { spokenText: '無關係，考試無過嘛是正常的代誌，下次努力就好矣。', emotion: 'sad', motion: 'idle', spaced: true },
  ])('keeps stage JSON out of spoken text: $spokenText', async ({ spokenText, emotion, motion, spaced }) => {
    const tokens = createPushStream<TextToken>()
    const meta = { streamId: 'local-test', intentId: 'local-test' }
    const segments: TextSegment[] = []
    const completed = readStream(createTtsSegmentStream(tokens.stream, meta), (segment) => {
      segments.push(segment)
    })
    let sequence = 0
    const write = (type: TextToken['type'], value: string) => {
      tokens.write({ ...meta, type, value, sequence: sequence++, createdAt: Date.now() })
    }
    const literals: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (value) => {
        literals.push(value)
        write('literal', value)
      },
      onSpecial: value => write('special', value),
    })
    const act = `<|ACT ${JSON.stringify({ emotion, motion })}|>`
    const raw = spaced ? `< | ACT { " emotion " : " ${emotion} " , " motion " : " ${motion} " } | >` : act
    for (const chunk of raw + spokenText)
      await parser.consume(chunk)
    await parser.end()
    tokens.close()
    await completed

    expect(literals.join('')).toBe(spokenText)
    expect(segments.map(segment => segment.text).join('')).toBe(spokenText)
    expect(segments.flatMap(segment => segment.special ? [segment.special] : [])).toEqual([act])
    const controls = createStreamingControlParser()
    const actions: unknown[] = []
    controls.onSignal((signal) => {
      if (signal.type === 'act')
        actions.push(normalizeActPayload(signal.payload))
    })
    await controls.dispatchWith(act)
    expect(actions).toEqual([{ emotion: { name: emotion, intensity: 1 }, motion }])
  })
})
