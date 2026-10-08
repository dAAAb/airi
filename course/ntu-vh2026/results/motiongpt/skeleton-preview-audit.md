# MotionGPT 原始骨架輸出檢查

日期：2026-10-08。這是模型輸出的數值與視覺檢查，不代表 AIRI 原生介面或 VRM 重定向已驗收。

## 資料與方法

預覽直接使用 `right-wave-cpu.json`、`bow-cpu.json` 與 `dance-cpu.json` 中的 22 關節座標。
三組都是 `OpenMotionLab/MotionGPT-base`、seed 42 的實際 CPU 輸出。

- 模型 revision：`a0a37a388137f15df8299c643a885a42b07772fe`
- 上游程式 revision：`001aaca8d0ee218fc17f8265d11ac124044fe42f`
- 正面攝影機位於 +Z，畫面向右為 +X，也就是初始姿態的角色左側。
- 左側攝影機位於 +X，畫面向右為 +Z，也就是初始前方。
- 橘色是解剖學右肢，青色是左肢，灰色是軀幹。
- 沒有鏡像、旋轉模型、置中 root、插補、濾波或重新採樣。
- 地面、世界座標與每段動畫的視野固定。轉身時不跟著旋轉攝影機。

GIF 每格對應一個原始 frame，維持 20 fps，播完才循環。
輸入與輸出的 SHA256、大小及數值指標都記錄在 [skeleton-preview-provenance.json](skeleton-preview-provenance.json)。
生成程式為 [render-skeleton-previews.py](render-skeleton-previews.py)，使用現有 Matplotlib、NumPy 與 Pillow。

## 結果

| 指令 | 動畫 | 觀察 |
| --- | --- | --- |
| 舉右手打招呼 | [正面／側面 GIF](right-wave-cpu-skeleton.gif) · [關鍵格](right-wave-cpu-keyframes.png) | 68 格、3.4 秒。右腕由約 0.88 m 升至 1.83 m，左腕維持約 0.86–0.90 m。高舉期間右腕左右往返，最後放下。左右手符合指令。 |
| 慢慢前彎鞠躬，再站直 | [正面／側面 GIF](bow-cpu-skeleton.gif) · [關鍵格](bow-cpu-keyframes.png) | 84 格、4.2 秒。頸部相對骨盆的前傾角由 −4.39° 到 42.90°，最後回到 −4.28°。但左腳踝升至約 0.238 m，出現未要求的抬左腳。 |
| 開心跳舞、左右擺動並移動雙臂 | [正面／側面 GIF](dance-cpu-skeleton.gif) · [關鍵格](dance-cpu-keyframes.png) | 196 格、9.8 秒。可見雙臂活動、步伐與轉身。Root 結束位置相對起點約移動 −0.24 m X、−0.42 m Z，並非固定站位循環。 |

上述角度是固定世界 YZ 平面內的頸部到骨盆方向，並非完整的生物力學關節角度。
座標單位沿用模型設定，沒有另做真實人物身高或動作捕捉校準。

CPU 生成時間依來源紀錄分別為 0.2177、0.2508、0.4780 秒。這些是已載入模型的生成時間，不含冷啟動、下載或繪圖。

## 驗證與限制

- 匯出的 GIF 格數分別為 68、84、196，與原始檔一致。
- 每格時間均為 50 ms，總播放時間分別為 3400、4200、9800 ms。
- 三組來源皆標示 `truncated: false`。
- 六個預覽檔案總共 7,940,504 bytes，低於 10 MB。
- 原始 JSON 沒有修改。預覽不混入現有的程序式揮手或跳舞動作。

揮手左右正確，不代表任意指令都能精準遵從。鞠躬的額外抬腳就是具體反例。
舞蹈包含位移，轉到桌寵時需要另驗證 root 位移與播放結束姿態。
這三個案例、單一 seed 無法代表模型整體品質，也不能證明 VRM 播放方向或關節對應正確。

## 新提示：雙臂伸展與拳擊

另外直接檢查 `novel/stretch-cpu.json` 與 `novel/boxing-cpu.json`，只新增兩張關鍵格 PNG。
原始輸入與輸出 SHA256、選取的 frame 索引、數值指標記錄於 [novel-keyframe-provenance.json](novel-keyframe-provenance.json)。
兩個原始 JSON 都沒有修改，沒有新增 GIF。

| 新提示 | 觀察 |
| --- | --- |
| 雙臂伸展到頭頂 | [正面／側面關鍵格](stretch-cpu-keyframes.png)。92 格、4.6 秒。雙腕同時高於頭部共 57 格，約 2.85 秒。左／右腕最高約 2.12／2.11 m，頭部高度約 1.54–1.57 m。雙臂高舉後放下，符合本次描述。 |
| 雙臂短拳擊組合 | [正面／側面關鍵格](boxing-cpu-keyframes.png)。156 格、7.8 秒。兩臂有交替伸出與收回，配合步伐及身體轉向，外觀符合拳擊類動作。左／右肩到腕距離分別約 0.18–0.55／0.18–0.47 m。 |

拳擊原始 root 的 X 範圍約 1.30 m，不是固定站位的手臂動作。
22 關節沒有手指、碰撞或力，因此無法確認握拳、命中或專業拳擊技術。
這些觀察是原始骨架的提示符合度，沒有進行真人評分或 VRM 介面驗收。

這兩張圖另增 239,615 bytes。全部八個圖像／動畫合計 8,180,119 bytes，仍低於 10 MB。
