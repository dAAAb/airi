# macOS Apple Silicon runtime 組裝

`build-runtimes.py` 組裝實際 standalone CPython，加上同 ABI 的已安裝 wheels。
它不複製 venv 的 Python symlink，也不依賴收件者的 Homebrew、MacPorts 或 Python framework。

原有四個 runtime，加上 Thin／Full 選用功能的 MotionGPT runtime：

| 路徑 | Python | 用途 |
|---|---|---|
| `runtimes/python` | standalone 3.12.13 | installer manager，只用標準函式庫 |
| `runtimes/asr` | standalone 3.12.13 | MLX 0.32.3、Breeze ASR26、Transformers 5.19、PyAV 19.0.1 |
| `runtimes/taigi` | standalone 3.11.15 | Torch 2.14.1、Transformers 4.50.3、KaedeTai、Taibun 1.1.8 |
| `runtimes/kokoro` | standalone 3.12.13 | Torch 2.8、Transformers 5.18、Kokoro 0.9.4 |
| `runtimes/motiongpt` | standalone 3.12.13 | Torch 2.8、Transformers 4.44.2、MLX／Metal 0.32.3、MotionGPT Base；Lite 不包含 |

保留分開環境，避免 ASR 與 GPT-SoVITS 的 Transformers／NumPy 版本互相覆蓋。
KaedeTai 與 Kokoro 目前都使用 CPU，不能把這個套件標成全模型 MLX。MotionGPT 支援 CPU、PyTorch MPS 及原生 MLX，auto 優先 MLX。MLX 的 T5、VQ decoder、關節還原都在 Metal 執行；PyTorch 僅用於第一次把官方 checkpoint 轉換為私人 safetensors 快取。

## 重現流程

先用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的 Apple Silicon install-only 發行建立 CPython。
本次實際使用 uv 已安裝的 3.11.15／3.12.13 standalone。不得改用依赖 `/Library/Frameworks` 的 venv executable。
用課程中的各模型 requirements 建立對應 venv，再執行：

- ASR：`../asr26/requirements-server.txt`（已包含基礎 requirements、FastAPI、PyAV）；Taigi：`../taigi-tts/requirements-tested.txt`。
- Kokoro：`kokoro-runtime-requirements.txt`；Taibun：`../taigi-tts/requirements-taibun.txt`。
- MotionGPT：`../motiongpt/requirements.txt`，以 CPython 3.12 建立獨立 venv；測試環境的完整版本見 `../motiongpt/requirements-lock.txt`。
- 各 venv 應使用表中的 Python minor version；Taibun 的來源 venv 在本建置程序使用 Python 3.12。

```sh
python3 build-runtimes.py \
  --python311 /path/to/standalone-cpython-3.11 \
  --python312 /path/to/standalone-cpython-3.12 \
  --asr-env /path/to/prepared-asr-venv \
  --taigi-env /path/to/prepared-taigi-venv \
  --kokoro-env /path/to/prepared-kokoro-venv \
  --taibun-env /path/to/prepared-taibun-python312-venv \
  --motiongpt-env /path/to/prepared-motiongpt-python312-venv \
  --destination resources/runtimes
python3 audit-runtimes.py resources/runtimes --output resources/runtime-audit.json
python3 validate-runtimes.py resources/runtimes
```

`--motiongpt-env` 是新增的選用參數，使用與 `--python312` 相同 ABI 的已備妥環境。省略時不建立 MotionGPT runtime；Lite 的 App builder 會排除此 runtime 與服務。此參數只組裝程式環境，不下載或封裝 MotionGPT 權重。

## 固定模型清單與 payload

公開的 `model-manifest.json` 記錄原有 21 個語音權重／設定檔與 8 個 MotionGPT 相關檔案的 revision、大小、SHA256、下載網址和服務參數。MotionGPT 列在 `download_only_models`，不放入可再散布的 payload。
它不含開發機路徑。薄版只需產生清單，使用者在 App 內選擇模型後才下載：

```sh
python3 prepare-model-payload.py --resources resources
```

Lite／Full 的原有模型先閱讀 `MODEL-LICENSES.zh-TW.md`，再準備 payload。以下 `--download-speech`／`--verify-speech` 會略過 MotionGPT；它由安裝頁的選用流程直接向官方下載：

```sh
# 下載約 2.72 GB 語音權重；每個檔案驗證後才原子替換。
python3 prepare-model-payload.py --resources resources --download-speech
# 無網路的重驗：
python3 prepare-model-payload.py --resources resources --verify-speech
# 已下載三個固定 Ollama 模型後，只複製清單中的模型（另約 15.77 GB）。
python3 bundle-ollama-models.py --source /path/to/ollama-model-store \
  --destination resources/payload/ollama --apfs-clone
# 只準備 Lite 的 Qwen 0.8B（共約 1.32 GB，含視覺 projector 與 draft 權重）：
python3 bundle-ollama-models.py --source /path/to/ollama-model-store \
  --destination /path/to/lite-payload/ollama --apfs-clone --models qwen
```

