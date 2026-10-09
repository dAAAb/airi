# AIRI Local：Apple Silicon 課程 App

這是 dAAAb 課程版的獨立 Electron 啟動殼，Bundle ID 為 `ai.daaaab.airi-local-classroom`。它不使用上游 AIRI 的更新服務，也不會取代使用者原有的 Ollama。

0.2.0 加入透明桌寵模式。角色頁的「桌寵模式」與原生「桌寵」選單可切換；`⌘⌥P` 或 Dock 圖示可解除滑鼠穿透並找回角色。模式切換保留同一個 renderer，不重啟錄音或對話。[完整操作與語意動作教學](../DESKTOP-PET.zh-TW.md)。

從桌寵齒輪開啟設定時，App 暫時使用一般視窗。返回角色主頁後才恢復桌寵；同頁的網址或歷史紀錄更新不會觸發恢復。

preload 只公開固定的模式／置頂／穿透控制，透過 Eventa 傳遞，主程序驗證視窗、主 frame 與精確 origin。建置會把既有 workspace 依賴編入 main 與 sandboxed preload。

App 以同一個 `http://127.0.0.1:17900` origin 顯示安裝頁與編譯後的 AIRI。管理服務擁有自己的 Ollama（12434）及推論服務；資料放在 `~/Library/Application Support/AIRI Local Classroom/local`。關閉 App 時，管理服务會關閉它自己啟動的子程序。

## 三種產物

- **lite — AIRI Local Lite.app**：離線包只帶 Qwen 3.5 0.8B、Breeze ASR-26、Kokoro，移除兩個 12B 模型、KaedeTai 與台語 TTS runtime。不含 MotionGPT runtime，也沒有 MotionGPT 安裝選項；動作頁仍可連接外部本機服務。可以用 ASR 聽台語；Kokoro 仍是中文發聲，不能把 Lite 說成具備完整台語對話語音。Qwen 來自中國阿里巴巴，模型的小參數量與產地是不同維度。
- **thin — AIRI Local.app**：帶瀏覽器、Python、Ollama、全部語音推論 runtime 與 AIRI。第一次開啟時勾選模型、閱讀必要條款並下載固定版本的權重。預設選 Lite 三項，可另外選完整台語組。包含 MotionGPT 程式／runtime，安裝頁的 MotionGPT 選項預設不勾選；勾選後從官方下載。
- **full — AIRI Local Full.app**：另外帶全部六項模型 payload，預設原本的 SARC／Gemma 4／ASR／Kokoro／KaedeTai 五項，也可改選 Qwen。初次開啟仍先驗證模型與必要條款。MotionGPT 程式／runtime 隨附，但權重不在這六項 payload 中；選項預設不勾選，首次使用仍需直接從官方下載約 1.336 GB。

Lite 與 Full 的 Electron renderer 會擋下非 loopback 的 HTTP／HTTPS 請求。原有離線模型缺漏時顯示錯誤，不能悄悄改用雲端。Full 的 MotionGPT 首次下載是安裝管理器在明確勾選後按固定官方清單執行。v0.4.0 的 Decisions 是另一個明確選配的連網入口：由本機管理器轉送當前文字到固定 OpenAI API，預設關閉，並未全面開放 renderer 連網。三種 App 共用課程 Bundle ID 與使用者資料，單次只開啟一個。

thin 也包含 Torch 等 runtime，不能把它描述成只有幾 MB 的下載器。模型權重大小、安裝後大小、壓縮檔大小與記憶體需求是不同數字。

## MotionGPT：先預覽，再開啟對話生成

使用的是固定 **MotionGPT Base**，不宣稱是最新模型。官方權重模型卡僅標 `cc`，未明示 CC 變體；本 Release 不代管或重包權重。Thin／Full 可選用官方直接下載，Lite 可自行連接外部本機服務。來源與授權政策見[模型記錄](../installer/MODEL-LICENSES.zh-TW.md)。

在 VRM 角色的「機體模組 → 動作」啟用模組，確認 `http://127.0.0.1:17905`，按「測試服務」。輸入一句動作描述，按「生成並預覽」，再決定是否開啟「允許對話自動生成動作」；後者預設關閉。Live2D 不支援此模組。

0.4.3 在手動測試加入「跪地上」「趴下來」「跌倒」三句完整匹配對照，避免極小模型把跪誤譯成趴。頁面標明內建對照來源；否定、複合或指定左右的句子仍走本機模型。

0.4.1 的手動測試支援輸入中文：先用「意識」目前選用的本機語言模型轉成英文，顯示實際描述，再送給 MotionGPT。英文直接生成。若未設定本機對話模型、選用雲端來源或轉換失敗，頁面會說明原因；不會擅自下載另一個模型或把中文送到雲端。這是前處理支援，並非 MotionGPT 權重突然學會中文。

