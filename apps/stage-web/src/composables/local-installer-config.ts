import type { AiriCard } from '@proj-airi/stage-ui/types/airiCard'

import { array, literal, object, parse, picklist, union } from 'valibot'

export const LOCAL_INSTALLER_ORIGIN = 'http://127.0.0.1:17900'
export const SARC_MODEL = 'hf.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF:Q4_K_M'
export const GEMMA_MODEL = 'gemma4:12b-it-qat'
export const QWEN_MODEL = 'qwen3.5:0.8b'
export type LocalInstallerRole = 'mandarin' | 'taigi' | 'qwen'

const localConfigSchema = object({
  models: array(picklist(['sarc-taigi', 'gemma4', 'qwen', 'asr26', 'kokoro', 'kaedetai'])),
  ollama: union([literal('http://127.0.0.1:12434/v1/'), literal('http://127.0.0.1:11434/v1/')]),
  asr: literal('http://127.0.0.1:18001/v1/'),
  speech: literal('http://127.0.0.1:18884/v1/'),
})

export function parseLocalInstallerConfig(value: unknown) {
  return parse(localConfigSchema, value)
}

export function isLocalInstallerLaunch(enabled: string | undefined, origin: string, search: string) {
  return enabled === 'true'
    && origin === LOCAL_INSTALLER_ORIGIN
    && new URLSearchParams(search).get('localSetup') === '1'
}

export function createLocalInstallerCards(
  config: ReturnType<typeof parseLocalInstallerConfig>,
  providers: { ollama: string, speech: string },
): { key: LocalInstallerRole, card: AiriCard }[] {
  const selected = new Set(config.models)
  const vision = selected.has('gemma4')
    ? { provider: providers.ollama, model: GEMMA_MODEL }
    : selected.has('qwen')
      ? { provider: providers.ollama, model: QWEN_MODEL }
      : { provider: '', model: '' }
  const cards: { key: LocalInstallerRole, card: AiriCard }[] = []
  const modelIds = { mandarin: GEMMA_MODEL, taigi: SARC_MODEL, qwen: QWEN_MODEL }
  const selectionKeys = { mandarin: 'gemma4', taigi: 'sarc-taigi', qwen: 'qwen' } as const
  const names = { mandarin: 'ReLU 華語', taigi: 'ReLU 台語（實驗）', qwen: 'ReLU 輕量華語' }
  for (const key of ['mandarin', 'taigi', 'qwen'] as const) {
    const taigi = key === 'taigi'
    if (!selected.has(selectionKeys[key]))
      continue
    const hasSpeech = selected.has(taigi ? 'kaedetai' : 'kokoro')
    cards.push({
      key,
      card: {
        name: names[key],
        version: '1.0.0',
        metadata: { localInstaller: 1, localInstallerRole: key },
        systemPrompt: taigi
          ? '你是親切的台語助理。請用自然的臺灣台語漢字回答，毋通用華語。說話正文每擺一到兩句，總共三十五字以內。正文毋通用英文字、數字、羅馬字、表情符號或 Markdown。數量請用漢字。若無把握就講無把握，毋通假仙。直接回答問題，毋免重複自我介紹。'
          : '你是親切的虛擬人課程助理。說話正文使用繁體中文，簡短回答一到兩句。看不到圖片或不確定時直接說明。不要輸出工具指令、Markdown 或思考過程；舞台要求的 ACT 標記另依舞台指令輸出。',
        extensions: {
          airi: {
            modules: {
              consciousness: { provider: providers.ollama, model: modelIds[key] },
              vision: { ...vision },
              speech: hasSpeech
                ? { provider: providers.speech, model: taigi ? 'taigi-hanzi' : 'kokoro', voice_id: taigi ? 'taigi-demo-reference' : 'zf_xiaobei' }
                : { provider: 'speech-noop', model: '', voice_id: '' },
              displayModelId: 'preset-vrm-1',
            },
            agents: {},
          },
        },
      },
    })
  }
  return cards
}
