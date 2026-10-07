const TAG_OPEN = '<|'
const TAG_CLOSE = '|>'
const ESCAPED_TAG_OPEN = '<{\'|\'}'
const ESCAPED_TAG_CLOSE = '{\'|\'}>'

interface MarkerToken {
  type: 'literal' | 'special'
  value: string
}

interface MarkerParserOptions {
  minLiteralEmitLength?: number
}

interface StreamController<T> {
  stream: ReadableStream<T>
  write: (value: T) => void
  close: () => void
  error: (err: unknown) => void
}

function createPushStream<T>(): StreamController<T> {
  let closed = false
  let controller: ReadableStreamDefaultController<T> | null = null

  const stream = new ReadableStream<T>({
    start(ctrl) {
      controller = ctrl
    },
    cancel() {
      closed = true
    },
  })

  return {
    stream,
    write(value) {
      if (!controller || closed)
        return
      controller.enqueue(value)
    },
    close() {
      if (!controller || closed)
        return
      closed = true
      controller.close()
    },
    error(err) {
      if (!controller || closed)
        return
      closed = true
      controller.error(err)
    },
  }
}

async function readStream<T>(stream: ReadableStream<T>, handler: (value: T) => Promise<void> | void) {
  const reader = stream.getReader()
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done)
        break
      await handler(value as T)
    }
  }
  finally {
    reader.releaseLock()
  }
}

/** Normalize only the two stage ACT fields; never interpret model text as code or a URL. */
function normalizeActMarker(marker: string) {
  const match = /^<\|ACT\s+(\{[\s\S]*\})\s*\|>$/.exec(marker)
  if (!match)
    return marker
  try {
    const payload: unknown = JSON.parse(match[1])
    if (!payload || typeof payload !== 'object' || Array.isArray(payload))
      return marker
    const entries = Object.entries(payload).filter(([key]) => key.trim() === 'emotion' || key.trim() === 'motion')
    const normalized = Object.fromEntries(entries.map(([key, value]) => [key.trim(), typeof value === 'string' ? value.trim() : value]))
    return `<|ACT ${JSON.stringify(normalized)}|>`
  }
  catch {
    return marker
  }
}

function createLlmMarkerParser(options?: MarkerParserOptions) {
  const minLiteralEmitLength = Math.max(1, options?.minLiteralEmitLength ?? 1)
  const tailLength = Math.max(TAG_OPEN.length - 1, ESCAPED_TAG_OPEN.length - 1)
  let buffer = ''
  let inTag = false

  return {
    async consume(textPart: string, onLiteral: (value: string) => Promise<void> | void, onSpecial: (value: string) => Promise<void> | void) {
      buffer += textPart
      buffer = buffer
        .replaceAll(ESCAPED_TAG_OPEN, TAG_OPEN)
        .replaceAll(ESCAPED_TAG_CLOSE, TAG_CLOSE)
        // Some local models tokenize the ACT delimiters with spaces. Keep this
        // tolerance specific to ACT so ordinary angle-bracket prose is unchanged.
        .replace(/<[ \t]{0,8}\|[ \t]{0,8}ACT[ \t]{0,8}(?=\{)/g, '<|ACT ')

      while (buffer.length > 0) {
        if (!inTag) {
          const openTagIndex = buffer.indexOf(TAG_OPEN)
          if (openTagIndex < 0) {
            const partialAct = /<[ \t]{0,8}(?:\|[ \t]{0,8}(?:A(?:C(?:T[ \t]{0,8})?)?)?)?$/.exec(buffer)
            const keepLength = Math.max(tailLength, partialAct?.[0].length ?? 0)
            if (buffer.length - keepLength >= minLiteralEmitLength) {
              const emit = buffer.slice(0, -keepLength)
              buffer = buffer.slice(-keepLength)
              await onLiteral(emit)
            }
            break
          }

          if (openTagIndex > 0) {
            const emit = buffer.slice(0, openTagIndex)
            buffer = buffer.slice(openTagIndex)
            await onLiteral(emit)
          }
          inTag = true
        }
        else {
          const spacedActClose = buffer.startsWith('<|ACT ') ? /\|[ \t]{0,8}>/.exec(buffer) : null
          const closeTagIndex = spacedActClose?.index ?? buffer.indexOf(TAG_CLOSE)
          const closeTagLength = spacedActClose?.[0].length ?? TAG_CLOSE.length
          if (closeTagIndex < 0)
            break

          const emit = buffer.slice(0, closeTagIndex) + TAG_CLOSE
          buffer = buffer.slice(closeTagIndex + closeTagLength)
          await onSpecial(normalizeActMarker(emit))
          inTag = false
        }
      }
    },

    async end(onLiteral: (value: string) => Promise<void> | void) {
      if (!inTag && buffer.length > 0) {
        // Only the end of input confirms this is an incomplete ACT rather than
        // a prose word such as ACTOR split after ACT across two chunks.
        buffer = buffer.replace(/<[ \t]{0,8}\|[ \t]{0,8}ACT[ \t]{0,8}$/, '')
        if (buffer)
          await onLiteral(buffer)
        buffer = ''
      }
    },
  }
}

function createLlmMarkerStream(input: ReadableStream<string>, options?: MarkerParserOptions) {
  const { stream, write, close, error } = createPushStream<MarkerToken>()
  const parser = createLlmMarkerParser(options)

  void readStream(input, async (chunk) => {
    await parser.consume(
      chunk,
      async (literal) => {
        if (!literal)
          return
        write({ type: 'literal', value: literal })
      },
      async (special) => {
        write({ type: 'special', value: special })
      },
    )
  })
    .then(async () => {
      await parser.end(async (literal) => {
        if (!literal)
          return
        write({ type: 'literal', value: literal })
      })
      close()
    })
    .catch((err) => {
      error(err)
    })

  return stream
}

/**
 * Creates a streaming parser for LLM responses with AIRI special markers.
 *
 * Use when:
 * - Handling streamed model output that may contain `<|...|>` markers.
 * - Literal text and special marker tokens need to be emitted separately.
 *
 * Expects:
 * - Callers feed chunks in order and call `end()` once the model stream ends.
 *
 * Returns:
 * - A parser with `consume()` and `end()` methods.
 */
export function useLlmmarkerParser(options: {
  onLiteral?: (literal: string) => void | Promise<void>
  onSpecial?: (special: string) => void | Promise<void>
  /**
   * Called when parsing ends with the full accumulated text.
   * Useful for final processing like categorization or filtering.
   */
  onEnd?: (fullText: string) => void | Promise<void>
  /**
   * The minimum length of text required to emit a literal part.
   * Useful for avoiding emitting literal parts too fast.
   */
  minLiteralEmitLength?: number
}) {
  let fullText = ''
  const { stream, write, close } = createPushStream<string>()

  const markerStream = createLlmMarkerStream(stream, { minLiteralEmitLength: options.minLiteralEmitLength })

  const processing = readStream(markerStream, async (token) => {
    if (token.type === 'literal')
      await options.onLiteral?.(token.value)
    if (token.type === 'special')
      await options.onSpecial?.(token.value)
  })

  return {
    /**
     * Consumes a chunk of text from the stream.
     *
     * @param textPart The chunk of text to consume.
     */
    async consume(textPart: string) {
      fullText += textPart
      write(textPart)
    },

    /**
     * Finalizes the parsing process.
     * Any remaining content in the buffer is flushed as a final literal part.
     */
    async end() {
      close()
      await processing
      await options.onEnd?.(fullText)
    },
  }
}
