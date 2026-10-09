# v0.4.1 原生 App 驗證

日期：2026-10-09。機器：Apple Silicon M4 Max、128 GB 統一記憶體。
使用 AIRI Local Full、MotionGPT-base 原生 MLX、既有 VRM 角色及本機 `gemma4:12b-it-qat`。
這次只測動作頁與播放；沒有重新宣稱完成語音、圖片或付費 Decisions API 測試。

## 原生畫面

1. 從桌寵按「開啟設定」，停留在一般設定視窗，沒有跳回桌寵。
2. 「機體模組 → 動作」測試服務，顯示 `OpenMotionLab/MotionGPT-base · mlx · 20 fps`，載入時間約 0.97 秒。
3. 輸入 `Jump high!`，按「生成並預覽」。畫面顯示實際英文仍是 `Jump high!`，不經 LLM 翻譯。
4. 以固定預覽框觀察整個片段：雙腳離開原先站立高度，接著下降；播放結束回到待機高度。頭與腳均在預覽範圍內。鏡頭未跟著骨盆上移。
5. 輸入 `跳高！`，按一次「生成並預覽」。介面先顯示本機轉換中，之後顯示：

   - 原始输入：`跳高！`
   - 實際英文：`A person jumps straight up into the air.`
   - 轉換模型：`gemma4:12b-it-qat`
   - 狀態：`已收到動作`

6. 重播這個中文產生的片段，同樣可見升空、下降與待機高度還原。

原生目視結果和骨架數值是不同證據；此處沒有用畫面像素估算物理公尺。
生成的手臂姿勢與跳高幅度仍由 MotionGPT 決定。不同英文、seed 與角色比例不保證同樣動作。
首次驗收後只更新英／繁中文限制說明，修正「移除全部根位移」的舊文字，再重新打包；動作與翻譯程式不變。

## 程式與資料驗證

| 範圍 | 結果 |
| --- | --- |
| generated motion + semantic motion | 38 tests 通過 |
| 本機中文轉換 helper/store + 既有 motion store | 26 tests 通過 |
| stage-ui-three、stage-ui、stage-pages、stage-web 型別檢查 | 通過 |
| 修改程式、測試、locale 的 ESLint | 通過 |
| i18n 與 stage-web production build | 通過 |
| `git diff --check` | 通過 |
| 四個真實 VRM，逐格方向、XZ、Y、停止還原 | 通過；見 [retarget-jump-real-vrms.json](retarget-jump-real-vrms.json) |
| 真正本機 Gemma 轉換三個中文測例 | 通過；見 [gemma-translation-smoke.json](gemma-translation-smoke.json) |

全 monorepo 檢查仍有環境限制，不能宣稱整庫全綠：

- 根目錄 `pnpm typecheck` 的 Turbo 子程序重新嘗試建立全域 pnpm 工具目錄而遇到 `EPERM`，尚未完成全專案檢查。
- 根目錄 `pnpm lint` 因既有 `docs/uno.config.ts` 缺少 `@radix-ui/colors` 結束。

這次未修改全域套件或補裝無關文件依賴。相關 workspace 的型別與修改檔案的 lint 已獨立完成。

## 範圍限制

垂直位移以動作首幀為基準、按腿長比例縮放並限制幅度。若模型首幀已在蹲姿或空中，不會自動猜測真實地板。
水平 XZ 仍原地播放，沒有腳部 IK、碰撞或接觸物理。轉換保留否定字句不代表動作生成器一定遵守否定，應逐層檢查。
中文轉換只允許目前已選的 loopback 本機 provider，不會自動改用雲端或下載模型；英文可直接測試。
