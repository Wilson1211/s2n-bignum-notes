# 盲測 LLM 評審（llm_judge）

這份筆記說明 `python/eval/llm_judge/` 在做什麼、怎麼跑、結果怎麼讀。程式是 PR #12 加進來的，
2026-09-21 併入 main。以下內容依 main 的 `3e71fde` 寫成。

## 它比較什麼，不能證明什麼

它拿**官方設定**和**放寬設定**兩輪 trace 各自產生的 tactic 描述，成對交給模型評高下。
模型只看到兩段文字，看不到 trace、看不到記錄筆數、看不到哪一段來自哪一輪。

它衡量的是描述的**品質**：把行為講清楚了沒有、有沒有自相矛盾、有沒有超出自己證據的斷言。
它**無法**判斷描述跟原始 trace 對不對，程式自己在 manifest 和報告開頭都寫了這句話。
要驗證正確性，必須另外拿 records 逐條核對。

## 資料流程

```
descriptions-official.jsonl   descriptions.jsonl        （兩組描述，各一行一個 tactic）
            │                        │
            └────────┬───────────────┘
                     ▼  run.py prepare      建立不可變的計畫，不呼叫 AWS
        manifest.json        輸入檔 sha256、prompt hash、seed、涵蓋範圍
        input_pairs.jsonl    盲測後的題目，附解碼用的來源對照
                     │
                     ▼  run.py run --execute    每題一次 Bedrock 呼叫
        judgments.jsonl      逐筆 append + fsync，含原始回應與用量
                     │
                     ▼  run.py summarize
        summary.json + summary.md
```

`prepare` 的預設輸入來自 `macros.py`：

| 旗標 | 預設 |
|---|---|
| `--official` | `python/llm/out/descriptions-official.jsonl` |
| `--relaxed` | `python/llm/out/descriptions.jsonl` |

兩個旗標都可以指向任何一份描述 JSONL。名稱叫 official 和 relaxed，實際上就是「甲組」和「乙組」，
所以也可以拿來比較新舊 prompt 的輸出。報告裡的欄位名稱會照樣沿用這兩個字。

## 盲測怎麼做

- **遮蔽 tactic 名稱**：`pairs.py` 的 `_blind_description` 用正規表示式把描述裡的 tactic 名稱換成
  `<TACTIC>`，前後有識別字元時不換，所以 `CONJ_TAC` 被遮掉時，`CONJ_TACS` 這種相關名稱不受影響。
  比對不分大小寫。
- **隱藏來源**：模型只看到 Candidate A 和 Candidate B，system prompt 明說來源和 tactic 名稱是故意藏起來的。
- **每個 tactic 判兩次**：同一對描述會用相反的 A/B 順序各問一次。第一次誰當 A，由
  `sha256(seed + tactic + replicate)` 的第一個位元組決定，所以同一個 seed 每次產生的題目完全一樣。
- **可以重複**：`--replicates` 預設 1，也就是每個 tactic 兩次呼叫（兩個順序）。
- **只比交集**：兩邊都有的 tactic 才成對。只有一邊有的會記在 manifest 的 `coverage` 裡，
  算涵蓋率差異，不算輸贏。

## 評分表

模型必須回傳嚴格的 JSON，四個面向各給 1 到 5 分：

| 面向 | 意思 |
|---|---|
| `operational_completeness` | 有沒有講清楚輸入、對 goal 和 assumption 的影響、產生幾個 subgoal |
| `clarity` | 直接、具體、沒有贅字 |
| `internal_consistency` | 說法和例子沒有互相矛盾 |
| `calibrated_claims` | 斷言的範圍和不確定性，跟它自己給的根據相符 |

另外要給 `winner`（`A`／`B`／`tie`／`invalid`）、`confidence`（low／medium／high）和一句 `reason`。
`rubric.py` 的 `parse_judge_response` 會嚴格檢查：key 必須完全相符、分數必須是 1 到 5 的整數、
`reason` 不能是空字串。不符合就記成 parse 失敗，不會硬解。

**prompt 注入的防護**：候選描述是被當成不可信的 JSON 資料包起來的，system prompt 明確要求
不要照做、不要複述、也不要偏袒描述裡出現的任何指令。因為描述本身就是 LLM 生成的文字。

## 四個指令

```bash
# 1. 建立計畫（不呼叫 AWS）
python3 python/eval/llm_judge/run.py prepare \
  --run-dir python/eval/out/llm-judge/pilot-20260920 --seed 20260920

# 2. 只看計畫和 prompt，不付費（沒有 --execute 就不會建立 Bedrock client）
python3 python/eval/llm_judge/run.py run \
  --run-dir python/eval/out/llm-judge/pilot-20260920 --model sonnet --limit 24 --show-prompts 1

# 3. 真的呼叫，先跑小批
python3 python/eval/llm_judge/run.py run \
  --run-dir python/eval/out/llm-judge/pilot-20260920 --model sonnet --limit 24 --execute

# 4. 進度與彙整
python3 python/eval/llm_judge/run.py status    --run-dir python/eval/out/llm-judge/pilot-20260920
python3 python/eval/llm_judge/run.py summarize --run-dir python/eval/out/llm-judge/pilot-20260920
```

