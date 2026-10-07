# macOS Apple Silicon runtime 組裝

`build-runtimes.py` 組裝實際 standalone CPython，加上同 ABI 的已安裝 wheels。
它不複製 venv 的 Python symlink，也不依賴收件者的 Homebrew、MacPorts 或 Python framework。

本次四個 runtime：

| 路徑 | Python | 用途 |
|---|---|---|
| `runtimes/python` | standalone 3.12.13 | installer manager，只用標準函式庫 |
| `runtimes/asr` | standalone 3.12.13 | MLX 0.32.3、Breeze ASR26、Transformers 5.19、PyAV 19.0.1 |
| `runtimes/taigi` | standalone 3.11.15 | Torch 2.14.1、Transformers 4.50.3、KaedeTai、Taibun 1.1.8 |
| `runtimes/kokoro` | standalone 3.12.13 | Torch 2.8、Transformers 5.18、Kokoro 0.9.4 |

保留分開環境，避免 ASR 與 GPT-SoVITS 的 Transformers／NumPy 版本互相覆蓋。
KaedeTai 與 Kokoro 目前都使用 CPU，不能把這個套件標成全模型 MLX。

## 重現流程

先用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的 Apple Silicon install-only 發行建立 CPython。
本次實際使用 uv 已安裝的 3.11.15／3.12.13 standalone。不得改用依赖 `/Library/Frameworks` 的 venv executable。
用課程中的各模型 requirements 建立對應 venv，再執行：

- ASR：`../asr26/requirements-server.txt`（已包含基礎 requirements、FastAPI、PyAV）；Taigi：`../taigi-tts/requirements-tested.txt`。
- Kokoro：`kokoro-runtime-requirements.txt`；Taibun：`../taigi-tts/requirements-taibun.txt`。
- 各 venv 應使用表中的 Python minor version；Taibun 的來源 venv 在本建置程序使用 Python 3.12。

```sh
python3 build-runtimes.py \
  --python311 /path/to/standalone-cpython-3.11 \
  --python312 /path/to/standalone-cpython-3.12 \
  --asr-env /path/to/prepared-asr-venv \
  --taigi-env /path/to/prepared-taigi-venv \
  --kokoro-env /path/to/prepared-kokoro-venv \
  --taibun-env /path/to/prepared-taibun-python312-venv \
  --destination resources/runtimes
python3 audit-runtimes.py resources/runtimes --output resources/runtime-audit.json
python3 validate-runtimes.py resources/runtimes
```

## 固定模型清單與 payload

公開的 `model-manifest.json` 記錄 21 個語音權重／設定檔的 revision、大小、SHA256、下載網址及四個服務的啟動參數。
它不含開發機路徑。薄版只需產生清單，使用者在 App 內選擇模型後才下載：

```sh
python3 prepare-model-payload.py --resources resources
```

完整離線版先閱讀 `MODEL-LICENSES.zh-TW.md`，再準備 payload：

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

## 音訊處理

`kokoro-server.py` 直接用 KModel／KPipeline 讀本地權重與聲線，不需要 Kokoro-FastAPI checkout。
Kokoro 與 KaedeTai 使用 soundfile／libsndfile 1.2.2 寫 WAV、MP3。
Breeze ASR 使用 PyAV 解碼，沒有依賴開發機的 FFmpeg CLI。
FFmpeg／libav、eSpeak、Python 與全部 wheels 的授權仍必須隨 binary release 保留，詳見 MODEL-LICENSES。

## 驗證範圍

本次 862 個 Mach-O 的實際 load dependency 與 symlink 沒有外部缺檔。
上游 wheels 的 build-time install-ID／rpath 另外列為 metadata，不能誤當成實際載入依賴。
移位後的四個 Python 均能啟動。MLX、Torch、Kokoro、Taibun、PyAV 的 isolated imports 通過。
Kokoro 的 Torch 2.8 會把本次程序新建的 JIT 臨時目錄加入 `sys.path`；檢查只允許該上游模組產生的精確目錄，其餘搜尋路徑都必須在封裝 runtime 內。
新 Kokoro adapter 的 WAV／MP3、完整 KaedeTai→Taibun→MP3 也用移位 runtime 實測通過。

這些檢查不等於完成 Developer ID 簽名、Apple notarization 或另一台乾淨 Mac 的驗收。
不得用「本機跑得動」取代正式 release 的來源授權和乾淨環境測試。
