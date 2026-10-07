/** Replay saved model responses through AIRI's actual marker and speech parsers. */
import process from 'node:process'

import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'

async function main() {
  // Resolve the same public, compiled package entries used by the stage application.
  const require = createRequire(new URL('../../../packages/stage-ui/package.json', import.meta.url))
  const { useLlmmarkerParser } = await import(require.resolve('@proj-airi/core-agent'))
  const { createPushStream, createStreamingControlParser, createTtsSegmentStream, normalizeActPayload, readStream } = await import(require.resolve('@proj-airi/pipelines-audio'))

  const report = { scope: 'Replay of saved synthetic model output; verifies parser and TTS text separation, not live rendering or pronunciation.', cases: [] }
  for (const file of ['desktop-pet-gemma-semantic.json', 'desktop-pet-qwen-semantic-final.json', 'desktop-pet-sarc-semantic.json']) {
    const result = JSON.parse(readFileSync(new URL(`../results/${file}`, import.meta.url), 'utf8'))
    for (const row of result.cases) {
      const tokens = createPushStream()
      const segments = []
      const meta = { streamId: 'replay', intentId: 'replay' }
      const done = readStream(createTtsSegmentStream(tokens.stream, meta), (segment) => {
        segments.push(segment)
      })
      let sequence = 0
      const write = (type, value) => tokens.write({ ...meta, type, value, sequence: sequence++, createdAt: 0 })
      const parser = useLlmmarkerParser({ onLiteral: value => write('literal', value), onSpecial: value => write('special', value) })
      for (const character of row.response)
        await parser.consume(character)
      await parser.end()
      tokens.close()
      await done
      const actions = []
      const control = createStreamingControlParser()
      control.onSignal((signal) => {
        if (signal.type === 'act')
          actions.push(normalizeActPayload(signal.payload))
      })
      for (const segment of segments) {
        if (segment.special)
          await control.dispatchWith(segment.special)
      }
      const speech = segments.map(segment => segment.text).join('')
      report.cases.push({
        source: file,
        model: result.model,
        case: row.case,
        raw_response: row.response,
        normalized_actions: actions,
        speech_text: speech,
        control_leaked_to_speech: /ACT|emotion|motion|<\s*\||\|\s*>/.test(speech),
        motion_matches: actions.length === 1 && row.expected_motion.includes(actions[0].motion),
      })
    }
  }
  const output = new URL('../results/desktop-pet-semantic-replay.json', import.meta.url)
  writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`)
  console.info(JSON.stringify({ cases: report.cases.length, control_leaks: report.cases.filter(row => row.control_leaked_to_speech).length, action_matches: report.cases.filter(row => row.motion_matches).length, output: output.pathname }, null, 2))
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
