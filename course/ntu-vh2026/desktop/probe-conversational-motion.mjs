import process from 'node:process'

import { createHash } from 'node:crypto'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'

async function main() {
  const require = createRequire(new URL('../../../packages/stage-ui/package.json', import.meta.url))
  const { useLlmmarkerParser } = await import(require.resolve('@proj-airi/core-agent'))
  const { createPushStream, createStreamingControlParser, createTtsSegmentStream, normalizeActPayload, readStream } = await import(require.resolve('@proj-airi/pipelines-audio'))
  const { getLocalCharacterMotionPrompt } = await import(new URL('../../../packages/stage-ui/src/constants/local-character-motion.ts', import.meta.url).href)
  const model = process.argv[2] ?? 'gemma4:12b-it-qat'
  const output = resolve(process.argv[3] ?? 'course/ntu-vh2026/results/motiongpt/conversational-gemma.json')
  const options = { temperature: 0.2, seed: 42, num_ctx: 4096, num_predict: 240 }
  const runtimePrompt = getLocalCharacterMotionPrompt({ motionGptEnabled: true })
  const systemPrompt = '你是親切的虛擬人課程助理。說話正文使用繁體中文，簡短回答一到兩句。看不到圖片或不確定時直接說明。不要輸出工具指令、Markdown 或思考過程；舞台要求的 ACT 標記另依舞台指令輸出。'
  const cases = [
    { name: 'stretch', input: '請把雙手高高舉過頭頂，做一段伸展，並說一句簡短的話。', expected: 'generate' },
    { name: 'boxing', input: '請站在原地，輪流用兩隻手向前打拳，做一小段拳擊練習。', expected: 'generate' },
    { name: 'conversation', input: '你好，今天心情怎麼樣？不用做動作。', expected: 'idle' },
  ]
  const report = {
    checked_at: new Date().toISOString(),
    scope: 'Synthetic natural-language turns through a real local LLM, production marker parser, speech segmenter, ACT normalization, and real MotionGPT HTTP inference. No user history or native visual quality claim.',
    model,
    system_prompt: systemPrompt,
    runtime_prompt: runtimePrompt,
    options,
    cases: [],
  }
  await mkdir(dirname(output), { recursive: true })
  for (const test of cases) {
    const started = performance.now()
    const response = await fetch('http://127.0.0.1:12434/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, stream: false, think: false, options, messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `${test.input}\n[Context]\n- system:airi-runtime-prompt: ${runtimePrompt}` },
      ] }),
      signal: AbortSignal.timeout(180_000),
    })
    if (!response.ok)
      throw new Error(`Local LLM returned HTTP ${response.status}`)
    const modelResult = await response.json()
    const content = modelResult.message?.content ?? ''
    const acts = []
    const controls = createStreamingControlParser()
    controls.onSignal((signal) => {
      if (signal.type === 'act')
        acts.push(normalizeActPayload(signal.payload))
    })
    const tokens = createPushStream()
    const meta = { streamId: test.name, intentId: test.name }
    const spoken = []
    const completed = readStream(createTtsSegmentStream(tokens.stream, meta), async (segment) => {
      if (segment.text)
        spoken.push(segment.text)
      if (segment.special)
        await controls.dispatchWith(segment.special)
    })
    let sequence = 0
    const write = (type, value) => tokens.write({ ...meta, type, value, sequence: sequence++, createdAt: Date.now() })
    const parser = useLlmmarkerParser({ onLiteral: value => write('literal', value), onSpecial: value => write('special', value) })
    for (const character of content)
      await parser.consume(character)
    await parser.end()
    tokens.close()
    await completed
    const selected = acts[0]
    const row = {
      ...test,
      model_response: content,
      parsed_acts: acts,
      spoken_text: spoken.join(''),
      generation: null,
      checks: {
        expected_action_selected: selected?.motion === test.expected,
        generated_description_preserved: test.expected !== 'generate' || !!selected?.motionPrompt,
        marker_not_spoken: !spoken.join('').includes('<|ACT'),
      },
    }
    if (selected?.motion === 'generate' && selected.motionPrompt) {
      const generated = await fetch('http://127.0.0.1:17905/v1/motions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: selected.motionPrompt, seed: 42 }),
        signal: AbortSignal.timeout(180_000),
      })
      const bytes = await generated.text()
      if (!generated.ok)
        throw new Error(`MotionGPT returned HTTP ${generated.status}: ${bytes.slice(0, 300)}`)
      const clip = JSON.parse(bytes)
      const file = `${test.name}-conversational-clip.json`
      await writeFile(resolve(dirname(output), file), `${JSON.stringify(clip)}\n`)
      row.generation = { prompt: clip.prompt, frames: clip.joints?.length, fps: clip.fps, generation_seconds: clip.generation_seconds, artifact: file, response_sha256: createHash('sha256').update(bytes).digest('hex') }
      row.checks.valid_generated_clip = clip.format === 'humanml3d-22' && clip.fps === 20
        && clip.joints.length >= 2 && clip.joints.length <= 196
        && clip.joints.every(frame => frame.length === 22 && frame.every(joint => joint.length === 3 && joint.every(Number.isFinite)))
    }
    row.elapsed_seconds = Math.round((performance.now() - started) / 10) / 100
    report.cases.push(row)
    await writeFile(output, `${JSON.stringify(report, null, 2)}\n`)
    console.info(JSON.stringify({ case: row.name, checks: row.checks, act: selected, frames: row.generation?.frames }))
  }
  if (report.cases.some(row => Object.values(row.checks).some(ok => !ok)))
    process.exitCode = 1
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
