# 本機台語對話：2026-10-07 實驗筆記

**課堂操作者已在 Chrome 親自確認：AIRI 聽得懂台語，也能用台語回答。** 這是已安裝環境的一次端到端驗收，不是母語自然度評分、混語能力保證，或全新電腦安裝測試。

這個實驗讓同一個 VRM 接上不同的耳朵、大腦與嘴巴。通用華語模式用 Gemma 4＋Kokoro；台語模式用 SARC＋Taibun＋KaedeTai。原始麥克風錄音、私人對話、個人角色卡 ID 與本機路徑不放進公開 repo。

## 一段台語對話如何完成

```text
麥克風音訊片段
  → Breeze-ASR-26 MLX：轉成文字，通常是華語漢字
  → SARC 台語 LLM：理解問題，產生台語漢字回答
  → Taibun：把台語漢字轉成帶調號 POJ
  → KaedeTai GPT-SoVITS：生成台語音訊
  → AIRI：播放聲音、驅動 VRM 說話嘴型
```

Taibun 是字典式轉寫，**不會把任意華語句子翻成自然台語**。SARC 先選用台語詞彙與語法，再交給轉寫器。圖片先由 Gemma 4 描述，再把描述交給台語對話模型；本次 SARC GGUF 只有文字 completion 能力。

## 精確模型與接口

以下是課堂開發環境的 loopback 埠。獨立 App 的私有埠或安裝目錄由其管理器決定，不能把表內埠號當成所有發行版的固定設定。

| 元件 | 已測模型／版本 | 開發環境接口 |
|---|---|---|
| AIRI Web | 本 fork | `http://127.0.0.1:5174/` |
| Ollama | 0.35.1 | `http://127.0.0.1:11434/v1/` |
| 台語 LLM | `hf.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF:Q4_K_M` | Ollama；11.8B，下載約 7.30 GB |
| 通用 LLM／vision | `gemma4:12b-it-qat` | Ollama；11.9B，下載約 7.15 GB |
| ASR | `RayyTien/Breeze-ASR-26-mlx-4bit`；API model `breeze-asr-26-mlx` | `http://127.0.0.1:8001/v1/` |
| 華語 TTS | `hexgrad/Kokoro-82M` v1.0；model `kokoro`、voice `zf_xiaobei` | `http://127.0.0.1:8880/v1/` |
| 台語 TTS | `KaedeTai/gpt-sovits-tw` S1 trilingual＋S2 r4 e15；model `taigi-hanzi`、voice `taigi-demo-reference` | `http://127.0.0.1:8883/v1/` |
| 漢字轉寫 | Taibun 1.1.8；POJ、south、mark、sandhi none | TTS adapter 內部呼叫 |
| 語音入口 | 本課固定路由 hub | `http://127.0.0.1:8884/v1/` |
| 小型 TTS 對照 | `facebook/mms-tts-nan`；model `mms-tts-nan-taigi-hanzi`、voice `nan-poj` | `http://127.0.0.1:8882/v1/`；非預設 |

SARC 的來源 revision 為 `aefda61b35defdb81c3ccaea2cab086b4e2325bd`，本機 Ollama digest 為 `66544e32e46623d914413577b2b353c853d071612f7304792b817d924554930b`。Gemma 4 的本機 digest 為 `38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3`。Tag 會更新，重測時也要記錄 digest。

KaedeTai 權重 revision 為 `fa251907be54b63277377a96a23377fd7f00e323`，程式來源 commit 為 `81959852f75c972a0a78364f8ea6b14133a11f4a`。S1／S2 加必要聲音編碼器約 1.40 GB。大小是下載量，不等於執行時 RAM。

## 同一個網址，兩張角色卡

兩張卡選同一個 OpenAI-compatible Speech provider，Base URL 使用語音 hub。卡片分別保存自己的 model／voice ID：

| 角色用途 | Chat | Speech model | Voice |
|---|---|---|---|
| 華語對話與看圖 | `gemma4:12b-it-qat` | `kokoro` | `zf_xiaobei` |
| 台語對話 | 完整 SARC model ID，見上表 | `taigi-hanzi` | `taigi-demo-reference` |

