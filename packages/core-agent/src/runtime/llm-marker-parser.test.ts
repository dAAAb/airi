import { describe, expect, it } from 'vitest'

import { useLlmmarkerParser } from './llm-marker-parser'

/**
 * @example
 * const parser = useLlmmarkerParser({ onLiteral, onSpecial })
 */
describe('useLlmmarkerParser', () => {
  /**
   * @example
   * Plain model text is emitted as literal output.
   */
  it('parses pure literals', async () => {
    const collectedLiterals: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (literal) => {
        collectedLiterals.push(literal)
      },
    })

    await parser.consume('Hello, world!')
    await parser.end()

    expect(collectedLiterals.join('')).toBe('Hello, world!')
  })

  /**
   * @example
   * `<|...|>` markers are emitted as special output.
   */
  it('parses special markers separately from literals', async () => {
    const collectedLiterals: string[] = []
    const collectedSpecials: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (literal) => {
        collectedLiterals.push(literal)
      },
      onSpecial: (special) => {
        collectedSpecials.push(special)
      },
    })

    await parser.consume('Hello <|ACT|> world')
    await parser.end()

    expect(collectedLiterals.join('')).toBe('Hello  world')
    expect(collectedSpecials).toEqual(['<|ACT|>'])
  })

  /**
   * @example
   * Unfinished markers are withheld instead of leaking into literal text.
   */
  it('does not include unfinished special markers', async () => {
    const collectedLiterals: string[] = []
    const collectedSpecials: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (literal) => {
        collectedLiterals.push(literal)
      },
      onSpecial: (special) => {
        collectedSpecials.push(special)
      },
    })

    await parser.consume('<|unfinished')
    await parser.end()

    expect(collectedLiterals).toEqual([])
    expect(collectedSpecials).toEqual([])
  })
})

describe('local model ACT whitespace compatibility', () => {
  const raw = '< | ACT { " emotion " : " happy " , " motion " : " dance " } | > 恭喜你通過期中考，替你跳舞慶祝！'
  const expectedMarker = '<|ACT {"emotion":"happy","motion":"dance"}|>'

  it('handles every possible split of the captured SARC response without speaking its JSON', async () => {
    for (let split = 1; split < raw.length; split++) {
      const literals: string[] = []
      const specials: string[] = []
      const parser = useLlmmarkerParser({
        onLiteral: (value) => { literals.push(value) },
        onSpecial: (value) => { specials.push(value) },
      })
      await parser.consume(raw.slice(0, split))
      await parser.consume(raw.slice(split))
      await parser.end()
      expect(specials, `split ${split}`).toEqual([expectedMarker])
      expect(literals.join(''), `split ${split}`).toBe(' 恭喜你通過期中考，替你跳舞慶祝！')
    }
  })

  it('handles character-by-character whitespace tokens and only keeps known ACT fields', async () => {
    const literals: string[] = []
    const specials: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (value) => { literals.push(value) },
      onSpecial: (value) => { specials.push(value) },
    })
    const input = '< | ACT {" emotion ":" sad "," motion ":" idle ","url":"https://example.org"} | > 無關係，下次閣努力。'
    for (const character of input)
      await parser.consume(character)
    await parser.end()
    expect(specials).toEqual(['<|ACT {"emotion":"sad","motion":"idle"}|>'])
    expect(literals.join('')).toBe(' 無關係，下次閣努力。')
  })

  it('preserves generated motion descriptions through every streaming split', async () => {
    const description = 'A person raises both hands above their head and stretches.'
    const marker = `< | ACT { "emotion": "happy", " motion ": " generate ", " motionPrompt ": " ${description} ", "url": "https://example.org" } | >`
    for (let split = 1; split < marker.length; split++) {
      const specials: string[] = []
      const parser = useLlmmarkerParser({
        onSpecial: (value) => { specials.push(value) },
      })
      await parser.consume(marker.slice(0, split))
      await parser.consume(marker.slice(split))
      await parser.end()
      expect(specials, `split ${split}`).toEqual([`<|ACT ${JSON.stringify({ emotion: 'happy', motion: 'generate', motionPrompt: description })}|>`])
    }
  })

  it.each([
    { motion: 'wave', motionPrompt: 'wave' },
    { motion: 'generate', motionPrompt: '' },
    { motion: 'generate', motionPrompt: 'x'.repeat(501) },
    { motion: 'generate', motionPrompt: { command: 'wave' } },
  ])('drops unsupported generated descriptions: $motion', async (payload) => {
    const specials: string[] = []
    const parser = useLlmmarkerParser({
      onSpecial: (value) => { specials.push(value) },
    })
    await parser.consume(`<|ACT ${JSON.stringify(payload)}|>`)
    await parser.end()
    expect(specials).toEqual([`<|ACT ${JSON.stringify({ motion: payload.motion })}|>`])
  })

  it.each(['a < b and c > d', '<div>hello</div>', '< | CLOCK time | >', 'Value <          10'])('preserves non-ACT prose %s', async (input) => {
    const literals: string[] = []
    const specials: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (value) => { literals.push(value) },
      onSpecial: (value) => { specials.push(value) },
    })
    for (const character of input)
      await parser.consume(character)
    await parser.end()
    expect(specials).toEqual([])
    expect(literals.join('')).toBe(input)
  })

  it.each(['< | ACTOR greeting | > example', '< | ACTUAL data | > example'])('keeps every split of non-ACT prose: %s', async (input) => {
    for (let split = 1; split < input.length; split++) {
      const literals: string[] = []
      const specials: string[] = []
      const parser = useLlmmarkerParser({
        onLiteral: (value) => { literals.push(value) },
        onSpecial: (value) => { specials.push(value) },
      })
      await parser.consume(input.slice(0, split))
      await parser.consume(input.slice(split))
      await parser.end()
      expect(literals.join(''), `split ${split}`).toBe(input)
      expect(specials, `split ${split}`).toEqual([])
    }
  })

  it('withholds an unfinished spaced ACT prefix only when input ends', async () => {
    const literals: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (value) => {
        literals.push(value)
      },
    })
    for (const character of 'hello < | ACT')
      await parser.consume(character)
    await parser.end()
    expect(literals.join('')).toBe('hello ')
  })

  it('withholds an incomplete ACT but does not retain an unlimited plain-text suffix', async () => {
    const literals: string[] = []
    const parser = useLlmmarkerParser({
      onLiteral: (value) => {
        literals.push(value)
      },
    })
    await parser.consume('before < | ACT {" motion ": "dance"')
    await parser.end()
    expect(literals.join('')).toBe('before ')
    const plain: string[] = []
    const other = useLlmmarkerParser({
      onLiteral: (value) => {
        plain.push(value)
      },
    })
    await other.consume('a'.repeat(1000))
    await other.consume('b'.repeat(1000))
    await other.end()
    expect(plain[0].length).toBeGreaterThan(950)
    expect(plain.join('')).toBe('a'.repeat(1000) + 'b'.repeat(1000))
  })
})
