# CPU／MPS／MLX：同提示、同 seed，保留實際 token 數

2026-10-08，Apple M4 Max／128 GB，MotionGPT-base 固定官方權重、float32、seed42。各後端依序執行五個提示，每個提示兩次；檔名最後的 `-1`／`-2` 是順序，不是模型版本。所有 30 份 JSON 均為真正模型輸出，沒有用程序動畫替代。不同框架的 RNG 不同，因此相同 seed 不等於相同 token。

| 提示 | CPU 第2次／tokens | MPS 第2次／tokens | MLX 第2次／tokens |
| --- | ---: | ---: | ---: |
| right-wave | 0.2706秒／17 | 0.5871秒／17 | 0.0759秒／16 |
| bow | 0.3033秒／21 | 0.8675秒／26 | 0.0955秒／21 |
| dance | 0.6086秒／49 | 1.5620秒／48 | 0.1821秒／48 |
| stretch | 0.3252秒／23 | 0.7473秒／22 | 0.0980秒／23 |
| boxing | 0.4808秒／39 | 1.5784秒／49 | 0.1814秒／48 |

一次 VQ 動作 token 解碼成4格，20fps；例如MLX伸展23tokens＝92格＝4.6秒。上表不含模型載入；已有 safetensors 快取時 MLX 載入約1秒。MLX首段尚未暖機的揮手耗時0.8957秒，第二次才是0.0759秒。因此不能把所有體驗都描述為「0.1秒完成」。不同長度也不能視為相同工作量的嚴格效能比賽。

MLX 使用原生 `mlx.core` 執行全部神經層及關節還原，實際 device 為 `Device(gpu,0)`。測試首先在沒有安裝 PyTorch 的既有MLX runtime 成功執行，再以正式MotionGPT可攜式runtime完成相同數值比對；PyTorch只需在第一次轉換 checkpoint 時使用。權重留在使用者自己的模型快取，未加入這個目錄。

完全相同的輸入、16步decoder token以及VQ token比對，見 [mlx-parity-portable.json](../mlx-parity-portable.json)。Encoder最大誤差1.8e−7、logits6.1e−5、VQ特徵1.14e−5、關節4.8e−7公尺，16步argmax全相同。這項比對驗證實作忠實度，並不是語意動作品質評分。

另外對 MLX 隨機生成的伸展、拳擊做原始骨架視覺檢查：[MLX骨架QA](../mlx-skeleton-preview-audit.md)。這是模型座標及投影图的檢查；原生App與VRM播放結果需另外驗收。

重現腳本為 `../../../motiongpt/benchmark_backends.py`。完整 prompt、token數、原始／回傳格數、是否裁切與時間在每份JSON及三份benchmark報告中，未挑掉任何失敗結果；本次30段均通過座標有效性與上限檢查，均未裁切。
