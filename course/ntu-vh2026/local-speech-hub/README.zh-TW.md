# 本機雙語音入口

讓兩張 AIRI 角色卡共用一個 provider URL，各自選擇中文或台語的 model／voice。

| AIRI 設定 | 值 |
| --- | --- |
| Provider | OpenAI Compatible Audio Speech |
| Base URL | `http://127.0.0.1:8884/v1/` |
| 中文 model／voice | `kokoro`／`zf_xiaobei` |
| 台語 model／voice | `taigi-hanzi`／`taigi-demo-reference` |

此入口只轉送到既有本機服務：Kokoro 在 8880，KaedeTai 在 8883。台語路徑先將台語漢字轉寫為 POJ。它不會把任意華語文字自動翻譯成自然台語，仍需由對話模型生成適合的台語內容。

AIRI 的 compatible provider 沒有通用 voice catalog。角色卡需直接填入完整 model／voice ID。`/v1/audio/voices` 及 `/v1/voices` 可供人工或 API 查詢，不代表原生 UI 會自動讀取。

## 啟動

先啟動兩個 TTS 後端，再於專案工作目錄執行：

```sh
cd course/ntu-vh2026/local-speech-hub
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
sh start.sh
```

使用資料夾內獨立 `.venv` 的 FastAPI、Uvicorn、httpx。只監聽 `127.0.0.1:8884`。這個入口不含模型權重，也不會自動安裝兩個 TTS 後端。

`GET /health` 回傳 `status: "ok"` 和兩個 model ID。這僅確認入口存活，不代表後端 TTS 已就緒。`GET /v1/models` 列出兩個 model。

## API 與限制

`POST /v1/audio/speech` 接收 JSON：

```json
{
  "model": "taigi-hanzi",
  "voice": "taigi-demo-reference",
  "input": "我欲用箸食魚。",
  "response_format": "wav",
  "speed": 1.0
}
```

- model／voice 只接受上表固定配對；無任意 URL 或自訂目標。
- body 上限 4096 bytes，包含 chunked 傳送。
- 總請求時限 60 秒，不跟隨 redirect，不使用環境 proxy。
- CORS 只允許 `http://127.0.0.1:5174` 與 `http://localhost:5174`。
- Host 只允許 `127.0.0.1`／`localhost`；無 Origin 的本機命令列呼叫可用。
- 後端錯誤的 status、body、Content-Type 原樣回傳。連線失敗回 502，逾時回 504。
- 不會因台語失敗改唸中文，也不會反向 fallback。
- 不記錄使用者輸入、不保存生成音訊、停用 access log。回應帶 `Cache-Control: no-store`。
- 僅記錄完成時間、固定 route／model／voice、HTTP status、耗時與回傳 bytes，供課堂確認呼叫結果。沒有 IP、headers 或回應內容。

這是回傳完整音訊的 HTTP 轉接，沒有把後端改造成串流語音服務。

## 驗證

```sh
.venv/bin/python test-hub.py
```

11 項合約測試通過，涵蓋固定路由、voice 保留、錯誤傳遞、大小限制、CORS／Host、timeout、連線失敗、模型清單及不含輸入的完成紀錄。

2026-10-07 另以兩個真實後端測試，每段只測一次，不能當穩定延遲保證：

| 路徑 | HTTP | 音訊 | 端到端耗時 |
| --- | --- | --- | --- |
| Kokoro 中文 | 200 | 24 kHz mono WAV，2.717 秒 | 0.271 秒 |
| KaedeTai 台語 | 200 | 32 kHz mono WAV，1.120 秒 | 0.368 秒 |

不支援的台語音訊格式得到與直連 8883 完全相同的 422 回應。測試僅保存 [validation.json](validation.json) 中的數字與固定錯誤訊息，沒有留下音訊。HTTP 成功確認路由與格式，並非母語者的發音評分。

Kokoro 的串流 WAV 檔頭使用暫定長度；本次音訊長度依實際 PCM bytes 計算，避免把檔頭占位值誤當播放時長。

## Mac App 的獨立服務

打包器設定 `AIRI_DESKTOP_MODE=1` 時，兩條固定路由改用 `127.0.0.1:18880` 與 `127.0.0.1:18883`。網頁來源加入 `http://127.0.0.1:17900`，hub 自身由 App 啟動於 18884。這個開關不接受任意 URL，也不改動原本 8880／8883 的服務。
