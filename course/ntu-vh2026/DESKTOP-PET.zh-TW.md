# 桌寵與 AI 語意動作

這次把兩個能力接在一起：Mac 桌面上的透明角色，以及依對話情境選擇的 VRM 動作。

## 桌寵操作

在 AIRI 角色主畫面按「桌寵模式」，或用 macOS 選單列的「桌寵」。上方握把可拖曳角色。

- 圖釘切換置頂，聊天按鈕開啟文字與圖片輸入。
- 麥克風沿用原本的 STT → LLM → TTS，不另開第二條錄音。
- 「滑鼠穿透」讓下方 App 接收點擊，角色繼續顯示。
- 按 `⌘⌥P`、點 AIRI Dock 圖示，或選「恢復操作／找回角色」，可恢復互動。
- 「回到一般視窗」保留角色、模型、對話與背景設定。

一般視窗與桌寵使用同一個頁面，切換不重新載入。透明區域預設仍屬於視窗；只有手動開啟穿透才把點擊交給下方 App。這一版不是逐像素的滑鼠命中測試。

重新啟動保留模式及位置，但滑鼠穿透會關閉。拔除外接螢幕後，角色會回到可見的工作區。快捷鍵被其他 App 占用時，仍可使用 Dock 與選單。

## 「知道開心」與「知道怎麼動」是兩層

```text
對話／圖片 → LLM 理解情境 → ACT 情緒與動作標記
                              ↓
                     VRM 表情與骨架播放器
                              ↓
                     短動作 → 平滑回到待機

說話正文 ─────────────→ TTS → 嘴型
```

LLM 選擇動作名稱，播放器定義動作的姿勢、幅度、時間與回復方式。華語和台語共用動作控制，TTS 只接收說話文字。

本次採用有限的程序骨架動作，沒有增加另一個動作生成模型。`dance` 是預先編排的短律動，不是 LLM 即時生成任意舞蹈。不同 VRM 的比例、衣服及骨架設定仍會影響外觀。

目前的兩種舞動是 `dance`（4.8 秒節奏擺動）與 `sway`（4 秒緩慢左右擺動）。`celebrate` 是 3 秒舉手慶祝，不是另一種舞蹈模型。播放器另有點頭、搖頭、揮手及鞠躬，`idle`／`stop` 會取消動作。動作只改有限幅度的骨架旋轉，不跳躍或移動角色根節點。詳見[播放器原始碼](../../packages/stage-ui-three/src/composables/vrm/semantic-motion.ts)。

`wave` 固定使用角色自己的右手。目前沒有左手揮手動作；即使對話要求「揮左手」，模型選到 `wave` 後仍會播放右手動作，不能把它當成已支援左右手指令。

因此，「請慢慢左右搖擺」是讓 LLM 選出提示中已有的 `sway`，並非讓模型輸出新的關節軌跡。這一版沒有音樂節拍分析、任意舞種生成或神經網路 text-to-motion 推論。

桌寵沿用 AIRI 的 ACT 串流機制，無須啟用 `builtIn_emitSparkCommand`。Spark 是連接模組／代理的工具，與骨架動畫不同。

## 左右、前後：會動不代表動對了

骨架的 `rightHand`、`rightUpperArm` 指**角色自己的右手、右上臂**。角色正面面對觀眾、手臂沒有交叉時，它的右手會出現在畫面左側。相機繞到背後，畫面左右關係會改變，骨架名稱卻不會跟著交換。

VRM 版本也影響座標。兩版皆為右手座標系、Y 軸朝上，但角色的前方與右方不同：

| 格式 | 角色右方 | 上方 | 角色前方 |
| --- | --- | --- | --- |
| VRM 0.x | +X | +Y | −Z |
| VRM 1.0 | −X | +Y | +Z |

