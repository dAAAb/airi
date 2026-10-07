# 讓 AIRI 講台語：KaedeTai、Taibun 與 MMS 對照

這裡提供程式與固定來源清單，不含權重、Python runtime、上游音檔或錄音。
完整課堂路徑是「台語 LLM 回答 → 台語漢字 → Taibun POJ → 台語 TTS」。
Taibun 做文字轉寫，**不會把華語文法翻譯成台語**。

| 路徑 | 角色 | 本次限制 |
|---|---|---|
| KaedeTai GPT-SoVITS | 主台語 TTS | 社群模型，非聯發科。需要 S1/S2、Hubert、speaker encoder，合計約 1.404 GB 權重 |
| Taibun 1.1.8 | 台語漢字轉南部腔 POJ | 未收錄字、英語、數字會拒絕。詞彙與多音字仍需人工檢查 |
| Meta MMS `mms-tts-nan` | 36.3M／145 MB 對照組 | Min Nan，不保證臺灣腔。詞表不收 `ⁿ`，不能把它刪掉假裝成功 |

## 來源與授權

- [KaedeTai 程式](https://github.com/KaedeTai/GPT-SoVITS) 固定 commit `81959852f75c972a0a78364f8ea6b14133a11f4a`，LICENSE 為 RVC-Boss 的 MIT。保留上游 LICENSE。
- [KaedeTai 台語權重](https://huggingface.co/KaedeTai/gpt-sovits-tw) 的模型卡標示 MIT。下載的 S2 是 r4 e15，不能套用作者未發布新版的品質主張。
- [Hubert／speaker encoder 下載來源](https://huggingface.co/lj1995/GPT-SoVITS) 是另一組上游資產。頂層 MIT 不等於已釐清全部訓練資料、聲音及第三方權重的重分發條件。
- [MMS Min Nan](https://huggingface.co/facebook/mms-tts-nan) 採 **CC-BY-NC-4.0**，有非商業用途限制，不放入此 repo，也不納入預設產品組合。
- [Taibun](https://github.com/andreihar/taibun) 採 MIT。

`source-manifest.json` 固定每個遠端檔案的 revision、大小和 SHA-256。
本目錄的公開範圍是程式與下載說明。製作含權重的公開 App 前，必須另外完成各項重分發授權確認。

## 安裝（macOS Apple Silicon 已驗證的依賴版本）

需要 Python 3.11、Git、curl、FFmpeg。Linux 可作為移植實驗，但本次沒有完整驗證。
先進入此目錄：

```sh
cd course/ntu-vh2026/taigi-tts
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
python3.11 -m venv .venv-taibun
.venv-taibun/bin/python -m pip install -r requirements-taibun.txt
```

閱讀以上來源與授權後，下載主模型：

```sh
python3.11 prepare.py kaedetai --download
python3.11 prepare.py kaedetai
sh start-kaedetai.sh
```

`prepare.py` 取得固定版上游程式，保留 LICENSE，再下載並核對權重。
它直接從上游取得作者的合成示範 `demo_02_kin_a_jit_thinn_khi.mp3` 作為參考音。
本 repo 不重新打包那個音檔。這是合成音作為參考，沒有使用學生或教師的錄音。

上游公開入口缺少 `tts_long.py`，公開權重也不包含完整 inference config。
我們的 `kaedetai/direct-taigi.py` 直接接公開 neural modules，使用同 commit 的 config，嚴格檢查所有權重 keys。
這段接法屬課堂實驗，不能宣稱是作者完整生產環境。

## AIRI 設定

| 欄位 | 台語漢字 | 手寫 POJ／台羅 |
|---|---|---|
| Provider | OpenAI-compatible TTS | 同左 |
| Base URL | `http://127.0.0.1:8883/v1/` | 同左 |
| Model | `taigi-hanzi` | `kaedetai-taigi` |
| Voice | `taigi-demo-reference` | 同左 |
| Format／speed | WAV 或 MP3／1.0 | 同左 |

API key 可用非秘密 placeholder，本機 adapter 不向外驗證 key。
先看 `http://127.0.0.1:8883/health`，再測下面的新句。

```sh
curl -f http://127.0.0.1:8883/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"taigi-hanzi","voice":"taigi-demo-reference","input":"你敢有啥物特別想欲講的話？","response_format":"wav"}' \
  -o taigi-test.wav
```

每句最多 60 個漢字或 180 phonemes。殘留漢字、未知 G2P token、過長句子會回 422。
請在生成新句時保留舊檔案，用不同檔名記錄輸入、模型、速度及聽辨結果。

獨立 App 可調整 port 和 origin，監聽位址仍固定 loopback：

```sh
AIRI_TAIGI_PORT=18883 \
AIRI_TAIGI_ALLOWED_ORIGINS=http://127.0.0.1:17900 \
sh start-kaedetai.sh
```

支援 `AIRI_TAIGI_MODELS_DIR`、`AIRI_TAIGI_SOURCE_DIR`、`AIRI_TAIBUN_PYTHON`、`AIRI_TAIBUN_SCRIPT`。
這些路徑可指向 App 內的 runtime／資源，沒有固定使用者家目錄。
`AIRI_TAIGI_DEVICE` 預設 `cpu`。本次量測使用 CPU，**不是 MLX 加速**。

## MMS 對照組（選做）

```sh
python3.11 prepare.py mms --download
sh start-mms.sh
```

Base URL `http://127.0.0.1:8882/v1/`，voice `nan-poj`。
Model `mms-tts-nan` 接 POJ，`mms-tts-nan-taigi-hanzi` 接台語漢字。
可用 `AIRI_MMS_PORT` 和 `AIRI_MMS_ALLOWED_ORIGINS` 指定另外的本機 port／origin。
MMS tokenizer 的未知字元會拒絕，包含 `ⁿ`。不能套用 KaedeTai 的相同輸入就假設兩者都會讀。

## 本次實測與失敗訊號

M4 Max、Python 3.11、Torch 2.14.1、Transformers 4.50.3，CPU 4 threads。
KaedeTai 新台語問題約 0.84 秒生成 3.04 秒音訊。較長鼓勵句約 1.68 秒生成 6.76 秒 MP3。
MMS 的三句小測試約 0.17–0.22 秒生成 2.16–3.14 秒音訊。
這些是少量功能測試，不是跨硬體 benchmark。

SARC 新回覆「你敢有啥物特別想欲講的話？」經 TTS→Breeze ASR26 回讀「你有什麼特別想說的話嗎」，語意相符。
另一句「我是你的台語助理」被回讀為「我是你的大義祖先」，顯示仍有品質問題。
MMS「一起來學台語」亦曾回讀成不同內容。ASR 能幫忙找問題，不能取代台語母語者聽辨。

原實驗已通過 HTTP、音訊生成及 Chrome 語音對話。公開版調整了路徑與設定，再完成以下離線檢查。
這次沒有重新下載全部權重，也沒有假稱在全新電腦重裝成功。

```sh
python3.11 -m compileall -q kaedetai mms prepare.py transliterate.py loopback-config.py
python3.11 test-source-contracts.py
```
