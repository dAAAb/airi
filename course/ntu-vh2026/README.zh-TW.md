# 讓同一個 VRM，換一副耳朵與嘴巴

這是臺大「虛擬人與遙現」第五週的本機語音實驗。先固定 VRM 角色，再比較語音辨識（STT）、語言模型（LLM）與語音合成（TTS）。測試記錄日期：**2026-10-07**。

**2026-10-07 更新：已在本機 Chrome 完成台語聽說，並由操作者確認。** 新組合是 Breeze-ASR-26＋SARC 台語 LLM＋Taibun＋KaedeTai TTS；設定、成功與失敗案例、重現限制見[本機台語對話筆記](TAIGI-LOCAL-NOTES.zh-TW.md)。聯發科 BreezyVoice 26 仍只有官方展示；KaedeTai 是另一個社群台語模型。

想從介面選模型與啟動兩種角色，請看 [AIRI Local Mac 安裝包說明](installer/README.zh-TW.md)。下面保留手動安裝與比較實驗，方便修改程式、追蹤每一層的結果。

**2026-10-08：** [桌寵與 AI 語意動作](DESKTOP-PET.zh-TW.md) 說明透明桌面模式、語意選動作的控制流程及學生實驗。

| 名稱 | 耳朵／嘴巴 | 這次真的做了什麼 |
| --- | --- | --- |
| MediaTek Breeze2-VITS-onnx | 嘴巴：台灣華語 | Sherpa-ONNX CPU、本機 HTTP 服務、AIRI TTS 測試通過。不是台語 TTS，也沒有用 MLX。 |
| MediaTek Breeze-ASR-26 → RayyTien MLX 4-bit | 耳朵：台語／華語音訊轉文字 | Apple Silicon MLX 檔案轉錄，修正 tokenizer 相容問題。新增常駐 HTTP provider，可接 AIRI 麥克風音訊片段。 |
| MediaTek BreezyVoice 26 / BreezyVoice-Taigi | 嘴巴：台語 | 僅聽官方預錄展示。截至查核日未找到公開權重或可驗證的相應 MLX 版。 |
| Kokoro-82M | 嘴巴：含中文聲線 | 原課堂對照，使用 `zf_xiaobei`。AIRI Local 安裝器新增本機服務。 |

ASR 的 987 MB 是主要量化權重檔，不是 TTS 大小，也不是執行時 RAM。模型來源、社群轉換者、執行後端必須分開記錄。

## 先啟動自己的 AIRI

先在 GitHub fork 本倉庫，再 clone 自己的 fork。若只複製預設分支，請確認它是本課的 `dAAAb/feat/ntu-local-speech`。本次使用 Node 26.7.0、pnpm 11.24.0；pnpm 版本由根目錄 `packageManager` 固定。

```bash
# 把 YOUR_GITHUB_USERNAME 換成自己的 GitHub 帳號
git clone https://github.com/YOUR_GITHUB_USERNAME/airi.git
cd airi
```

課堂使用 Web 版及其依賴。以下是這次實際使用的安裝／建置範圍；完整桌面與其他 workspace 請另看[上游說明](../../README.md)。從倉庫根目錄執行：

```bash
pnpm --filter '@proj-airi/stage-web...' install --frozen-lockfile --ignore-scripts
pnpm -r --filter '@proj-airi/stage-web^...' run build
sh course/ntu-vh2026/start-airi-local.sh
```

`--ignore-scripts` 略過全庫安裝後的自動 hook／建置，第二行明確建置 Web 需要的 packages。這套精簡安裝不保證全 monorepo 的 lint／typecheck 可執行。首次啟動還會取得角色或其他前端素材，需預留下載時間。

開啟 `http://127.0.0.1:5174/`，匯入自己的 VRM。helper 直接呼叫 Vite 並指定 loopback，避免上游 `dev` 腳本的裸 `--host` 對區網開放。LLM provider 可以先接 Ollama：`http://127.0.0.1:11434/v1/`。

**本機網頁不等於所有推論都在本機。** 換成 OpenRouter 等雲端 provider 後，對應文字、圖片或音訊會送往所選服務。先記錄每一層的 provider，再作比較。本 lab 的 TTS 僅綁定 loopback，ASR 推論開啟 Hugging Face 離線模式。首次安裝、模型下載和 AIRI 外部資源仍需網路。

## A. 本機台灣華語嘴巴：Breeze2 CPU

