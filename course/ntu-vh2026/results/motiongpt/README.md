# MotionGPT 實測原始輸出

後續：[原生 MLX 與對話動作驗證](native-app-validation.md) · [0.4.0 Decisions 選配與安裝包驗證](decisions-validation.md)

2026-10-08，Apple M4 Max／128 GB，Python 3.12.3、PyTorch 2.8.0、Transformers 4.44.2。

這些 JSON 是本機神經模型產生的 22 關節序列；未用手寫動畫取代，也未為了讓圖好看而修改座標。`prompt`、`seed`、模型 ID、實際 device、動作 token 數、20 fps 格數及生成耗時均保留。量測腳本與固定來源位於 `../../motiongpt/`。

| 檔案 | token 數 | 格數／片長 | 生成時間 |
| --- | ---: | ---: | ---: |
| right-wave-cpu.json | 17 | 68／3.4 秒 | 0.2177 秒 |
| right-wave-mps.json | 17 | 68／3.4 秒 | 0.9743 秒 |
| bow-cpu.json | 21 | 84／4.2 秒 | 0.2508 秒 |
| bow-mps.json | 26 | 104／5.2 秒 | 1.8002 秒 |
| dance-cpu.json | 49 | 196／9.8 秒 | 0.4780 秒 |
| dance-mps.json | 48 | 192／9.6 秒 | 1.6339 秒 |
| novel/stretch-cpu.json | 23 | 92／4.6 秒 | 0.3034 秒 |
| novel/boxing-cpu.json | 39 | 156／7.8 秒 | 0.4185 秒 |

上述八段全部通過有限數值、22×3 形狀、最大座標及最大196格檢查，沒有裁切。模型載入約 3 秒，另外計算；最早一次 MPS 冷啟動揮手生成約 6.98 秒，表格是後續執行的數值。CPU／MPS 使用相同 seed 42，但不保證生成完全相同的 token，所以不同長度不能當成等量運算比較。

這裡的數值通過不代表語意品質已通過人工評分。尤其「boxing」可能不符合使用者期待的特定拳法；應查看播放結果再評估。右手、左手用角色的解剖方向定義，不用觀眾的螢幕左右。座標為 +Y 向上、初始面向 +Z、+X 為角色自己的左側；`joint_names` 列出標準 HumanML3D 22 骨架次序。

伸展與拳擊用來驗證可以生成超出原本短動作清單的新序列；它們不是提前加入新的程序動畫。

原始固定來源：

- [MotionGPT-base 權重](https://huggingface.co/OpenMotionLab/MotionGPT-base/tree/a0a37a388137f15df8299c643a885a42b07772fe)
- [MotionGPT 程式](https://github.com/OpenMotionLab/MotionGPT/tree/001aaca8d0ee218fc17f8265d11ac124044fe42f)

權重八個檔案共 1,335,831,259 bytes。原始 checkpoint 的 SHA-256 為 `0d8a9e1a0c3bd15ed2d2160a22abe3edef299920eb9565a7e9decf1da4c8e79c`；下載權重未放進本目錄或 repo。輸出只包含合成骨架座標，不含學生、使用者影像或語音。
