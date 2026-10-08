# 模型與執行環境的重新散布記錄

原有模型查核日期：2026-10-07；MotionGPT 追加查核：2026-10-08。這份記錄區分「公開程式」、「使用者從原作者下載」與「我們把權重／執行檔放入 GitHub Release」。以下依作者公開授權判讀，不把整個 bundle 統稱為 AIRI 的 MIT 授權。

## 模型權重

| 安裝 ID | 已查官方授權 | 發布權重時要做什麼 |
|---|---|---|
| `sarc-taigi` | [SARC 模型卡](https://huggingface.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF)為 Gemma；基底是 Gemma 3 | 遵守 [Gemma 條款 §3](https://ai.google.dev/gemma/terms)：附完整條款、指定 NOTICE、保留來源、標示修改；將禁止用途限制納入下游有效協議並告知接收者。不能改標 Apache 或 MIT。 |
| `gemma4` | [Google Gemma 4 模型卡](https://huggingface.co/google/gemma-4-12B-it)及[官方授權](https://ai.google.dev/gemma/apache_2)為 Apache 2.0 | 附 Apache 2.0、保留版權與適用 NOTICE、標示修改。已安裝的 `gemma4:12b-it-qat` 在 Ollama `/api/show` 回傳的 license 也是 Apache 2.0。這與 Gemma 3 不同。 |
| `qwen` | [Qwen 3.5 0.8B 官方模型卡](https://huggingface.co/Qwen/Qwen3.5-0.8B)及該 repo LICENSE 為 Apache 2.0 | 保留阿里巴巴 Qwen 來源、Apache 授權與 Ollama 量化 payload 的 notices。Lite 模型包含視覺 projector 與 draft 權重，不能只計算主模型檔。 |
| `asr26` | [聯發科原版](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)與 [RayyTien MLX 轉換](https://huggingface.co/RayyTien/Breeze-ASR-26-mlx-4bit)均標 Apache 2.0 | 保留兩層來源、Apache 授權、量化／相容修正的修改記錄。MLX 轉換不會使原模型變成自己的 MIT 權重。 |
| `kokoro` | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)為 Apache 2.0 | 權重、使用的 voice 檔與來源聲明一起記錄。模型卡的資料／Creative Commons attribution 也保留；推論依賴另列。 |
| `kaedetai` | [KaedeTai 模型卡](https://huggingface.co/KaedeTai/gpt-sovits-tw)的 metadata 和 License & credits 都明列 MIT；不是未授權模型 | 隨 S1/S2 保留作者、模型卡與 MIT；同時列出 GPT-SoVITS、Hubert、speaker encoder、Taibun 與參考音訊來源。不能只附一張 AIRI LICENSE 就宣稱所有部分同授權。 |
| 選用 `motiongpt` | [MotionGPT Base 官方模型卡](https://huggingface.co/OpenMotionLab/MotionGPT-base/blob/a0a37a388137f15df8299c643a885a42b07772fe/README.md)只寫 `license: cc`，未明示 CC 變體；[程式授權副本](../motiongpt/vendor/LICENSE.MotionGPT)為 MIT | 本發行版不重新散布或代管權重。Thin／Full 由使用者選用後，直接向官方固定 revision 下載並驗證；Full 也不把它放進離線 payload。不能把程式的 MIT 延伸到權重。 |
| 可選 `mms-tts-nan` | [Meta 模型卡](https://huggingface.co/facebook/mms-tts-nan)為 CC BY-NC 4.0 | [條款](https://creativecommons.org/licenses/by-nc/4.0/)允許非商業分享／改作，須署名、連結授權、標示修改且不可加限制。不要放入宣稱可不限用途商用的預設包。 |

Gemma 3/SARC 的 NOTICE 必須包含條款指定的句子，並提供條款正文。安裝頁可展示來源與條款，讓使用者明確確認；點選框不會取代發行者本身的散布義務。

## MotionGPT 的程式與權重分界

本次固定 `OpenMotionLab/MotionGPT-base` revision `a0a37a388137f15df8299c643a885a42b07772fe`。它是用來重現課堂實驗的 Base checkpoint，不宣稱是最新模型。

- 程式固定 OpenMotionLab commit `001aaca8d0ee218fc17f8265d11ac124044fe42f`，保留原作者 MIT、copyright 與修改記錄。
- 權重模型卡只有 `cc`，不足以判斷署名、非商業、禁止改作或相同方式分享等具體條件。本發行版不把它解讀為已取得不限用途的再散布授權。
- Thin／Full 只隨附程式、固定下載清單與必要 runtime；MotionGPT 首次由使用者選用後從官方來源取得，約 1.336 GB。**Full 不含這組模型權重**。
- [固定檔案清單](../motiongpt/model-manifest.json)記錄 checkpoint、FLAN-T5 tokenizer 與 HumanML3D 統計檔的來源、revision、大小和 SHA-256。這些下載來源不會被改指向本專案的 Release。
- Lite 不附 MotionGPT runtime 或安裝選項。手動連接既有的本機 MotionGPT 服務，不會改變上游權重的使用條件。

使用者直接下載也不等於授權條件消失。若未來取得更明確的權重條款，需重新查核後才能改變本發行策略。Python、Torch、Transformers、tokenizer 與原作者程式各自的 notices 仍須保留。

## KaedeTai 的來源層次

- [KaedeTai/GPT-SoVITS LICENSE](https://github.com/KaedeTai/GPT-SoVITS/blob/main/LICENSE)為 MIT，保留 RVC-Boss copyright。實測程式固定 commit `81959852f75c972a0a78364f8ea6b14133a11f4a`。
- [KaedeTai/gpt-sovits-tw](https://huggingface.co/KaedeTai/gpt-sovits-tw)固定 revision `fa251907be54b63277377a96a23377fd7f00e323`，S1/S2 權重明列 MIT。
- 實際下載的 Hubert／ERes2Net 檔案來自 [lj1995/GPT-SoVITS](https://huggingface.co/lj1995/GPT-SoVITS)，該權重集合標 MIT。[TencentGameMate/chinese-hubert-base](https://huggingface.co/TencentGameMate/chinese-hubert-base)原來源也標 MIT；speaker encoder 程式來源 [3D-Speaker](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE)是 Apache 2.0。發布時保存下載 revision、每檔雜湊與這些分項聲明，不用頂層 MIT 抹去上游署名。
- 合成參考音訊來自作者 repo 的 `tw_samples/demo_02_kin_a_jit_thinn_khi.mp3`。原 repo 以 MIT 公開且沒有另外標此檔授權；發布時保留其完整來源與「作者合成展示」標示。這不是對任何真人聲音／人格權的概括授權，不能以此鼓勵未經同意的聲音複製。
- [Taibun](https://github.com/andreihar/taibun)程式為 MIT，字典資料另為 CC BY-SA 4.0。分發或修改字典需保留來源與相同條款；不要將字典重新標成 MIT。

ERes2Net 權重也已直接核對[原作者 ModelScope 模型卡](https://modelscope.cn/models/iic/speech_eres2netv2w24s4ep4_sv_zh-cn_16k-common)：同名 `w24s4ep4` 版本的 README metadata 明列 Apache License 2.0。原文已保存在 release 的 `eres2net-model-card.md`。

## 執行檔與依賴

[Ollama 引擎](https://github.com/ollama/ollama/blob/main/LICENSE)為 MIT，散布需附版權與授權全文。引擎可散布不等於其中每個模型都是 MIT；固定的 Ollama binary 仍須保留其附帶第三方 notices。

本次開發機的 FFmpeg 4.4.4 啟用 `--enable-gpl`，`ffmpeg -L` 明示 GPL v2 或更新版本。[FFmpeg 官方說明](https://ffmpeg.org/legal.html)說明授權取決於實際組態；**不能把這個 binary 當成 LGPL 或 MIT 直接複製而不附對應條件**。發布它與其動態函式庫時，需提供適用授權、對應來源、修改和建置資料，採取 GPL 容許的來源提供方式。若改用另一個 minimal build，重新查核那個實際 build。

Kokoro 環境中的 [eSpeak NG](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING)是 GPL v3 或更新版本，連同程式／資料打包時另履行相應來源與授權義務。[Misaki](https://github.com/hexgrad/misaki/blob/main/LICENSE)本身採 Apache 2.0，不能據此推論它的所有 phonemizer 相依項也都採 Apache。Python、Torch、NumPy、librosa、FFmpeg codec libraries 等以實際 wheel／binary 的 notices 為準。

### 實際 Mac runtime 的追加查核

安裝包不複製開發機的 FFmpeg 4.4.4 CLI。實際 ASR 解碼使用 PyAV 19.0.1，語音輸出使用 SoundFile 0.13.0／libsndfile 1.2.2。

但 PyAV wheel 仍內含影音函式庫：實際 `av_version_info` 為 FFmpeg 9.0.2，`avutil_license` 回報 LGPL v3 或更新版本。[該 wheel 的固定建置來源](https://github.com/PyAV-Org/pyav-ffmpeg/tree/9.0.2-1)含一個修改：把 x264/x265 從 GPL feature list 移到 version-3 list。實際 x264/x265 標頭依然是 **GPL v2 或更新版本**，因此不能稱整個 wheel 為「LGPL-only」。

`collect-license-notices.py` 已保存 FFmpeg、所有該 build 的 macOS codecs、patch、建置腳本及上游 SHA-256。eSpeak 1.52.0、phonemizer-fork 3.3.2、espeakng-loader 0.2.4 與 libsndfile 1.2.2 的對應來源另列。使用者能取得、修改、重建和替換這些元件，依各自授權行使權利。清單見[第三方 notices](THIRD-PARTY-NOTICES.md)。

Gemma 完整條款與禁止用途政策保存成純文字，供離線閱讀。原始網站 HTML 不放進本機 web origin。只有選用 SARC 的 Gemma 使用條款需要明確確認，Apache/MIT 部分呈現來源與授權，不多加同意門檻。

## Release 判斷

模型的公開條款並未一概禁止 GitHub Release：SARC、Gemma 4、Qwen、ASR、Kokoro、KaedeTai 可以依各自條件整理再散布。MMS 保留為標示非商用的可選實驗。MotionGPT 因權重 CC 變體未明示，保留官方直接下載途徑，不重包或代管。最終產物需有逐檔 payload manifest、來源版本、SHA-256、完整授權與 notices，並滿足實際 bundled GPL 元件的來源提供要求。

此記錄不是「只要使用者勾選就全部清關」的宣告。發行前逐項確認實際打包檔案；尚未收齊的 runtime notices／對應來源必須補齊，或改用清楚記錄來源的使用者下載途徑。不要在尚未做乾淨環境驗收時宣稱安裝包可在所有 Mac 一鍵運作。