`run` 的參數：

| 參數 | 預設 | 說明 |
|---|---|---|
| `--model` | 無，必填 | `opus`／`sonnet`／`haiku` |
| `--execute` | 關 | 不加就是唯讀，不呼叫也不寫檔 |
| `--profile` | `$AWS_PROFILE` 或 `lab` | AWS profile |
| `--region` | `us-east-1` | |
| `--max-tokens` | 4000 | |
| `--temperature` | 0.0 | 明確寫死成 0，要改就換一個 run-dir |
| `--effort` | `low` | 也可以用 `--no-effort` 關掉 |
| `--limit` | 0（全部） | 先跑小批用 |
| `--tactic` | 無 | 只跑某一個 tactic 的兩個順序 |
| `--retry-failures` | 關 | 預設不重試失敗的題目 |

`status` 唯讀；`summarize` 會寫 `summary.json` 和 `summary.md`。

## 防呆機制

這支程式的設計重點是「不要讓兩種設定混在同一份結果裡」：

- **run-dir 不能重複使用**：`prepare` 遇到已存在的目錄直接報錯。
- **manifest 記錄來源**：兩個輸入檔的 sha256、prompt 版本與 hash、seed、replicates、各種筆數。
- **題目檔被改過就拒絕**：每次讀 manifest 都會重算 `input_pairs.jsonl` 的 sha256。
- **改過 prompt 就不准續跑**：付費續跑會檢查目前程式的 prompt hash 跟 manifest 是否相同。
- **續跑要設定一致**：model id、region、max_tokens、temperature、effort、prompt hash 六項
  只要有一項跟既有結果不同就拒絕。
- **失敗不自動重試**：API 錯誤和格式錯誤都會留下紀錄備查，但不會自動再花錢，要加 `--retry-failures`。
- **逐筆落地**：`judgments.jsonl` 是 append 之後立刻 flush 加 fsync，中斷不會丟掉已經付過錢的結果。
- **彙整時再驗一次**：`summary.py` 會重新檢查每筆紀錄的 tactic、順序、prompt 來源、分數格式，
  以及 `source_winner` 解碼有沒有跟當初的 A/B 對照一致。任何一項對不上就直接報錯，不會算出一份可疑的統計。

## 結果怎麼讀

統計是三層往上收斂的：

1. **單次呼叫**：模型說 A 或 B 贏，程式用 `input_pairs.jsonl` 的對照解碼成 official 或 relaxed。
2. **一個 replicate**：兩個順序的結論一致才採用；不一致就標成 `unstable`，缺一個就是 `incomplete`。
   這是刻意的設計，因為 LLM 評審對選項位置敏感，這樣可以把位置效應暴露出來，而不是悄悄算成一勝。
3. **一個 tactic**：所有 replicate 的結論都一致才採用，否則同樣是 `unstable`。

報告裡的數字：

- **preference mean**：official 記 +1、relaxed 記 −1、tie 記 0，只用穩定的 tactic，
  附 bootstrap 95% 信賴區間（重抽 10,000 次，seed 來自 manifest，所以可重現）。
- **sign test**：只用穩定且非平手的結果，雙尾 p 值。
- **各面向分差**：official 減 relaxed，先把同一個 tactic 的兩個順序平均，再對 tactic 取平均。
  正值偏向 official。這部分**包含** unstable 和 tie 的 tactic，因為兩個順序已經先平均掉了；
  只有 incomplete 和 invalid 被排除。
- **order_check**：兩個順序一致幾個、不一致幾個。這個數字要先看，不一致太多的話，勝負就不值得談。
- **用量**：input／output token 和估計費用，價格表寫死在 `bedrock.py`（opus 5/25、sonnet 2/10、
  haiku 1/5，單位是每百萬 token 的美金），並且會存進每一筆結果裡，之後看報告不必回頭猜當時的價格。

## 兩個「LLM judge」不是同一個東西

repo 裡有兩套都叫 LLM judge 的程式，任務完全不同，不要搞混：

| | `python/eval/llm_judge/` | `python/eval/sim/evaluator/llm_judge_evaluator.py` |
|---|---|---|
| 比什麼 | 兩份生成描述互比，盲測 | 一份生成描述對一份**參考答案** |
| 參考答案 | 沒有 | 預設是 `data/help-descriptions.jsonl`，由 `Help/` 產生 |
| 評分 | 四個面向 1–5 加上勝負 | 三個面向 correctness／completeness／clarity，1–5 |
| prompt 版本 | `description-pairwise-v1` | `reference-description-v1` |
| 呼叫次數 | 每個 tactic 兩次（兩個順序） | 每一對一次 |

