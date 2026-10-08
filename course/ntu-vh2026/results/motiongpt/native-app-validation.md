# AIRI Local 0.3.0 原生驗證紀錄

日期：2026-10-08，Apple Silicon M4 Max／128 GB。

## 已在原生 App 看見的結果

先前同版候選包（CPU backend）完成：

- 「機體模組 → 動作」繁中標籤、啟用／自動生成開關、本機連線、提示、預覽／重播／停止可操作。
- 手動生成雙臂過頭伸展，VRM 確實抬高雙臂並回復；拳擊生成有手臂前伸、收回、步伐及轉身。
- 重播及停止可用；這不代表後端已開始的計算會被立即殺掉。
- 桌寵齒輪能穩定開啟設定、進入子頁、返回主頁恢復桌寵，見[齒輪紀錄](../desktop-pet-gear-fix.md)。

## 後續找到並修正的整合錯誤

1. 前端保存 native fetch 後以 class method 呼叫，造成 Illegal invocation；已改 wrapper，並有 receiver 回歸測試。
2. i18n 動作標籤曾放到錯誤 YAML 節點；已修正並重建 compiled locale。
3. 對話中模型雖有 ACT，但 core-agent 的第一層解析器丟掉 motionPrompt，導致自動生成未觸發；已修正欄位保留。真實 Gemma API → parser → MotionGPT 已測到伸展 48 幀、拳擊 164 幀；閒聊不生成，見[結果](conversational-gemma.json)。

## 新 MLX 包的驗證邊界

最新候選包包含上述修正、CPU／MPS／MLX runtime 選單、安裝器恢復模型勾選。Web build、backend source/bundle hash、ad-hoc code-sign verify 通過；原始碼與可攜式 runtime 測試通過。

- 三後端共 30 段真實生成有效；MLX 同 token 數值比對通過。
- 正式 standalone runtime 的 runtime API 切換與生成（CPU、MPS、MLX、auto）通過，見[API 原始結果](portable-runtime-backends.json)。
- MLX 原始骨架伸展／拳擊方向與外觀檢查通過，限制見[骨架 QA](mlx-skeleton-preview-audit.md)。
- **最新版 App 的 MLX 選單操作與修正後自動對話動作，尚未完成原生目視驗證。** 準備重新啟動新版時 Mac 鎖定，Computer Use 無法繼續；待操作者解鎖後驗證。先前 CPU 手動播放成功不取代這兩項驗證。

這是 ad-hoc 簽署的本機測試包，沒有 Developer ID 公證；MotionGPT 模型與私人轉換快取不包含在公開 App／Git 中。
