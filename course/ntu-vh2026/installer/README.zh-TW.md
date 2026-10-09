# AIRI Local Mac 安裝器

這個資料夾提供 Apple Silicon Mac 本機安裝器的原始碼。它把模型選擇、下載驗證、服務啟動和角色設定串在同一個頁面。模型權重、Python runtimes 與建置後的 AIRI 不存入 Git；安裝包由 release 建置程序提供。

有兩種預設選擇：輕量組合使用 Qwen 3.5 0.8B、Breeze ASR-26 與 Kokoro；完整台語組合再使用 Gemma 4、SARC 與 KaedeTai。Lite 離線包只提供輕量三模型；Full 離線包包含原有六模型，預設使用台語五模型；下載版可選這六模型，預設輕量組合。Thin／Full 另提供預設不勾選的 MotionGPT 動作模型；它不包含在離線 payload 中。

| 組合 | 對話與輸出 | 使用界線 |
|---|---|---|
| 輕量 | Qwen 3.5 0.8B ＋ Breeze ASR-26 ＋ Kokoro | 可用華語語音及圖片描述；不包含台語發音模型。Qwen 是中國阿里巴巴的 Dense 小模型，能力與回答穩定性不能視為等同較大模型。 |
| 完整台語 | Gemma 4 ＋ SARC ＋ Breeze ASR-26 ＋ Kokoro ＋ KaedeTai | 華語／台語各一張角色卡，圖片由 Gemma 4 先描述。 |

完整台語組合包括：

| 角色或功能 | 模型 |
|---|---|
| ReLU 華語 | Gemma 4 12B IT QAT ＋ Kokoro `zf_xiaobei` |
| ReLU 台語（實驗） | SARC Taigi 12B Q4_K_M ＋ Taibun ＋ KaedeTai |
| 共用聽覺 | Breeze ASR-26 MLX 4-bit |
| 圖片描述 | Gemma 4，台語角色接收描述後再回答 |

完整組合建議至少 32 GB 統一記憶體，這是配置估計，尚未以 32 GB Mac 做最低規格驗收。下載頁的大小指模型權重，另需 runtime、暫存與可用磁碟空間。已驗證的台語品質與性能界線見[課堂筆記](../TAIGI-LOCAL-NOTES.zh-TW.md)；不能把開發機實測等同所有 Mac 的乾淨安裝驗收。

## 從安裝包開始

1. 開啟 AIRI Local。安裝器頁面位於 `http://127.0.0.1:17900/setup`。
2. 選擇模型。隨附 Ollama 使用獨立的 `12434` 埠，或選擇已啟動於 `11434` 的 Ollama。
3. 選用 SARC 時，閱讀並確認 Gemma 條款。其他模型顯示其授權連結與 notices。
4. 按「下載並驗證」。Lite／Full 的原有模型可從隨附 payload 驗證。Thin 需下載所選模型；Thin／Full 若選用 MotionGPT，首次另從官方來源下載約 1.336 GB。
5. 驗證完成後按「啟動 AIRI」。依已選模型建立本機專用角色卡（輕量一張，完整台語兩張），使用 AIRI 內建 AvatarSample_A。
6. 在 AIRI 選擇角色、開啟麥克風並授權。也可上傳自己的 VRM。

選了 ASR 的配置會開啟辨識文字自動送出。可在聽覺設定關閉。台語輸出限制短句、台語漢字；英文、未知字與過長文字可能被 TTS 明確拒絕。

再次從安裝頁啟動時，安裝器重接自己建立的角色服務。名稱、提示詞和外觀保留，其他角色卡不變。單純開啟 AIRI 首頁不會匯入設定。重新選取的模型決定啟動哪些服務；未選 TTS 的新角色使用靜音語音 provider。

安裝頁會恢復上次儲存且目前安裝包支援的模型選擇，包括 MotionGPT，但不會自動接受授權條款。