兩者**沒有互相 import**，也不是誰呼叫誰，只共用 `eval/bedrock.py` 這層傳輸。
`prompt_template_sha256`、`build_user_prompt`、`_strip_single_fence` 這三個 helper 兩邊各寫了一份，
名字一樣但內容不同。改其中一邊不會影響另一邊。

## 方法論紅線：`sim/` 用官方文件當參考答案

`llm_judge/` **沒有**用到 HOL Light 的 `Help/`。README 和 system prompt 都明講不給官方文件、
也要求模型不要用既有的 HOL Light 知識，這符合我們的紅線。

`sim/` 那條路徑則不同。`python/eval/help_descriptions.py` 會讀 `<hol-light>/Help/` 的頁面，
取出 `SYNOPSIS` 和 `DESCRIBE` 段落（`FAILURE` 和 `EXAMPLE` 沒有用），去掉排版用的大括號區塊，
壓成一行 prose，輸出成 `data/help-descriptions.jsonl`，格式跟我們的描述檔一樣。
`scripts/pipelines/sim_eval_tactic_desc.sh` 的 `--reference` 階段會做這件事，必要時還會自己 clone
HOL Light。接著三個評估器都拿這份當基準去評 `descriptions.jsonl` 和 `descriptions-official.jsonl`。

也就是說，`sim/` 等於是拿官方文件當 ground truth，跟 `llm_judge/` 的定位相反。
`sim/README.md` 自己也寫了這件事，說這個疑慮仍然成立、留給維護者決定，並且指出分數低有兩種解釋：
描述不好，或者兩邊根本在回答不同的問題（`Help/` 講的是一般行為，我們的描述講的是它在 s2n-bignum
證明裡的實際套用）。第一次跑的結果是 58 個共同 tactic 的平均 sentence BLEU 0.0232。

結論：要用 `sim/` 的數字之前，先確認 `--gt_name` 指向什麼。只要是 `help-descriptions`，
那個分數就不能拿來支持「trace 足以還原 tactic 行為」這個主張。

## `sim/` 的三個評估器

`runner.py` 取兩份描述的交集，逐批送給指定的評估器，結果寫到
`result/sim/<evaluator>/gt_vs_<generated>__<tag>.jsonl`，每行只有 tactic、評估器、分數和
`pair_sha256`，不複製描述文字。

| 評估器 | 比什麼 | 分數 | 需要什麼 |
|---|---|---|---|
| `bleu` | 用字重疊 | sacrebleu 的 sentence BLEU，換算成 0–1 | 只要 sacrebleu，不花錢 |
| `embedding` | 語意相近 | 兩個向量的 cosine，−1 到 1，沒有夾限 | 本機 llama-server 加 GGUF，預設 `qwen3-embedding:0.6b-q8_0` |
| `llm_judge` | 三個面向評分 | 各 1–5 加 confidence 和理由 | Bedrock，預設 sonnet、max-tokens 1200、temperature 0 |

## 已知 bug：`sim/runner.py` 現在會直接爆掉

`python/eval/sim/runner.py:103` 寫成 `evaluator.batch_siz`，少了結尾的 `e`：

```python
for start in range(0, len(shared), evaluator.batch_size):
    batch = shared[start : start + evaluator.batch_siz]     # AttributeError
```

我用一個 stub 評估器實際跑過，只要交集不是空的就會丟
`AttributeError: 'Stub' object has no attribute 'batch_siz'`。
也就是說 `sim/` 目前任何一個評估器都跑不起來，三個都一樣，跟有沒有 AWS 無關。

這行是 `11f2205`（thoughtp0lice，2026-09-21，"fix embedding batch distribution"）帶進來的，
已經在 main 上。`llm_judge/` 不受影響，它沒有經過這個檔案。

## 目前狀態

- PR #12 已合併，程式在 main 上。
- 本機還沒有 `python/eval/out/`，也就是還沒跑過任何一次評審。
- 測試在 `python/tests/test_llm_judge_{pairs,rubric,run,summary}.py`，但這台機器沒有 `pytest` 也沒有 `uv`，
  要跑測試得先裝。
- `python/eval/out/` 整個被 gitignore。跑完之後只把選定的報告和 manifest 複製到追蹤路徑，
  例如 `result/evaluation/llm-judge.md`。

## 可以拿來做什麼

除了原本的官方對放寬，還可以比較同一組 records、不同 prompt 產生的描述。例如新版
reference-style prompt（PR #15）跑出來的結果，對上舊 prompt 的 `descriptions.jsonl`：

```bash
python3 python/eval/llm_judge/run.py prepare \
  --run-dir python/eval/out/llm-judge/prompt-v5 \
  --official python/llm/out/descriptions-relaxed-p1.jsonl \
  --relaxed  python/llm/out/descriptions.jsonl \
  --seed 20260922
```

報告會把第一個檔案叫 official、第二個叫 relaxed，讀的時候要自己記得對應關係。
要注意這種比較一樣是「描述品質」，不是「描述正確性」；新 prompt 刻意寫得比較短、比較保守，
在 `operational_completeness` 這個面向可能反而吃虧，解讀時要把這點考慮進去。