hub 只按模型 ID 固定轉送：`kokoro` 到 8880，`taigi-hanzi` 到 8883。模型與 voice 必須成對，不會在台語失敗後偷偷改讀華語。卡片的自訂欄位留白表示繼承模組設定。

台語角色已測提示：

> 你是親切的台灣台語對話助手。請用自然的台灣台語漢字回答，毋通用華語。每擺干焦講一到兩句，總長毋通超過三十五个漢字。毋免解說翻譯，毋免羅馬字，毋免標題。

實驗使用 temperature 0.2、seed 42、context 4096、最多 160 個輸出 token。SARC 仍會偶爾超長；短句指令不是硬性限制。KaedeTai adapter 另限制最多 60 個漢字與 180 個音素，拒絕無法完整轉寫的字、英文或阿拉伯數字。

## 成功與失敗都保留

| 測試 | 觀察 | 可以下的結論 |
|---|---|---|
| Chrome 真人台語聽說 | 操作者確認能聽、能回答 | 本機互動管線可用；不是母語盲聽評分 |
| 新問題請角色先問一句話 | SARC 產生「你敢有啥物特別想欲講的話？」 | 是即時生成的回答，不是固定播放台詞 |
| 上句經 Taibun→KaedeTai→ASR | POJ：`Lí kám-ū siáⁿ-mi̍h te̍k-pia̍t siūⁿ-beh kóng ê ōe?`；回讀「你有什麼特別想說的話嗎」 | 這一句回讀保留原意 |
| 固定句「我是你的台語助理」 | 曾回讀成「我是你的大義祖先」 | TTS／ASR 仍有錯誤；不能用單次回讀判定全部發音 |
| 相同鼓勵句交給 MMS | 無需改拼音即可產生聲音 | 小模型有可用例子；未做母語自然度評分 |
| MMS 遇到鼻化 `ⁿ` 等未收錄字元 | adapter 回 422 | 不猜成 `n`／`nn`，不讓 tokenizer 默默漏字 |
| Gemma 4 直接寫 POJ | 三句測試出現不正確羅馬字、重複或漢字 | 通用能力強，不代表台語轉寫可靠 |
| 0.8B Qwen／230M LFM 寫 POJ | 三句測試未完成正確 POJ 轉換 | 小不是唯一選型目標；此觀察不是完整模型排名 |
| SARC 晚餐建議 | 超過要求長度，夾用華語詞 | 台語專用模型也需要長度和詞彙檢查 |
| Gemma 4 開啟 thinking、只給 160 tokens | 預算耗在思考，沒有可見回答 | 對話無回應不一定是麥克風壞掉 |
| Chrome 白底綠三角形 | Gemma 4 說出「白色背景中央的實心綠色三角形」，Kokoro 回 HTTP 200 | 這張圖看對且語音生成成功，不等於所有圖片都理解 |

本次合成參考聲音來自作者公開的合成示範，不是學生或授課者的聲音複製。公開 repo 不散布本次私人現場錄音。

## 效能該怎麼讀

實測電腦為 Apple M4 Max、128 GiB RAM。ASR 使用 MLX；KaedeTai、MMS 與 Kokoro 的已測路徑使用 CPU。沒有把這幾個 TTS 宣稱為 MLX 加速。

| 單次測試 | 本次觀察 |
|---|---|
| SARC 產生上面的新問題回答 | 約 0.592 秒 |
| KaedeTai 合成該回答 | HTTP 約 0.837 秒；音訊長 3.04 秒 |
| KaedeTai 合成鼓勵句 | HTTP 約 1.677 秒；音訊長 6.76 秒 |
| MMS 合成相同鼓勵句 | 推論約 0.367 秒；音訊長 6.528 秒 |

數字包含的工作不同，不能相減就稱為模型加速比，也不是從開始說話到聽見回答的延遲。完整互動還包含錄音、偵測停句、ASR、排隊、LLM、分句、TTS、播放緩衝。ASR 服務先收完一段音訊再辨識，不是逐 token 串流解碼。

