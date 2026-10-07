# AIRI Local：Apple Silicon 課程 App

這是 dAAAb 課程版的獨立 Electron 啟動殼，Bundle ID 為 `ai.daaaab.airi-local-classroom`。它不使用上游 AIRI 的更新服務，也不會取代使用者原有的 Ollama。

App 以同一個 `http://127.0.0.1:17900` origin 顯示安裝頁與編譯後的 AIRI。管理服務擁有自己的 Ollama（12434）及推論服務；資料放在 `~/Library/Application Support/AIRI Local Classroom/local`。關閉 App 時，管理服务會關閉它自己啟動的子程序。

## 三種產物

- **lite — AIRI Local Lite.app**：離線包只帶 Qwen 3.5 0.8B、Breeze ASR-26、Kokoro，移除兩個 12B 模型、KaedeTai 與台語 TTS runtime。可以用 ASR 聽台語；Kokoro 仍是中文發聲，不能把 Lite 說成具備完整台語對話語音。Qwen 來自中國阿里巴巴，模型的小參數量與產地是不同維度。
- **thin — AIRI Local.app**：帶瀏覽器、Python、Ollama、全部語音推論 runtime 與 AIRI。第一次開啟時勾選模型、閱讀必要條款並下載固定版本的權重。預設選 Lite 三項，可另外選完整台語組。
- **full — AIRI Local Full.app**：另外帶全部六項模型 payload，預設原本的 SARC／Gemma 4／ASR／Kokoro／KaedeTai 五項，也可改選 Qwen。初次開啟仍先驗證模型與必要條款。

Lite 與 Full 的 Electron 會擋下非 loopback 的 HTTP／HTTPS 請求。模型缺漏時顯示錯誤，不能悄悄改用雲端。三種 App 共用課程 Bundle ID 與使用者資料，單次只開啟一個。

thin 也包含 Torch 等 runtime，不能把它描述成只有幾 MB 的下載器。模型權重大小、安裝後大小、壓縮檔大小與記憶體需求是不同數字。

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
  runtimes/ollama/ollama
  upstream/kaedetai/...
  web/local-models/onnx-community/silero-vad/onnx/model.onnx
  payload/...                # full 使用
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

full 通常超過 GitHub 單一 asset 限制。發行時應建立含分片 hash 的分割封裝，避免先在空間不足的硬碟產生一個巨大壓縮檔。本腳本不會自行上傳或建立 release。

## 檢查

```sh
node --test course/ntu-vh2026/desktop/test-policy.cjs
python3 course/ntu-vh2026/desktop/test-build-app.py
```

安全策略測試涵蓋精確 origin、音訊權限、外部 URL scheme 與 offline 網路限制。打包測試涵蓋模型缺漏、越界路徑、外部 symlink 及 HTTPS 下載來源。這些測試不能取代實際 App 的麥克風、離線推論與乾淨機器驗證。

Lite 的測試另外確認只複製 Qwen manifest 引用的 blobs，不會連同原目錄裡的 SARC／Gemma 權重一起打包。主執行檔與 `CFBundleExecutable` 必須同時重新命名；保留 `Electron` 檔名可能讓 Electron 誤判為開發模式。啟動器也會驗證自家 `build-info.json` 的 Bundle ID 再定位固定 Resources。

參考：[Electron 官方手動打包文件](https://www.electronjs.org/docs/latest/tutorial/application-distribution)、[Electron 權限 API](https://www.electronjs.org/docs/latest/api/session)。
