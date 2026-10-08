# AIRI Local 0.4.0 Decisions 驗證

日期：2026-10-09。Apple Silicon M4 Max / 128 GB。

## 自動化驗證

- Decisions 本機管理器與固定 OpenAI adapter：16 項測試通過。全部使用假的 transport；沒有真實 API key 或付費呼叫。
- 既有 manager 回歸：32 項通過。
- 前端 Decisions client/store：22 項通過，包括預設關閉、記憶體 key、缺 key、低信心、逾時、本機先完成、雲端先完成、取消、角色切換、播放前過期結果檢查及本地 ACT 即時分派。
- Motion store 11 項、語音 ACT 4 項、翻譯 2 項通過。
- stage-web 型別檢查、正式 web build 通過。新檔 lint 無錯誤；Stage 既有註解格式 warnings 未列為本次功能錯誤。
- 安裝包邊界測試 11 項通過；安裝器 setup.js 語法檢查通過。

## 安裝包

Full 與 Thin 均為 0.4.0 arm64，ad-hoc code-sign 深層驗證通過；沒有 Developer ID 公證。
已比對 installer/manager.py、decisions.py、web/index.html、web/setup.js 與來源 hash 相同。
未把 MotionGPT 官方權重、私人 MLX 轉換快取、使用者 profile 或 API key 放進安裝包。

## 原生 UI

- Full App 原生啟動成功，保留既有五個模型勾選、角色與對話；重新驗證模型後進入舞台。
- 「機體模組 → 動作」顯示預設關閉的 Decisions 開關、資料傳送範圍，以及安全性文字欄位。未填值時「本次使用」停用；金鑰來源下拉式方塊可操作。本機沒有既有 OpenAI 金鑰，因此沒有實測選用既有真實 key。
- 本機 MotionGPT 顯示 `mlx`，切換套用後載入時間顯示 0.99 秒，服務就緒。
- 啟用 Decisions 但不填 key，新增對話並送出「請把雙手高高舉過頭頂，做一段伸展，並說一句簡短的話。」。VRM 確實舉起雙臂伸展、再回復待機；文字回覆為「好的，現在開始伸展。」。
- 此次連續擷取 185 幀／12 秒；約第 5 秒可見雙臂高舉，第 9 秒已回復。這是單次流程驗證，不能與其他版本的單次畫面時間相比得出加速倍率。
- 返回動作設定顯示「本地 ACT 先選定動作」。測試後已將 Decisions 恢復關閉，沒有儲存或使用測試金鑰。
- 桌寵模式 → 齒輪 → 設定 → 機體模組 → 動作，設定視窗持續正常顯示，沒有閃回桌寵。
- 打包後管理器的真實 loopback 路由：雲端關閉回 400 / cloud_disabled，缺 key 回 400 / missing_key，缺工作階段 token 回 403。這三次均不會呼叫 OpenAI。

既有原生 MLX / 自動對話動作紀錄見 [0.3.0 驗證](native-app-validation.md)。

Thin ZIP 大小 1,610,640,629 bytes；ZIP CRC 檢查通過。SHA-256：`d987804711d7ba6df0d3a8e0585a0f5b55f508e2e9237025c6a3ec6616ac7771`。

## 效能邊界

本次尚未使用真實 OpenAI API key 呼叫 Decisions，因此不提供或推估實測雲端加速倍率。
UI 毫秒值代表後端量到的 Decisions 請求耗時，不包含錄音、STT、前端往返、MotionGPT 生成與 VRM 播放。
原生 MLX 的生成效能另見 [本機實測](backends/README.md)。Decisions 只負責選動作，沒有取代骨架生成。