隨附 Ollama 的可寫模型庫固定放在 `~/Library/Application Support/AIRI Local Classroom/local/ollama`。Lite／Full 先驗證隨附權重，再將所選模型以 APFS copy-on-write 複製到這個私人目錄，讓 Ollama 產生的 metadata 不會破壞 App 簽章。這不是 symlink 或 hardlink；更動私人副本不會改到 App。

跨版本重用時會重新比對 SHA-256，已符合固定版本的檔案不重複複製。無法使用 APFS clone 時會檢查完整複製空間，並保留至少 1 GiB；空間不足就停止。`11434` 既有 Ollama 模式不建立或修改這份模型庫。

## 選用 MotionGPT 動作模型

Thin／Full 的模型清單有 **MotionGPT 動作生成**，預設不勾選。Full 雖包含原有六模型，MotionGPT 首次仍需連網直接下載；本發行版不代管或重包這組權重。

使用的是固定版本的 **MotionGPT Base**，不是「最新動作模型」。官方權重模型卡僅標 `cc`，未明示 Creative Commons 的具體版本。程式 MIT 與權重授權分開處理，詳見[授權記錄](MODEL-LICENSES.zh-TW.md)。固定模型、tokenizer 和統計檔合計 1,335,831,259 bytes（約 1.336 GB），不含 runtime 和暫存空間。

1. 在 Thin／Full 安裝頁勾選 MotionGPT，完成下載驗證，再啟動 AIRI。
2. 使用 VRM 角色，開啟「機體模組 → 動作」。Live2D 不支援此功能。
3. 確認本機服務位址為 `http://127.0.0.1:17905`，啟用模組並按「測試服務」。
4. 輸入簡短動作描述，按「生成並預覽」，檢查正面、側面與姿態恢復。
5. 手動預覽成功後，再明確開啟「允許對話自動生成動作」。這個開關預設關閉。

安裝頁選用模型只代表準備並啟動服務，不會替使用者開啟對話自動生成。Lite 不含 MotionGPT runtime，也沒有此安裝選項；Lite 的「動作」頁仍可連接使用者另外啟動的 loopback 本機服務。

v0.4.1 手動測試可輸入中文。目前「意識」選用的本機語言模型會先轉成英文，頁面顯示實際英文後再交給 MotionGPT。英文直接生成。未設定本機模型、選用雲端模型或轉換失敗時會顯示原因，不會偷偷切到雲端或下載其他模型。MotionGPT 本身的 tokenizer 仍無法直接理解這些中文描述。

「動作」頁可選自動、CPU、Apple Metal（PyTorch MPS）或原生 MLX。自動模式在可用時優先 MLX，載入失敗保留 CPU 並顯示原因。首次 MLX 使用會在私人模型目錄轉換約 1 GB 的本機快取，後續不用重複轉換。[本機數值與速度驗證](../motiongpt/README.zh-TW.md)記錄結果；不同後端的隨機取樣可能產生不同長度，不能只用單次耗時推論所有 Mac 的效能。

模型生成 22 關節位置序列，再轉成 VRM 骨架動作。v0.4.1 保留按角色腿長縮放並限幅的上下位移，讓跳躍離地、蹲下保留高度變化；水平走位仍移除。停止或播完會還原待機位置，鏡頭不追隨骨盆上下移動。沒有腳部 IK、碰撞、手指細節或精準舞蹈／音樂節拍保證。預編 `wave`／`dance` 等短動作仍可使用；新模型生成與預編動作是不同來源。

## v0.4.0 選配 OpenAI Decisions

在 VRM 的「機體模組 → 動作」可啟用雲端動作判斷，**預設關閉**，不需要為本機功能提供 API key。明確啟用並提供 key 後，才由本機管理器把當前使用者文字送到固定的 `https://api.openai.com/v1/decisions`，使用 `gpt-6-luna`。此功能不傳送圖片、原始音訊、歷史對話、VRM 或骨架；動作生成與播放仍在本機，原本選用的語音與視覺 provider 不變。