動作設定可切換 CPU、PyTorch Metal／MPS、原生 MLX；自動模式優先 MLX。此 Mac 的 MLX 暖機生成比先前 CPU／MPS 快，且已用相同 token 比對模型數值；這不是所有 Mac 的效能保證。[實測與限制](../motiongpt/README.zh-TW.md)。第一次使用 MLX 另建立約 1 GB 的私人權重快取，無需再次下載模型。

生成的 22 關節序列轉為 VRM 骨架動作。0.4.2 在旋轉後用全身支撐骨節校正高度，修正第一幀已趴／跪卻仍位於站姿高度的問題。來源地面固定為 HumanML3D 的 Y=0，負向預測誤差不會把整段抬高；跳躍保留按角色腿長縮放、範圍受限的離地高度。水平走位仍移除，停止或播完會還原待機位置。這是骨架支撐面校正，不含網格厚度、碰撞、腳部 IK 或手指細節。模型未生成跌倒或本身懸空時，校正不會替它捏造動作。預編短動作仍可使用。詳見[趴跪與地面測試](../results/motiongpt/ground-contact/README.zh-TW.md)。

## v0.4.0：選配雲端動作判斷

VRM 的「機體模組 → 動作」可明確啟用 OpenAI Decisions，**預設關閉**。啟用且有 API key 時，僅傳送當前使用者文字（含 STT 辨識文字），不傳送圖片、原始錄音、聊天歷史、VRM 或骨架。端點固定為 OpenAI Decisions API、模型固定為 `gpt-6-luna`。語音與視覺保留原本的 provider 設定；動作生成與播放仍在本機。

可輸入只保留於本次 App 工作階段的 key，或明確選用已設定的 OpenAI provider key。後者沿用原有 provider 儲存方式，並未改成暫存或新增加密。沒有 key 時不送出請求。API 額度與 ChatGPT 訂閱分開計費。

雲端只在固定動作選項中判斷；伸展、深蹲、拳擊、左手揮手等選項對應固定的本機 MotionGPT 描述。其他新動作仍交由本機 LLM。每回合第一個有效動作結果先執行，晚回結果不覆寫。信心值低於 0.6、拒答、逾時或失敗時繼續本機路徑；0.6 是初始策略門檻，不是校準後的準確率。

雲端選到生成動作時，仍需已啟用本機 MotionGPT，並明確開啟「允許對話自動生成動作」。此 API 不能繞過這兩項設定。模擬測試涵蓋請求格式、錯誤與競速處理；**尚未驗證付費 API 的實際速度與判斷品質**。[設計、範例與限制](../motiongpt/decisions-and-motion.md)。

## 安全界線

Renderer 使用 sandbox、context isolation，停用 Node integration 與 webview。沒有提供任意執行 shell 的 preload API。麥克風只授權給 17900 的本機頁面與音訊請求，仍需通過 macOS 的麥克風同意。相機、位置等請求不予授權。

外部 HTTPS 連結交由系統瀏覽器處理，不能嵌入 App 執行。App 先檢查管理埠是否占用，拒絕接管未知服務。退出時只發訊號給它自己的 Python ChildProcess，不搜尋或終止名為 `ollama` 的程序。

## 從原始碼建置

需要 macOS Apple Silicon、Node／pnpm 與 Python 3。這個流程使用預編譯 Electron，不編譯 Swift，也不修改 Xcode 授權設定。

先依 [installer](../installer) 的來源與 runtime 流程準備 `../installer/resources/`：

```text
resources/
  payload-manifest.json
  runtimes/python/bin/python3
  runtimes/asr/...
  runtimes/taigi/...
  runtimes/kokoro/...
  runtimes/motiongpt/...     # Thin／Full；由 build-runtimes.py --motiongpt-env 組裝
  runtimes/ollama/ollama
  upstream/kaedetai/...
  web/local-models/onnx-community/silero-vad/onnx/model.onnx
  payload/...                # Full 的原有六模型，不包含 MotionGPT
```

從 repository root 執行：

```sh
python3 course/ntu-vh2026/desktop/download-electron.py
python3 course/ntu-vh2026/desktop/stage-ollama.py
sh course/ntu-vh2026/desktop/build-web.sh
python3 course/ntu-vh2026/desktop/build-app.py --mode thin
# 已備齊 Qwen、ASR、Kokoro 後，輸出最小離線組
python3 course/ntu-vh2026/desktop/build-app.py --mode lite
# 或：所有 payload 檔案準備完成後
python3 course/ntu-vh2026/desktop/build-app.py --mode full
```

固定下載來源：

