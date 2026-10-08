# MotionGPT MLX：原始骨架視覺檢查

日期：2026-10-08。本次只檢查已儲存的 MLX 輸出與骨架關鍵格，沒有操作原生 App，也沒有驗收 VRM 重定向。

## 輸入與繪圖

- [雙臂伸展原始輸出](backends/stretch-mlx-2.json)
- [雙臂拳擊原始輸出](backends/boxing-mlx-2.json)

兩組檔案標示 `backend: mlx-metal`、`precision: float32`、seed 42。
骨架採 HumanML3D 的 22 關節，+Y 向上、初始前方 +Z、角色初始左側 +X。
正面圖從 +Z 觀看，橘色右肢位於畫面左側。側面圖從角色左側 +X 觀看，前方 +Z 位於畫面右側。

繪圖沿用 CPU 檢查的投影程式，不鏡像、不重新定向、不置中 root，也不修改任何原始座標。
新產生兩張 PNG，沒有新增 GIF。輸入 SHA256、輸出 SHA256、選取 frame 與數值指標保留於 [mlx-keyframe-provenance.json](mlx-keyframe-provenance.json)。
重現入口為 [render-mlx-keyframes.py](render-mlx-keyframes.py)，共用 [render-novel-keyframes.py](render-novel-keyframes.py) 與 [render-skeleton-previews.py](render-skeleton-previews.py)。

## 觀察

| 動作 | 結果 |
| --- | --- |
| 雙臂向頭頂伸展 | [正面／側面關鍵格](stretch-mlx-2-keyframes.png)。92 格、4.6 秒。雙腕同時高於頭部 57 格，最高約 2.12／2.11 m，頭部約 1.54–1.57 m。兩臂從低位上抬、伸展，再放下，符合本次提示。 |
| 雙臂拳擊組合 | [正面／側面關鍵格](boxing-mlx-2-keyframes.png)。192 格、9.6 秒。右臂與左臂分別出現向前伸出，另一臂保留在身體附近，之後收回。配合步伐，外觀符合拳擊類動作。 |

拳擊的側面圖第 23 格可見右臂向初始前方 +Z 伸出，第 135 格可見左臂伸出。
這些方向與來源中的關節名稱一致，圖像沒有把角色左右交換。
肩到腕距離的左／右範圍約為 0.19–0.57／0.18–0.47 m，支持兩臂各有伸出與收回。

伸展的 root 水平範圍約 3 cm，站位相對穩定。
拳擊的 root X／Z 範圍約 0.67／0.71 m，最後約在起點後方 0.53 m，原始輸出不是原地站姿循環。

## 不足與驗證界線

- 伸展與拳擊的最低關節 Y 分別為 −0.003135 m 與 −0.005338 m。存在約 3–5 mm 低於零平面的座標，不能宣稱有嚴格地面接觸約束。
- 22 關節沒有手指、碰撞與受力資料。拳擊外觀相符，不代表握拳、命中或專業技術正確。
- 本次檢視的是選取關鍵格及全序列數值，沒有據此宣稱所有 frame 的平滑度、平衡或關節角度都經過人工逐格確認。
- 原生 VRM 還需驗證重定向、左右前後、原地播放、腳部滑動與結束姿態。
- 兩份來源都標示 `truncated: false`。相同 seed 不保證 CPU／MLX 隨機取樣相同；拳擊片長也與先前 CPU 樣本不同。

來源記錄的生成時間為伸展 0.0980 秒、拳擊 0.1814 秒。這是既有推論結果內的時間，本次繪圖沒有重新執行模型或重新量測性能。
數值 parity 是另一項測試，不能代替動作語意或 VRM 播放驗收。

兩張新 PNG 合計 248,535 bytes。連同先前預覽，全部圖像與 GIF 合計 8,428,654 bytes，低於 10 MB。
