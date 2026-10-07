# AIRI Local 0.2.0 原生驗收紀錄

2026-10-08，Apple Silicon M4 Max、128 GiB 統一記憶體。以下區分已觀察的畫面與離線骨架量測；不是通用相容性保證。

## 原生 App 已觀察

- 使用 Full App、內建 AvatarSample_A（VRM 0），Gemma 4 12B 經既有本機 Ollama 11434，Kokoro `zf_xiaobei` 經 App 本機語音服務。
- 一般視窗與桌寵可相互切換；未送出文字「桌寵草稿保留測試」仍保留。
- 桌寵的聊天歷史、輸入區與工具列可同時使用；聊天可收起，舞台持續顯示。
- 置頂開關可切換；滑鼠穿透後，以 `⌘⌥P` 恢復可互動視窗。
- 「再向大家揮手一次，說嗨就好」觸發手臂動作與開心表情，之後恢復待機。
- 「我們的作品得獎了！請用一小段開心的舞蹈慶祝」觸發短律動與表情，之後恢復待機。
- 本機語音服務紀錄上述回答的 TTS HTTP 200；這不等於真人台語收音與發音重新驗收。
- App 結束後，17900／12434 私人服務停止，使用者既有 11434 Ollama 持續運行。

## 方向錯誤與修正

上述畫面最初只能證明「有動作」，不能證明動作方向正確。使用者提醒後，量測發現 VRM 0 直接套用 VRM 1 旋轉的方向錯誤。已依官方 VRMA 的版本轉換修正 quaternion x／z，保留左右骨頭 ID。

四個實際模型（內建 A／B、課堂 VRM 0／1）與實際 idle clip 的骨架量測通過。Avatar A 的鞠躬，頭部前移由 −8.63 cm 變成 +8.80 cm；揮右手由越過身體左側改成留在角色右側。詳見[原始量測](desktop-pet-vrm-directions.json)。CI 使用獨立通用骨架，不依賴未隨 repository 散布的角色檔。

**方向修正後的最後原生畫面檢查尚待完成：Mac 鎖定，無法操作 UI。** 未將此項記成通過。拖曳的實際位移、附件草稿、拔除螢幕與真人麥克風本次也沒有完整驗收。

## 最終 Full 包的服務驗收

鎖定期間另用最終 App 內的 LocalManager、Ollama 與語音執行環境，在 `/tmp` 的隔離資料目錄啟動服務；沒有操作 GUI、下載模型或改動使用者設定。Gemma／ASR／Kokoro 檔案與模型識別碼驗證、私人服務啟動及清理，共 11 個條件通過。

- 隨附 Ollama 0.35.1：Gemma 回 HTTP 200，單次 2.394 秒；這是服務可用性測試，回覆受 token 上限截斷，不是回答品質評分。
- Speech hub → Kokoro：HTTP 200，4.0 秒 WAV，生成耗時 0.577 秒。
- Breeze ASR：health HTTP 200；沒有輸入真人錄音。
- App 簽章在測試前後均通過；既有 11434 的版本與 PID 未改變。測試建立的私人服務全部停止。

[原始服務驗收報告](desktop-pet-full-backend-smoke.json)。本次沒有重新測試 SARC／KaedeTai 的完整台語語音鏈。

## 自動檢查與限制

- Marker parser／chat orchestrator：57 tests 通過。
- VRM 程序動作：23 tests 通過，包含 VRM 0／1、不同模型朝向、右手／前向與姿態恢復。
- 本機 manager：27 tests 通過，涵蓋 Ollama 0.35／0.40 的固定識別碼及逐檔驗證。
- 原生視窗狀態／來源政策：10 tests 通過。
- 打包／下載器／分片：9＋11＋1 tests 通過。
- 受影響套件型別檢查與新增／修改檔案 lint 通過；原有 Stage／VRMModel 註解警告保留。
- 全 repository lint 被既有 docs 缺少 `@radix-ui/colors` 阻擋；root typecheck 的 Turbo 子程序嘗試在受限全域路徑安裝 pnpm，未完成。沒有把這兩項記成通過。
- 三種 App 為 ad-hoc 簽署並通過 `codesign --verify --deep --strict`，不是 Apple Developer ID 簽署或 notarization。
