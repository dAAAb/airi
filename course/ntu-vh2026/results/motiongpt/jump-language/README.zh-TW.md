# 中文提示與跳躍高度：分開追蹤兩種問題

2026-10-09，以本機 MotionGPT-base、原生 MLX／Metal、seed 42 實測。這些檔案是模型的真實輸出，不是手工動畫。沒有使用雲端 API、個人圖片或對話。

另見 [v0.4.1 原生 App 畫面與建置驗證](native-app-validation.md)，記錄英文與中文跳躍的實際播放結果。

## 中文在哪一步遺失？

用此版本隨附的 tokenizer，實際編碼後再解碼：

| 原始提示 | tokenizer 還原內容 |
| --- | --- |
| 跳高！ | `Generate motion: <unk>!</s>` |
| 跳起來然後雙腳落地。 | `Generate motion: <unk></s>` |
| Jump high! | `Generate motion: Jump high!</s>` |
| A person jumps high then lands on both feet. | `Generate motion: A person jumps high then lands on both feet.</s>` |

這兩句中文的動作內容在 tokenizer 階段就變成未知符號，不能期待後續模型還原原意。兩句英文沒有未知 token。完整 token 與編號保留於 [tokenizer-probe.json](tokenizer-probe.json)。

聊天路徑先讓本機語言模型把中文意圖寫成英文 `motionPrompt`，因此和直接送中文的手動頁有不同結果。修正方式是讓手動頁也先進行本機翻譯，顯示實際送給 MotionGPT 的英文。翻譯與模型動作品質仍須分開檢查，中文翻譯成功不保證動作正確。

新的手動翻譯函式實際經由 `translateMotionPrompt → providerOllama → streamFrom` 呼叫本機 `gemma4:12b-it-qat`（停用 thinking），結果如下。沒有讀取或修改使用者設定，沒有 API key 或雲端請求。

| 中文 | 真實英文輸出 | 單次耗時 |
| --- | --- | ---: |
| 跳高！ | A person jumps high into the air. | 2.259 秒 |
| 請用左手揮手打招呼 | A person waves with their left hand. | 0.676 秒 |
| 不要跳，請向前鞠躬一次。 | A person performs one forward bow without jumping. | 0.698 秒 |

這三句保留了動作、左手與否定條件。[原始翻譯紀錄](gemma-translation-smoke.json)包含模型與端點。它們不能證明所有中文或較小模型都能正確轉換，也不表示 MotionGPT 一定遵守英文中的否定條件。

## 模型有生成跳躍高度嗎？

有。兩句英文都得到上升後下降的 pelvis 高度。原始序列使用公尺、+Y 向上、每秒 20 格；下表尚未經 VRM 骨架映射。

| 提示 | 片長 | pelvis 初始／最高／最後高度 | 最高比初始增加 | 兩腳較低者的最高高度 |
| --- | ---: | --- | ---: | ---: |
| `Jump high!` | 56 格／2.8 秒 | 0.960338／1.335605／0.959228 m | 0.375267 m | 0.345893 m |
| `A person jumps high then lands on both feet.` | 172 格／8.6 秒 | 0.922759／1.308001／0.925891 m | 0.385242 m | 0.285330 m |

短句的 pelvis 在第 29 格最高。兩腳初始高度約 1.1／1.3 cm，最後約 1.3／1.3 cm，能用來追蹤「蹲低→離地→回原高度」是否在 VRM 映射時被遺失。舊播放器移除根節點全部位移，連垂直高度一起移除；只看關節旋轉便會錯過跳躍升空。修正應保留按角色尺度換算的相對 Y，並保留 XZ 原地播放。

[起始站姿檢查](standing-baseline.json)：短句前五格的 pelvis 約 0.9603～0.9616 m，左右腿的垂直伸長約為腿鏈長度的 98.7%，第 0 格接近站直，最低下蹲出現在第 19 格。因此此例以第 0 格作相對高度基準合理。其他生成片段若從蹲姿開始，這個基準就不等於標準站姿或真實地板，仍需另查。

完整句的右腳最高約 0.782 m，左腳約 0.285 m，動作存在明顯不對稱；部分腳部位置最低约 −1 cm。這代表長句不一定更好，也不能把輸出的地板位置當成已驗證的物理接觸。沒有腳部 IK、碰撞或落地安全保證。這份數值記錄不等於原生 App 的播放驗收。

- [短句原始序列](jump-short-mlx-seed42.json)
- [完整句原始序列](jump-landing-mlx-seed42.json)
- [高度指標、SHA-256 與生成時間](metrics.json)

生成耗時分別為 0.0881／0.1504 秒，使用已載入並暖機的 MLX 服務，不含模型載入、翻譯、VRM 播放或語音時間。這是兩個單次取樣，不是完整延遲評測。

## 修正後，四個真實 VRM 的骨架映射

用短句的同一段 56 格序列，載入四個真實 VRM 的節點、骨架對應與 three-vrm humanoid，逐格量測。此測試不載入材質或原生視窗。

| VRM | root Y 最低／最高相對位移 | 兩個 Foot 骨節較低者的最高相對高度 |
| --- | --- | ---: |
| AvatarSample A，VRM 0 | −0.2167／+0.3538 | +0.3742 |
| AvatarSample B，VRM 0 | −0.2042／+0.3333 | +0.3522 |
| 第四週角色，VRM 0 | −0.2053／+0.3350 | +0.3515 |
| 第四週角色，VRM 1 | −0.2053／+0.3350 | +0.3515 |

數字是 VRM 場景單位，基準為動畫開始前的靜止骨架。`Foot` 骨節位於腳踝，不是網格腳底，所以不能當成精準地面間隙。四個角色的 root XZ 在每格都維持不變；所有位置及旋轉有限；完整動作期間的肢段方向 cosine 最低約為 1，VRM 0／1 沒有因 Y 修正反轉左右或前後。停止後所有 normalized 位置與原始旋轉還原。

[完整逐格檢查摘要](retarget-jump-real-vrms.json)記錄每個模型雜湊、最大與最小高度及每項檢查。它修正了舊腳本只在停止後檢查根部位置的盲點；這仍是骨架數值驗證，原生視窗、相機構圖與實際網格要另外驗收。

## 重現

先啟動本機 MotionGPT 並選 MLX，再呼叫固定的 loopback 端點：

```sh
curl --fail --max-time 55 http://127.0.0.1:17905/v1/motions/generate \
  -H 'Content-Type: application/json' \
  --data '{"prompt":"Jump high!","seed":42}' > jump-short.json

curl --fail --max-time 55 http://127.0.0.1:17905/v1/motions/generate \
  -H 'Content-Type: application/json' \
  --data '{"prompt":"A person jumps high then lands on both feet.","seed":42}' > jump-landing.json
```

`joint_names` 指定每個關節，pelvis 為 0、left/right ankle 為 7／8、left/right foot 為 10／11。比較每格的 `joints[frame][joint][1]`，不能用手部高度代替身體離地高度。不同框架或後端即使 seed 相同也可能生成不同動作。