以下指令從 `course/ntu-vh2026/` 執行。已驗證環境為 Python 3.12、Sherpa-ONNX 1.13.8。請先查看[官方模型卡](https://huggingface.co/MediaTek-Research/Breeze2-VITS-onnx)的使用條款。本倉庫不附權重，也不把未明列的權重授權當作 AIRI 的 MIT 授權。

```bash
cd course/ntu-vh2026
python3.12 -m venv breeze2/.venv
breeze2/.venv/bin/python -m pip install -r breeze2/requirements.txt
python3 model-assets.py breeze2 --download
breeze2/.venv/bin/python breeze2/test-service.py
sh breeze2/start.sh
```

另開終端機，在同一目錄生成自己的試聽檔：

```bash
python3 breeze2/generate-examples.py
```

音檔與 HTTP 計時存入 `local/tts/`。這些檔案由 Git 忽略。服務 `http://127.0.0.1:8881/health` 可查狀態。

在 AIRI 設定中，新增 OpenAI-compatible TTS / Speech provider，然後在「語音合成／嘴巴」模組選用：

| 設定 | 值 |
| --- | --- |
| Base URL | `http://127.0.0.1:8881/v1/` |
| Model | `breeze2-vits` |
| Voice | `breeze2-zh-tw` |
| API key | 這個本機服務不需要。如 UI 必填，填非秘密字串 `local`。 |
| Format | `wav`；若用 MP3／PCM，需先安裝 FFmpeg。 |

服務允許 AIRI 的 `127.0.0.1:5174` 與 `localhost:5174` Origin。換埠時需同步修改 `breeze2/server.py` 的明確允許清單，不能直接開放所有網站。

### 該聽什麼

`testcases.json` 包含地名、多音字、中英混合與數字案例：

- 「歡迎來到臺灣。我們今天從臺北搭高鐵到高雄，下午再前往臺南。」
- 「銀行的行長說，這個方法行得通。」
- 「今天我們用 OpenRouter 切換 AI 模型，再讓 VRM 角色說 Hello world。」

第三句會明確回 **HTTP 422**。原版字典缺少英文詞和阿拉伯數字，直接交給引擎會漏念。因此 adapter 先攔截，讓學生看見失敗原因。`2026` 可改寫成「二零二六」。這個攔截只涵蓋拉丁字母與阿拉伯數字，不保證所有其他字都可合成。

對照相同句子的 Kokoro 與 Breeze2 音檔，先盲聽再看名字。記錄漏字、地名、多音字、韻律與個人偏好。不能用「ASR 轉錄回來的字」單獨判定 TTS 發音正確。

## B. 本機台語耳朵：ASR-26 MLX

這一路需要 **Apple Silicon Mac**、Python 3.12、FFmpeg。Windows/Linux 同學可先做 CPU TTS；此處沒有假設 MLX 能跨到其他 GPU。請先閱讀[聯發科模型卡](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)及[社群轉換版模型卡](https://huggingface.co/RayyTien/Breeze-ASR-26-mlx-4bit)。

```bash
python3.12 -m venv asr26/.venv
asr26/.venv/bin/python -m pip install -r asr26/requirements.txt
python3 model-assets.py asr26 --download
asr26/.venv/bin/python asr26/verify-tokenizer.py
asr26/.venv/bin/python asr26/transcribe.py /path/to/your-recording.wav --json
```

`model-assets.py` 固定本次下載的 revision 並核對 SHA-256。重跑不加 `--download` 只驗證本機檔案。已有模型可加 `--model-dir /path/to/model`，轉錄與 tokenizer 驗證也支援同一參數。

上述指令是**檔案轉錄**。現在也提供[常駐 HTTP provider](asr26/README.zh-TW.md)，以 `http://127.0.0.1:8001/v1/` 接收 AIRI 麥克風音訊片段。它收完一段再辨識，並不是 token 級串流。音檔推論快於播放時間，不代表整條 STT→LLM→TTS 對話已即時。

### 真的修到什麼

`mlx-audio 0.4.3` 的 HF Whisper wrapper 查找 `<|nospeech|>`，這個 tokenizer 實際使用 `<|nocaptions|>`。找不到時回傳 unknown token **50257**，恰好也是 EOT。解碼器把結束標記禁掉，因此一直重複。

`asr26/whisper-compat.py` 只修正記憶體中的 wrapper。它確認 no-speech 是 **50362**、EOT **50257** 不被遮蔽，並驗證與模型 `generation_config.json` 的遮蔽清單一致。不改權重或 `site-packages`。詞表缺少、歧義或映射錯誤會明確失敗。

```bash
python3 asr26/test-compat.py
asr26/.venv/bin/python asr26/verify-tokenizer.py
```

第一個是無模型 regression test。第二個使用真正的本機 tokenizer。升級 mlx-audio 後，先重跑第二個驗證，再決定是否移除此修正。

## C. 用相同真人錄音重做小實驗

原始媒體與條款列在 [`sources/audio-sources.json`](sources/audio-sources.json)。repo 不散布第三方音訊。查看來源條款後，可自行抓取兩句 ML2021 中英混語與行政院台語家務分工廣播：

```bash
python3 prepare-fixtures.py --download
asr26/.venv/bin/python asr26/benchmark.py --engine mlx --output local/asr26-results.json
```

已有原始檔案時，改用 `--source-dir /path/to/originals`。腳本驗證原始 SHA-256，再統一轉成 16 kHz mono PCM。若來源檔案變動，會停止，不能沿用舊結果。FFmpeg 不同版本的 WAV 標頭可造成重採樣檔雜湊差異。

若要重做 CPU 對照，另外安裝 `faster-whisper` 的獨立環境，下載官方 `Systran/faster-whisper-base` CTranslate2 權重，再執行 `asr26/benchmark.py --engine base --base-model-dir /path/to/base-model --output local/base-results.json`。不要把 MLX 和 CPU 結果差異稱為純後端加速比，因為模型與量化配置也不同。

也請錄自己的語音，避免只測公開範例。「放進你的 training 裡面」和「要求機器學到 attention」可測原詞是否保留。台語請由母語者說日常句子，再分別附「台語原話」與「華語意思」。把繁體中文送給華語 TTS 不會自動變成台語發音。

## 已完成的測試結果

硬體為 Apple M4 Max、128 GiB RAM。五段音檔各兩次，以下列第二次。完整記錄在 [`results/`](results/)。公開版只移除私有絕對路徑，不改測量值或辨識文字。

| 輸入 | 音檔長度 | ASR-26 MLX | Whisper-base CPU |
| --- | ---: | ---: | ---: |
| Kokoro 合成介紹 | 5.81 s | 0.475 s | 0.282 s |
| Breeze2 合成同句 | 4.52 s | 0.445 s | 0.279 s |
| 真人：training | 1.59 s | 0.320 s | 0.227 s |
| 真人：attention | 1.73 s | 0.322 s | 0.230 s |
| 台語家務分工廣播 | 29.69 s | 1.101 s | 0.610 s |

ASR 計時包括特徵處理與完整解碼，不含模型載入、錄音、檔案讀取或重採樣。MLX allocator 峰值約 1.63 GiB。Breeze2 同句約 4.5 秒的音訊，暖機 HTTP 回應約 0.79–0.83 秒。Kokoro 對照約 0.39 秒。這些都不是首聲延遲或 STT→LLM→TTS 全鏈延遲。

台語廣播這一段，ASR-26 留下的內容較完整，仍把「阿公」寫成「阿憨」。用同一份華語參考稿算診斷 CER：ASR-26 **18.9%**、base **76.6%**。台語與華語不是逐字對應，不能把這個數字叫作台語正字錯誤率或一般正確率。

| 真人原句 | ASR-26 輸出 |
| --- | --- |
| 放進你的 training 裡面 | 放進你的春捲裡面 |
| 要求機器學到 attention | 要求機器學到注意 |

官方說明包含混語能力，但這兩句沒有可靠保留英文原詞。語意翻譯與逐字轉錄是不同要求。公開範例也不是隱藏測試集，這五段不能代表所有口音、噪音或設備。

## 台語嘴巴：本次的邊界

[BreezyVoice 26 官方文章](https://www.mediatek.com/zh-tw/tek-talk-blogs/mediatek-research-breeze-3)附有「你這個帳戶的年利率有 3%」台語展示。這是**官方預錄**，不是此 repo 的本機生成結果。官方音訊的來源連結保留在 `sources/audio-sources.json`，不重新散布。

截至 2026-10-07，本次查核未找到公開可下載的 BreezyVoice 26 權重及對應 MLX 版。2025 年舊 BreezyVoice 的社群 MLX 移植是台灣華語／CosyVoice v1，不能因名稱相近就當作台語 BreezyVoice 26。Breeze2-VITS 也不能替代它。

## 課堂試一試

每組保留同一角色，先只換一層：LLM provider、STT 或 TTS。再換角色，觀察同一句回答的感受是否不同。記錄以下六件事：

1. 真人原話／TTS 輸入文字。
2. STT 實際辨識文字，尤其英文、台語、名字。
3. LLM 回答與選用模型，分清 tool use 和 vision 能力。
4. TTS 真正念出的內容，標出漏字和發音問題。
5. 端到端等待時間、硬體、權重大小、執行記憶體。
6. 資料送往哪裡，失敗發生在哪一層。

LLM 能回文字不代表支持 vision 或 tool use。MoE 的總參數量與每 token 啟用參數量也不是一回事。不要只用「模型大小」判斷整個虛擬人的能力。

先跑每一段，再跑整條鏈。`Failed to fetch` 先查服務、Base URL、Origin/CORS。`structuredClone` 是前端資料複製問題。`builtIn_emitSparkCommand` 是角色動作工具，不是「麥克風一定失敗」的訊號。對應 AIRI 程式修正在[本機課堂修正說明](../../docs/classroom-local-fixes.md)。

## 授權與檔案

課堂程式沿用本倉庫 MIT 授權。第三方模型、字典、資料集和官方展示各有自己的條款，並不繼承 AIRI 授權。這個目錄沒有模型權重、第三方音訊、API keys、使用者 VRM、截圖、錄音、venv 或私人服務 logs。`local/` 是學生自己的實驗輸出，請勿直接把未經同意的真人錄音 commit 上來。

- `asr26/`：MLX 轉錄、tokenizer regression、計時。
- `breeze2/`：CPU TTS adapter、契約測試、產生試聽檔。
- `sources/`：模型之外的媒體來源、參考稿與限制。
- `results/`：2026-10-07 課堂實測的去路徑記錄。
- `testcases.json`：繁體中文、英文技術詞、數字與真人錄音練習。
