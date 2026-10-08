# 桌寵齒輪：設定視窗立即退回桌寵的修正

日期：2026-10-08。原始碼回歸測試已通過，後續已在原生 AIRI Local v0.3 App 驗證齒輪、設定子頁與返回主頁的切換。

## 問題與原因

使用者在桌寵模式按齒輪後，一般視窗短暫出現，隨即退回桌寵。

這次重現的事件順序如下：

1. `openSettings()` 暫時切換一般視窗，保留使用者偏好的桌寵模式。
2. Vue Router 前往 `/settings` 前，先以 `replaceState` 更新目前的 `/` 歷史項目。
3. 原生端把這次同頁更新當成返回角色主頁，立即恢復桌寵。
4. `App.vue` 的桌寵狀態監聽器再推送 `/` 路由，形成回到主頁的循環。

Vue Router 的本機實作可在 `apps/stage-web/node_modules/vue-router/dist/vue-router.js` 的 `push()` 確認。它先寫入目前網址，再推入目標網址。

另一個競態來自非同步 `getState()`。較早讀取的桌寵狀態，能在較新的設定頁狀態之後回傳，覆蓋畫面狀態。

## 修正行為

- 原生端保存主框架目前路由，採用 Electron 導航事件提供的網址。
- 只有從其他頁面真正返回 `/` 時，才恢復偏好的桌寵模式。
- 同一主頁的歷史項目、查詢參數或 hash 更新，不再觸發恢復。
- 子框架導航不能切換主視窗模式。
- 前端移除「桌寵模式改變就推送主頁」的回饋路徑。
- 前端狀態讀取使用版本號，忽略落後於原生事件的非同步結果。

設定仍在同一個 `BrowserWindow` 與 `webContents` 內開啟。修正不重載對話或角色，也不更改使用者資料。

Electron 事件的 `url` 與 `isMainFrame` 契約見[官方 webContents 文件](https://www.electronjs.org/docs/latest/api/web-contents#event-did-navigate-in-page)。Vue Router 的導航等待規則見[官方導航失敗文件](https://router.vuejs.org/guide/advanced/navigation-failures.html)。

## 回歸驗證

原生測試載入實際 `main.cjs` 的 `DesktopWindowController`。只有 Electron 與檔案系統等外部邊界使用替身。測試沒有啟動 GUI、模型或服務，也沒有寫入真實使用者設定。

新增的三個原生回歸案例涵蓋：

1. 舊主頁 `replaceState` → 設定頁 → 設定子頁，全程維持一般視窗。返回角色主頁後恢復桌寵。
2. `getURL()` 仍是上一頁時，採用事件目標網址。子框架事件無效。
3. 同主頁 query/hash 不恢復桌寵。明確選擇一般視窗後，往返設定仍維持一般視窗。

把測試輸入換成修正前 `HEAD` 的 `main.cjs`，三個案例全部失敗。修正後全部通過。

| 檢查 | 指令與結果 |
| --- | --- |
| 原生單元測試 | Repo 根目錄：`NODE_PATH=apps/stage-web/node_modules node --test course/ntu-vh2026/desktop/test-*.cjs`。13/13 通過。 |
| 前端狀態測試 | `apps/stage-web`：`../../node_modules/.bin/vitest run src/composables/desktop-pet.test.ts --project unit`。6/6 通過，包含兩個非同步狀態競態。 |
| 變更檔案 lint | Repo 根目錄：`./node_modules/.bin/eslint course/ntu-vh2026/desktop/main.cjs course/ntu-vh2026/desktop/desktop-state.cjs course/ntu-vh2026/desktop/test-desktop-navigation.cjs apps/stage-web/src/App.vue apps/stage-web/src/composables/desktop-pet.ts apps/stage-web/src/composables/desktop-pet.test.ts`。通過。 |
| 差異空白檢查 | Repo 根目錄：`git diff --check`。通過。 |
| Stage-web 型別檢查 | `apps/stage-web`：`./node_modules/.bin/vue-tsc --noEmit`。通過。首次執行受同期 MotionGPT 宣告更新阻擋，相依套件建置完成後重跑成功。 |
| 全庫 lint | Repo 根目錄：`./node_modules/.bin/moeru-lint .`。因 `docs/uno.config.ts` 缺少 `@radix-ui/colors` 終止，exit 2。未改動該相依套件。 |

工作區的 `pnpm` 啟動器嘗試寫入受限的工具目錄，因此測試改用已安裝的本機執行檔。

## 原生 AIRI Local v0.3 驗證

主工作階段在實際原生 App 完成以下三項操作，觀察結果通過：

1. 桌寵按齒輪後，設定頁穩定留在一般視窗，沒有立即退回桌寵。
2. 進入設定子頁後，頁面與一般視窗模式維持穩定。
3. 返回角色主頁後，恢復桌寵模式。

這個原生驗證只涵蓋上述切換。沒有據此擴大宣稱長時間反覆操作、對話資料保存、麥克風連續收音或多螢幕行為已驗收。
「使用者明確選一般視窗後仍保持偏好」已有單元測試，尚未在此紀錄中完成原生操作驗證。