KaedeTai 程式碼與作者的合成參考音訊由 `python3 ../taigi-tts/prepare.py kaedetai --download --source-only` 依該目錄 `source-manifest.json` 的固定 commit 取得，
將其 `../taigi-tts/kaedetai/GPT-SoVITS` 放到 `resources/upstream/kaedetai`，保留 LICENSE，排除 `.git` 和 `__pycache__`。
不要複製個人錄音、模型快取目錄或任何 API key。
App builder 的 `--mode full` 會把清單 `offline` 改成 true；薄版則保持 false。
`../desktop/README.zh-TW.md` 說明 Electron、Ollama、前端與最終 App 的組裝。

目的地必須沒有同名 runtime。工具拒絕覆蓋，避免破壞現有版本。
Mac 使用 APFS clone 減少暫存空間，其他檔案系統不在本次驗證範圍。
Taibun 是純 Python，複製至 taigi runtime，沿用該 runtime 原有的 cp311 msgpack。
PyAV wheel 的 cp312 套件與原生 libav 一起複製至 asr runtime。

`relocate-python.py` 將 CPython install-ID 改成 `@rpath`，重設 build-time sysconfig prefix，重新 ad-hoc 簽署 libpython。
來源 CPython 不會被修改。它保留每個套件的 dist-info 與 license 檔。
刪除舊 bytecode 和 venv bootstrap，避免夾帶開發機路徑。

## MotionGPT 動作服務

Thin／Full 隨附選用功能的程式與 runtime，安裝頁預設不勾選 MotionGPT。Full 的原有六模型可離線使用，但首次選用 MotionGPT 仍需下載約 1.336 GB。官方模型卡只寫 `cc`，未明示變體，因此本發行版不重包權重，見[授權記錄](MODEL-LICENSES.zh-TW.md)。

管理器以 `runtimes/motiongpt/bin/python3.12` 啟動 `../motiongpt/server.py`，服務位於 `127.0.0.1:17905`。只有選用模型才啟動；模型檔案依固定清單驗證。Lite 沒有此 runtime 和安裝選項，但 AIRI 動作頁可連接使用者另外啟動的本機服務。

MotionGPT Base 不是最新模型。這次保留固定版本，方便比對真實生成、VRM 轉換與預編動作。CPU／MPS 單次資料見[benchmark](../results/motiongpt/benchmark.json)，包含輸出幀數與載入時間，不能直接當成所有工作負載的速度排名。

輸出是 20 fps、最多 196 幀的 HumanML3D 22 關節位置。前端移除角色根節點走位，轉為 VRM 0／1 的原地骨架旋轉；沒有腳部 IK、碰撞或精準舞蹈保證。先在「機體模組 → 動作」啟用並預覽，再另行開啟預設關閉的對話自動生成。

## 音訊處理

`kokoro-server.py` 直接用 KModel／KPipeline 讀本地權重與聲線，不需要 Kokoro-FastAPI checkout。
Kokoro 與 KaedeTai 使用 soundfile／libsndfile 1.2.2 寫 WAV、MP3。
Breeze ASR 使用 PyAV 解碼，沒有依賴開發機的 FFmpeg CLI。
FFmpeg／libav、eSpeak、Python 與全部 wheels 的授權仍必須隨 binary release 保留，詳見 MODEL-LICENSES。

## 驗證範圍

原有四個 runtime 的既存驗收中，862 個 Mach-O 的實際 load dependency 與 symlink 沒有外部缺檔。這個數字不包含新增的 MotionGPT runtime。
上游 wheels 的 build-time install-ID／rpath 另外列為 metadata，不能誤當成實際載入依賴。
移位後的四個 Python 均能啟動。MLX、Torch、Kokoro、Taibun、PyAV 的 isolated imports 通過。
Kokoro 的 Torch 2.8 會把本次程序新建的 JIT 臨時目錄加入 `sys.path`；檢查只允許該上游模組產生的精確目錄，其餘搜尋路徑都必須在封裝 runtime 內。
新 Kokoro adapter 的 WAV／MP3、完整 KaedeTai→Taibun→MP3 也用移位 runtime 實測通過。

新增 MotionGPT runtime 必須另做移位、isolated imports 與服務健康檢查，不能沿用上述四個 runtime 的通過記錄。

這些檢查不等於完成 Developer ID 簽名、Apple notarization 或另一台乾淨 Mac 的驗收。
不得用「本機跑得動」取代正式 release 的來源授權和乾淨環境測試。