可輸入只保留於本次 App 工作階段的 key，或明確選用已設定的 OpenAI provider key；既有 provider key 的儲存方式不變。不要把「本次 key 不落盤」理解成既有 provider 設定也改成暫存。沒有 key、未啟用或非 VRM 時，不發出這項雲端請求。

本機 LLM 與雲端判斷共用每回合的動作仲裁，第一個有效結果先執行，晚回結果不覆寫。雲端拒答、低信心或連線失敗會保留本機路徑。生成動作的固定選項仍受 MotionGPT 啟用與「允許對話自動生成動作」開關限制。Lite／Full 原有離線模型缺漏時不會改用這個 API 補上。

尚未用付費 API 實測速度或判斷品質。現有測試使用模擬回應，不能當成雲端加速證據；說明與課堂案例見[Decisions 與動作](../motiongpt/decisions-and-motion.md)。

## 原始碼與本機邊界

- `manager.py` 只綁 `127.0.0.1:17900`，安裝動作需要同源請求與本次程序 token。下載與啟動都受固定清單限制。
- 靜態 JSON 資源保留原始 UTF-8 位元組；API 物件才進行 JSON 序列化，避免模型設定檔載入時發生 bytes 型別錯誤。
- `web/` 是無外部套件的安裝頁，不載入分析碼或遠端 JS。
- AIRI 的匯入需同時符合編譯旗標 `VITE_AIRI_LOCAL_INSTALLER=true`、精確本機 origin 與 `?localSetup=1`。
- 選用的 MotionGPT 只綁本機 `17905`；安裝器只按固定清單從官方來源下載其檔案，不接受任意模型網址。
- Decisions 請求需精確本機 origin 與管理器 token；後端只接受固定 OpenAI 端點與模型，不跟隨重新導向，不記錄或儲存 key／文字，也不接受任意服務網址。
- App 內的 ASR 為 `18001`，華語 TTS 為 `18880`，台語 TTS 為 `18883`，共用 speech hub 為 `18884`。這與手動教學用的 `8001/8880/8883/8884` 分開。
- 發現不屬於安裝器的埠占用時會回報，避免終止未知程序。
- Ollama 模型 digest、模型檔 SHA-256 與 payload manifest 用於確認版本；不把模型「存在」等同「已驗證」。

安裝器不會把 ChatGPT 訂閱轉成 API 額度。選用 Decisions 可能產生 OpenAI API 費用；切到其他雲端 provider 後，相應請求會送往該雲端服務，與 Decisions 的資料範圍分開計算。

## 授權與 release 資料

`collect-license-notices.py` 收集原作者模型卡、Gemma 全文與 NOTICE、其他授權全文，以及實際影音函式庫對應來源。Gemma 頁面轉成純文字供離線閱讀，不把第三方 HTML 腳本帶入本機 origin。

```sh
python3 course/ntu-vh2026/installer/collect-license-notices.py
```

輸出位於忽略版控的 `resources/licenses/`。其中 `upstream-source-manifest.json` 記錄 URL、SHA-256 和位元組數，`source/` 保留影音函式庫的對應原始碼。檔案、權重與 runtime 各自的授權不因打包而改成 MIT。詳見[授權查核](MODEL-LICENSES.zh-TW.md)及[第三方 notices](THIRD-PARTY-NOTICES.md)。

## 已執行的程式檢查

```sh
node --test course/ntu-vh2026/installer/test-setup-state.mjs
python3 course/ntu-vh2026/installer/test-manager.py
python3 course/ntu-vh2026/installer/test-decisions.py
pnpm -F @proj-airi/stage-web exec vitest run src/composables/local-installer-config.test.ts src/composables/local-installer.test.ts --project unit
pnpm -F @proj-airi/stage-web typecheck
```

前端狀態 5 項、AIRI 設定匯入 10 項測試通過，stage-web typecheck 通過。安裝管理器測試以其最新輸出為準。完整根目錄 `pnpm lint` 仍因此開發 checkout 缺少 `docs` 的 `@radix-ui/colors` 而失敗；本次變更的 scoped ESLint 通過。