來源：[VRM 官方座標說明](https://vrm.dev/api/coordinate/)。螢幕座標、世界座標、骨架局部座標是不同層，不能只根據畫面上的左或右決定旋轉正負號。

這次的程序動作以 **VRM 1.0 座標**編排，再依模型版本轉換。對 VRM 0.x，動作四元數由 `(x, y, z, w)` 轉為 `(-x, y, -z, w)`，沿用 three-vrm-animation 處理 VRMA 的版本適配方式。`getNormalizedBoneNode()` 整理骨架並不代表兩版的前向差異已經消失。[本機動作適配器](../../packages/stage-ui-three/src/composables/vrm/semantic-motion.ts)

不交換 `left*`／`right*` 骨架 ID，也不加 CSS 鏡像來掩蓋方向錯誤。旋轉方向錯誤可能讓手往下或穿過身體；即使模型選對 `wave`，畫面仍未必是正確揮手。

預設 `AvatarSample_A` 的原始檔使用 `extensions.VRM.specVersion: "0.0"`。其中 `meta.version: "1.0"` 是**角色資產修訂版**，不能拿來判斷 VRM 格式。程式使用 three-vrm 提供的 `vrm.meta.metaVersion` 區分格式版本。

方向驗收要把同一段動作從正面與側面都看一次：

1. 正面看右手揮手：確認動的是角色右臂，抬手沒有穿過胸口。
2. 側面看點頭、鞠躬：應朝角色前方彎曲，不能變成後仰。
3. 分別測 VRM 0.x 與 1.0，不用兩個外觀相似的角色替代版本確認。
4. 動作結束或送出 `idle` 後，檢查姿態恢復；重複播放不能累積偏移。
5. 相機轉向後重新觀察，確認程式沒有把觀眾左右誤當角色左右。

本節描述座標修正與驗收方法，不宣稱原生 App 的所有角色方向已完成視覺驗收。模型選對名稱、解析器讀到標記、骨架有變動、動作方向正確，必須分開記錄。

## 查到的技術與整合選擇

| 技術 | 解決的問題 | 本次用途 |
| --- | --- | --- |
| [TalkingHead](https://github.com/met4citizen/TalkingHead) | 嘴型、情緒、手勢與動畫播放，提供 AI function calling 範例 | 參考語意決策與動畫執行的分工 |
| [MotionEngine](https://github.com/lhupyn/motion-engine) | 將語意控制連到姿態、情緒與短動作軌道 | 參考有名稱、可組合的動作控制 |
| [MotionGPT](https://github.com/OpenMotionLab/MotionGPT) | 從文字生成動作序列，也處理動作描述等任務 | 進階研究方向；本安裝包沒有內建此模型 |
| [three-vrm-animation](https://github.com/pixiv/three-vrm/tree/dev/packages/three-vrm-animation) | 載入 VRM Animation，映射至 VRM 角色 | 現有 VRMA 管線及未來導入舞蹈片段的基礎 |

TalkingHead 的主要角色格式是具指定骨架的 GLB，不能把它的動作 API 直接當作所有 VRM 都能使用。因此本次保留 AIRI／three-vrm，另加小型動作適配器。沒有複製第三方舞蹈素材，也沒有新增上述研究模型的權重。

## 2026-10-08 模型與解析器實測

這組測試從本機 Ollama API 輸入合成的單輪文字，沒有使用真人麥克風或圖片。共同設定為 `temperature=0.2`、`num_ctx=4096`、`num_predict=160`、`think=false`。提示放在與 AIRI 相同的使用者訊息後方 `[Context]` 區塊；原始回覆和實際提示均保留在 JSON。

| 測試情境 | 預期動作 | Gemma 4 12B | Qwen 3.5 0.8B | SARC 台語 12B |
| --- | --- | --- | --- | --- |
| 通過考試，請跳舞慶祝 | `dance` 或 `celebrate` | `dance` ✓ | `celebrate` ✓ | 空白變體標記，重播取得 `dance` ✓ |
| 考試沒過，不要跳舞 | `idle` 或 `nod` | `idle` ✓ | `shake`，不符合本題預期 | 空白變體標記，重播取得 `idle` ✓ |
| 早安，請揮手 | `wave` | `wave` ✓ | `wave` ✓ | 未測 |
| 想看慢慢左右搖擺 | `sway` | `sway` ✓ | `idle`，不符合本題預期 | 未測 |

按上述預先定義的動作條件，Gemma 為 **4／4**，Qwen 為 **2／4**。慶祝題接受 `celebrate`，所以通過不表示一定執行了 `dance`。Qwen 的否定題沒有跳舞，但它選的 `shake` 不在本題接受範圍，正文還把使用者遭遇說成自己的遭遇。這些分數不是一般智力、台語能力或所有對話的成功率。

原始紀錄：[Gemma](results/desktop-pet-gemma-semantic.json)、[Qwen 最終版](results/desktop-pet-qwen-semantic-final.json)、[SARC](results/desktop-pet-sarc-semantic.json)。Gemma／SARC 呼叫 `11434`，Qwen 呼叫 App 的 `12434`。載入狀態與服務不同，JSON 的單次耗時不能當成公平的速度排名，也不是語音首字延遲。

SARC 輸出 `< | ACT ... | >`，JSON 鍵值也帶空白。原始探針的嚴格正規表示式記為 `act: null`，兩題都未通過；更新後的 AIRI 標記解析器可正規化這種空白。重播實際原始回答後，**SARC 兩題的動作皆可解析且符合預期（2／2）**。這是格式相容性結果；第一題正文仍偏華語，不能當成台語表達或發音品質已通過。

將三個模型共 10 則原始回覆逐字送入 AIRI 的實際標記與 TTS 分段解析器，結果為：**10／10 取得一個動作、8／10 符合題目動作條件、0／10 的 ACT 控制標記混入 TTS 正文**。[完整重播紀錄](results/desktop-pet-semantic-replay.json)

| 驗證層 | 這份資料能證明的事 | 不能由此推論的事 |
| --- | --- | --- |
| 模型 API | 在指定提示下輸出了哪些字與動作名稱 | 多輪一致性、圖片理解、真人語音辨識 |
| 逐字重播 | ACT 可解析，控制標記與 TTS 正文分離 | 已產生聲音、台語發音正確 |
| 程序骨架播放器 | 有明確的動作允許清單、時長及姿態恢復流程 | 每個 VRM 都有相同外觀或正確衣物碰撞 |
| 原生桌寵 | 必須另做視窗、拖曳、穿透與畫面驗收 | API／解析器通過不等於原生畫面已驗收 |

原生 App 的已觀察項目、方向修正與待驗收項目另外記在[原生驗收紀錄](results/desktop-pet-native-qa.md)。模型／解析器分數不能取代這份畫面與操作紀錄。

### 試錯過程也要留給同學

最早的 Qwen 探針表面上動作 **4／4**，卻每題都回「真替你高興！」，包括考試失敗的題目。只檢查 JSON 動作會漏掉這個問題。[初版原始回答](results/desktop-pet-qwen-semantic.json)

把訊息結構改成實際 AIRI 的 runtime context，再限制正文、否定情境和動作名稱後，仍有選錯動作、複述使用者及輸出不完整標記的情況。這些版本不是彼此獨立的大型評測，不能只挑最高分當成模型能力。[第二版](results/desktop-pet-qwen-semantic-v2.json)、[第三版](results/desktop-pet-qwen-semantic-v3.json)、[第四版](results/desktop-pet-qwen-semantic-v4.json)

評分至少分成三欄：**格式能不能解析、動作是否合意、說話是否合情境**。再加上畫面、STT 和 TTS，才能描述完整角色互動。

### 重現探針與重播

以下在 repository root 執行，需先安裝專案依賴、啟動對應本機 Ollama，並已備妥指定模型。探針不下載模型，不連雲端。若模型都在自己的 `11434`，把 Qwen 命令的埠一起改成 `11434`。

這組命令將新報告放進 `/tmp/airi-semantic-lab`，保留 repository 的原始證據：

```sh
mkdir -p /tmp/airi-semantic-lab

python3 course/ntu-vh2026/desktop/probe-semantic-model.py \
  --endpoint http://127.0.0.1:12434 \
  --model 'qwen3.5:0.8b' \
  --output /tmp/airi-semantic-lab/qwen.json

python3 course/ntu-vh2026/desktop/probe-semantic-model.py \
  --endpoint http://127.0.0.1:11434 \
  --model 'gemma4:12b-it-qat' \
  --output /tmp/airi-semantic-lab/gemma.json

python3 course/ntu-vh2026/desktop/probe-semantic-model.py \
  --endpoint http://127.0.0.1:11434 \
  --model 'hf.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF:Q4_K_M' \
  --language taigi --cases celebration negative_context \
  --output /tmp/airi-semantic-lab/sarc.json
```

`--language taigi` 改的是角色回答規則；這兩題的輸入文字仍為華語，不是台語 ASR 測試。探針會讀取目前的[動作提示](../../packages/stage-ui/src/constants/local-character-motion.ts)，所以新 commit 或模型版本可能產生不同結果。

以下重播 **repository 內既有的 10 則原始回答**，不呼叫模型，也不產生音訊：

```sh
pnpm -F @proj-airi/pipelines-audio build
pnpm -F @proj-airi/core-agent build
node course/ntu-vh2026/desktop/replay-semantic-responses.mjs
```

重播腳本固定讀取上表的三份原始報告，寫回 `results/desktop-pet-semantic-replay.json`。上述版本的預期摘要是 `cases: 10`、`control_leaks: 0`、`action_matches: 8`。它不會自動讀取 `/tmp` 的新探針報告。完整方法見[探針](desktop/probe-semantic-model.py)與[重播腳本](desktop/replay-semantic-responses.mjs)。

## 給同學的實驗

固定角色與 TTS，分別對小模型、大模型說：

1. 「我今天通過考試了！」觀察是否依語意選擇適當慶祝。
2. 「請揮手跟大家打招呼。」觀察動作與回答是否一致。
3. 「我今天很難過，不想慶祝。」檢查否定句，不能只因出現「慶祝」就跳舞。
4. 「請跳一小段舞。」區分選動作成功與骨架播放成功。
5. 用台語重做相同情境，分別記錄 STT、LLM、TTS 與動作結果。

記錄原始回答、ACT 標記、畫面動作、第一個聲音的等待時間。沒有 ACT、錯誤 ACT、動作不合語境，是不同失敗。看到角色待機晃動或嘴型改變，不能當成語意控制成功。

小模型不保證每次遵循標記格式；沒有有效標記時維持待機。未知動作不執行。請依實測記錄評估，不把一次成功推論當作完整能力評測。
