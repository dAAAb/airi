# 把 ASR-26 接到 AIRI 的麥克風

新增的 OpenAI-compatible HTTP 服務會常駐載入本機模型，把 AIRI 錄到的音訊片段轉成文字。它使用 MLX、保留已驗證的 tokenizer 修正，並用 lock 依序推論。

這是「收完一段再辨識」，不是 token 級串流。支援台語輸入，但通常輸出華語漢字。它不會合成台語聲音。

從 `course/ntu-vh2026/` 執行：

```bash
python3.12 -m venv asr26/.venv
asr26/.venv/bin/python -m pip install -r asr26/requirements-server.txt
python3 model-assets.py asr26 --download
asr26/.venv/bin/python asr26/verify-tokenizer.py
asr26/.venv/bin/python asr26/test-server.py
sh asr26/start-server.sh
```

已有模型目錄時，以 `BREEZE_ASR26_MODEL_DIR=/path/to/model` 指定。PyAV wheel 隨附解碼函式庫，不需另外安裝 FFmpeg 指令。服務只監聽 `127.0.0.1:8001`，不影響原本 `8000` STT。

AIRI 的 OpenAI-compatible Transcription provider 設定：

| 欄位 | 值 |
| --- | --- |
| Base URL | `http://127.0.0.1:8001/v1/` |
| Model | `breeze-asr-26-mlx` |
| API key | 不需要。若欄位必填，可用非秘密字串 `local`。 |
| Language | `zh`，台語輸入也使用此設定。 |

再到聽覺／語音辨識模組選用這個 provider，確認麥克風權限及輸入裝置。Base URL 不能填舊的 `8000`，也不要填網站首頁。

本機 HTTP 測試：

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/v1/models
curl http://127.0.0.1:8001/v1/audio/transcriptions \
  -F 'model=breeze-asr-26-mlx' \
  -F 'language=zh' \
  -F 'file=@/path/to/your-recording.wav'
```

支援 `json`、`text`、`verbose_json` 回應，以及 PyAV 可讀取的 WAV、WebM、MP3、M4A。每段音訊最多 25 MiB、120 秒。上傳暫存檔會在成功或失敗後清除。解碼失敗回 422，超限回 413。

CORS 僅允許課程網頁 `http://127.0.0.1:5174`、`http://localhost:5174`，以及 AIRI Local App 的 `http://127.0.0.1:17900`。外站 Origin 的 POST 會被拒絕。測試音訊不會上傳雲端。

服務回應包含 `X-Inference-Seconds`、`X-Audio-Seconds`、`X-ASR-Model`，方便比對單次辨識耗時。這不包含 LLM、TTS 或整體對話延遲。