## 為何改這些程式

1. Provider 和圖片訊息的 Vue proxy 曾跨過 `structuredClone` 邊界而失敗；修成可複製的快照／普通記錄。
2. Ollama 的原生 `think` 不等於 OpenAI-compatible 路徑的 reasoning 選項；改用既有 provider 映射，關閉時送 `reasoning_effort:none`。
3. SARC 此版不支援 tools。`VITE_AIRI_DISABLE_TOOLS=true` 明確停用工具定義與工具選擇，保留嘴型與待機動畫。
4. ASR tokenizer 的 no-speech 拼字差異曾誤把 EOT 當成禁止 token；記憶體相容修正解除不能結束的重複解碼。
5. compatible provider 的模型清單不一定包含自訂 ID。角色卡新增 model／voice 文字輸入。
6. 舞台曾以全域 provider 值蓋掉角色卡。現在先解析卡片／模組值，全域只作預設，讓華語與台語切換真的生效。

細節與命令在 [本機修正記錄](../../../docs/classroom-local-fixes.md)。

## 重現範圍與檢查

- [ASR HTTP provider](asr26/README.zh-TW.md)、[台語 TTS adapters](taigi-tts/)、[語音 hub](local-speech-hub/) 提供程式與固定來源設定。
- Ollama 模型由使用者依原作者條款自行取得；權重、虛擬環境與第三方音檔不屬於原始碼 repo。
- 本次成功使用預先安裝的研究環境。公開版的來源固定與測試通過，不等於全新電腦已驗收；安裝頁與 Mac 發行包需各自記錄驗收結果。
- ASR HTTP 無模型 contract tests：11 通過；LLM tests：36 通過；speech tests：36 通過；真正 headless Chrome 角色卡測試：2 通過。
- Stage UI 與 Stage Pages typecheck 通過；[更早六檔的 120 tests 和來源修正](../../../docs/classroom-local-fixes.md)另有記錄。
- 完整根目錄 typecheck 仍因精簡 Web 安裝缺少 Electron 相關依賴失敗；根目錄 lint 仍缺 docs 的 `@radix-ui/colors`。未以停用規則隱藏問題，也不稱全 monorepo 全綠。

## 來源與授權分開標示

SARC 是台灣 SARC 團隊微調 Google Gemma 3；Breeze-ASR-26 是聯發科模型，MLX 轉換由 RayyTien 提供。KaedeTai 是 GPT-SoVITS 的社群台語適配，不是聯發科 BreezyVoice 26。

| 元件 | 官方來源／條款 |
|---|---|
| SARC GGUF | [模型卡](https://huggingface.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF)、[Gemma 3 條款](https://ai.google.dev/gemma/terms) |
| Gemma 4 | [Google 模型卡](https://huggingface.co/google/gemma-4-12B-it)、[Apache 2.0](https://ai.google.dev/gemma/apache_2)；與 Gemma 3 條款不同 |
| Breeze ASR-26／MLX | [聯發科原版](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)、[RayyTien 轉換](https://huggingface.co/RayyTien/Breeze-ASR-26-mlx-4bit)：Apache 2.0 |
| Kokoro | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)：Apache 2.0 |
| KaedeTai | [模型卡](https://huggingface.co/KaedeTai/gpt-sovits-tw)標示 MIT；[台語程式](https://github.com/KaedeTai/GPT-SoVITS)，依賴另保留來源條款 |
| Taibun | [程式／字典來源](https://github.com/andreihar/taibun)：程式 MIT、字典 CC BY-SA 4.0 |
| MMS | [Meta 模型卡](https://huggingface.co/facebook/mms-tts-nan)：CC BY-NC 4.0，非商用對照用途 |

AIRI 程式的授權不會取代模型、字典、聲線、FFmpeg 或其他依賴的條款。下載、自用與重新打包散布也有不同要求；重新發布權重時另讀發行包的授權清單。