| 元件 | 來源與驗證 |
| --- | --- |
| Electron 43.4.1 arm64 | [官方 release](https://github.com/electron/electron/releases/tag/v43.4.1)，SHA256 `fe3cac8cbfd9ba1739fac6c69166cf30848741f93cbe251d800ae6ef7cebb64b` |
| Ollama 0.35.1 Darwin CLI | [官方 release](https://github.com/ollama/ollama/releases/tag/v0.35.1)，SHA256 `3137dbf28948ee844e0fb3e584d9b5de6879d73d9f0cb7eff3ad64930601d307` |

打包腳本會保留 Electron／Ollama 授權，並攜帶工作區固定版本 onnxruntime-web 1.27.0 的 WASM／MJS／MIT 授權。課程來源不含模型、venv、個人錄音或登入資料。模型及第三方 runtime 的個別授權仍依 [授權清單](../installer/MODEL-LICENSES.zh-TW.md) 辦理。

Apple APFS 可用 copy-on-write 複製既有 payload，減少此機器重複占用。腳本保留至少 5 GiB 的實際剩餘空間；不支援 clone 時會先檢查實際複製空間。一般下載後解壓的電腦仍需要完整安裝容量。

產物預設放在本資料夾 `dist/`。腳本拒絕覆蓋既有產物。預設僅做 ad-hoc signing，**沒有 Developer ID 簽署或 Apple notarization**。不能把本機成功啟動等同於已完成公開發行簽署。

Lite／Full 的壓縮包可能超過 GitHub 單一 asset 限制。`package-release.py` 串流產生每段至多 1.8 GB 的分片、SHA256 清單及小型 `Installer.zip`，避免先建立巨大壓縮檔。`Installer.zip` 保留組裝腳本的執行權限；把它與所有分片放在同一資料夾，解壓後雙擊 `Open-*.command`，即可先驗證再組装。

```sh
python3 course/ntu-vh2026/desktop/package-release.py \
  'course/ntu-vh2026/desktop/dist/AIRI Local Full.app' \
  --output course/ntu-vh2026/desktop/dist/packages/full \
  --prefix AIRI-Local-Full-0_1_0-arm64
```

指定 `--upload-release TAG` 時，只允許上傳到已存在的 draft release。每段都要收到 GitHub 對應的大小與 SHA256 才刪除本機暫存，失敗則保留檔案。預設不會上傳，也不會建立 release。

## 一鍵下載分片

完成 multipart 封裝後，可另外產生小型 `*-Downloader.zip`。學生只需下載這個 ZIP、解壓後雙擊 `Download-*.command`。原本的手動 `*-Installer.zip` 保留。

```sh
python3 course/ntu-vh2026/desktop/generate-download-installer.py \
  path/to/AIRI-Local-Full-0_1_0-arm64-parts.json \
  --output path/to/downloaders \
  --unpacked-bytes ACTUAL_APP_BYTES
python3 course/ntu-vh2026/desktop/test-download-installer.py
```

`ACTUAL_APP_BYTES` 使用封裝前 App 的邏輯檔案總大小。下載器固定從 `dAAAb/airi` 下載 manifest 指定的分片，不接受自訂 URL。新版本請指定 `--release-tag v0.2.0-ntu2026-local`；省略時保留 0.1.0 的重現流程。請等全部分片上傳完成、manifest 定案後再產生下載器。

下載前檢查剩餘分片容量、解壓後 App 大小，再保留 2 GiB 餘裕。檔案放在解壓下載器的同一資料夾；空間不足時，先把整個資料夾搬到其他磁碟。已通過驗證的分片不重抓，未完成分片支援續傳。所有 SHA256 與大小通過後才解壓到新的資料夾，再執行 `codesign --verify` 並開啟資料夾。分片保留供離線搬運，下載器不修改 Gatekeeper。

測試使用極小 App fixture 和 fake curl，涵蓋缺片下載、續傳、已驗證片重用、錯誤 hash 拒絕、磁碟不足、symlink／檔名越界拒絕及 ZIP 執行權限。

## 檢查

```sh
node --test course/ntu-vh2026/desktop/test-policy.cjs
python3 course/ntu-vh2026/desktop/test-build-app.py
python3 course/ntu-vh2026/desktop/test-package-release.py
```

安全策略測試涵蓋精確 origin、音訊權限、外部 URL scheme 與 offline 網路限制。打包測試涵蓋模型缺漏、越界路徑、外部 symlink 及 HTTPS 下載來源。這些測試不能取代實際 App 的麥克風、離線推論與乾淨機器驗證。

Lite 的測試另外確認只複製 Qwen manifest 引用的 blobs，不會連同原目錄裡的 SARC／Gemma 權重一起打包。主執行檔與 `CFBundleExecutable` 必須同時重新命名；保留 `Electron` 檔名可能讓 Electron 誤判為開發模式。啟動器也會驗證自家 `build-info.json` 的 Bundle ID 再定位固定 Resources。

Mac build 的 `VITE_AIRI_LOCAL_INSTALLER=true` 會停用 PWA service worker 的產生與註冊，由 App 封裝管理前端更新。一般網頁版仍保留 PWA。更新測試若發現舊 service worker 接管，僅清除該 App origin 的 `serviceworkers`／`cachestorage`，保留 localStorage、IndexedDB 中的角色、設定及對話。

參考：[Electron 官方手動打包文件](https://www.electronjs.org/docs/latest/tutorial/application-distribution)、[Electron 權限 API](https://www.electronjs.org/docs/latest/api/session)。
