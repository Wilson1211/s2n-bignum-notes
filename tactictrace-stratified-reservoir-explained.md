# TacticTrace：分層 reservoir sampling 詳細說明

整理日期：2026-09-27。

本文說明 `/home/tong-nong/TacticTrace-sampling` 目前實作的 Stage 1 抽樣方法：保留原本的 `legacy`，另外提供可透過參數選擇的 `stratified-reservoir`。這是私人學習筆記，不取代專案中的英文使用文件。

先說結論：**新方法先依每次 tactic 執行後留下的 subgoal 數量分組，再在每一組裡隨機保留有限數量的 records。** 目的在於減少資料過度集中於某一類結果、或只保留早期 records 的情況；目前不能直接宣稱它已經讓 LLM description 更好，仍需要實驗比較。

## 1. 我們到底在哪個階段抽樣？

整個流程可以分成三個 stage：

```text
執行 proof，觀察 tactic 的使用情況
                  │
                  ▼
Stage 1：哪些成功的 tactic records 要留下來？ ← 本文的新方法
                  │
                  ▼
整理資料、去除重複 records
                  │
                  ▼
Stage 2：哪些 records 要放進 description generation 的 prompt？
                  │
                  ▼
LLM 產生 tactic description
                  │
                  ▼
Stage 3：用哪些 records 評估 description？
```

三者不能互相代替。假如 Stage 1 已經丟掉某種行為的所有 records，Stage 2 就算重新隨機抽樣，也無法把那種行為找回來。

本文不是在修改 `describe.py` 的 prompt，也不是修改 LLM judge 的抽樣方式。`describe.py` 的 phase 1／2／3 是另一套分類，不是上圖的三個 stage。即使 description generation 對小型資料集使用所有 deduplicated records，也仍然受到 Stage 1 留下哪些資料的影響。

## 2. 一筆 tactic record 是什麼？

可以先把它理解成一次 tactic 使用的輸入與結果：

```text
goal_before：執行前的 goal，包含 assumptions 與 conclusion
tactic 與 arguments：用了什麼 tactic、傳入什麼參數
goals_after：成功執行後產生的子目標清單
num_subgoals：子目標清單的長度
```

實際輸出還會包含 tactic 定義位置、呼叫位置，以及各個子目標新增或移除的 assumptions 等欄位。

以下只是協助理解的簡化例子，不是實際 JSON 檔：

```text
執行前：目標是 P /\ Q
執行：CONJ_TAC
執行後：[目標 P, 目標 Q]
num_subgoals = 2
```

`num_subgoals = 0` 表示這次 tactic 沒有留下新的子目標，解決了傳給它的這個 goal；不一定表示整份 proof 的其他目標也全部完成。

新抽樣方法不改變 tactic 如何執行，只改變成功執行後的 records 是否保留。失敗的 tactic applications 不在這個成功記錄流程裡，因此不能靠這份樣本完整推論 tactic 的失敗條件。

## 3. 原本的 `legacy` 怎麼做？

這個開發 checkout 的 `max_num_records` 是 20。以下以 `K = 20` 表示一個 tactic 可以保留的 records 上限。

原本的流程是：

1. 檢查執行前與執行後的 goals，過大的 record 不保留。
2. 如果這個 tactic 還沒有存滿 K 筆，直接加入。
3. 存滿後，如果現有 records 的輸入 conclusion 字串長度都小於 100，就停止替換。
4. 否則，把新 record 和舊 records 一起按輸入 conclusion 字串長度排序，移除最長的一筆。

這裡的「短」是 `string_of_term` 印出輸入 conclusion 後，由 OCaml `String.length` 計算的字串位元組數，不是整筆 JSON 的長度，也不是 LLM token 數。若有多位元組字元，也不等於人眼看到的字數。

例如，某個 tactic 最早的 20 筆 records 都很短，而且剛好來自非常相似的 proof 情境，之後遇到的其他行為就可能不再進入資料集。

因此，`legacy` 偏向短小的輸入，但**短小不等於多樣**。新方法就是另一個可以比較的選項，而不是直接刪掉原本的方法。

## 4. 為什麼不是全部 records 直接隨機抽？

假設某個 tactic 有 1,000 筆合格 records：

| 執行結果 | 數量 |
| --- | ---: |
| 留下 1 個 subgoal | 990 |
| 留下 0 個 subgoal | 10 |

如果從全部 records 均勻抽 100 筆，預期只有 1 筆來自第二類，實際也可能完全沒抽到。

「每筆 record 有相同機會」和「不同類型有比較平均的呈現」是兩個不同目標。前者較貼近原始出現頻率；後者比較適合探索不同結果是否能幫助 LLM 描述 tactic 行為。

目前實作選擇後者：先分組，各組分配容量，再在組內隨機挑選。沒有另外實作第三個名為 `reservoir` 的不分組 policy；目前可選的只有 `legacy` 與 `stratified-reservoir`。

## 5. 第一部分：stratified，也就是先分組

目前依 `num_subgoals` 分成三組：

| 組別 | 條件 | 可以觀察到的粗略結果 |
| --- | --- | --- |
| `0` | `num_subgoals = 0` | 解決目前這個 goal |
| `1` | `num_subgoals = 1` | 留下一個 goal；可能有變化，也可能變化很小 |
| `2+` | `num_subgoals >= 2` | 留下多個 goals |

這三組是根據輸出結構分的，不是把 tactic 的語意完整分類。例如同樣留下 1 個 goal，可能是修改 conclusion，也可能是改變 assumptions；目前都放在同一組。

### 5.1 容量 20 如何分配？

程式先把總容量除以 3，再把餘數依序分給前面的組別：

```text
20 ÷ 3 = 6，餘數 2

組別 0  ：6 + 1 = 7
組別 1  ：6 + 1 = 7
組別 2+ ：6     = 6

總容量：7 + 7 + 6 = 20
```

所以是「每個 tactic 合計最多 20 筆」，不是「每組各 20 筆」。

### 5.2 有一組 records 不夠，會把空間給別組嗎？

目前不會。配額是固定的。

| 組別 | 合格 records 數量 | 容量 | 最後保留 |
| --- | ---: | ---: | ---: |
| `0` | 1 | 7 | 1 |
| `1` | 100 | 7 | 7 |
| `2+` | 1 | 6 | 1 |
| 合計 | 102 | 20 | 9 |

這個例子最後只有 9 筆，不會把剩下的 11 個位置給組別 `1`。

特別是永遠只產生一個 subgoal 的 tactic，目前最多留下 7 筆。這是固定配額的取捨，也是後續比較 description 品質時需要注意的因素。

如果未來修改編譯時的總容量，配額會跟著計算；總容量小於 3 時，部分組別甚至會得到 0 個位置。本文不是建議現在修改既有實驗的容量。

## 6. 第二部分：reservoir sampling，組內如何選？

Records 是 proof 執行時一筆一筆出現的，事先不一定知道總共有多少筆。Reservoir sampling 讓程式只保存有限筆 records，同時讓後來出現的 records 仍有機會進入樣本。

對某個 tactic 的某一組，定義：

- `k`：這一組可保留的筆數。
- `n`：到目前為止，這一組累計遇到的合格 records 數量。
- `slots`：存放被選中 records 的位置，索引從 0 開始。

每收到一筆合格 record：

```text
1. n 加 1。
2. 如果 n <= k，直接放入空位。
3. 如果 n > k，均勻隨機產生 j，範圍是 0 到 n - 1。
4. 如果 j < k，用新 record 替換 slots[j]。
5. 否則不保留這筆新 record。
```

注意：`n` 不是目前存了幾筆。即使某筆 record 被抽樣丟棄，`n` 也要加 1，才能讓後續的機率計算正確。

### 6.1 具體例子：容量 2，依序遇到 A、B、C

為了容易看懂，這裡把某一組的容量暫時設想成 `k = 2`，不是修改實際程式的 7／7／6 配額。

```text
遇到 A：n = 1，未滿，保留 [A]
遇到 B：n = 2，未滿，保留 [A, B]
遇到 C：n = 3，已滿，從 {0, 1, 2} 均勻抽一個 j
```

第三步有三種等機率結果：

| 抽到的 j | 動作 | 保留下來 |
| --- | --- | --- |
| 0 | C 替換第 0 格的 A | C、B |
| 1 | C 替換第 1 格的 B | A、C |
| 2 | 不在兩個保留位置內，丟棄 C | A、B |

A、B、C 各自在三種結果中出現兩次，因此每筆最後留下的機率都是 `2/3`。

這個例子是在列出可能結果，不是在聲稱 seed 42 一定產生某個特定 j。

### 6.2 為什麼後來的 records 不會比較吃虧？

當已經存滿 `k` 筆時，第 `n` 筆新 record 的保留機率是 `k/n`。

對於前面某一筆舊 record：它在上一步仍被保留的機率是 `k/(n-1)`；這一步被替換掉的機率是 `1/n`。所以它繼續被保留的機率是：

```text
k/(n-1) × (1 - 1/n) = k/n
```

因此，在均勻隨機抽取的模型下，同一組裡的每一筆合格 record 都有相同的最終保留機率。實作使用固定 seed 的偽隨機序列來執行這些抽取。

但這只保證「組內」的抽樣性質。組與組之間的配額刻意固定，所以整體樣本不是對所有 records 做相同機率的抽樣。

## 7. 為什麼要有 seed？42 是什麼意思？

`--trace-sampling-seed 42` 是指定偽隨機序列的起點，**不是抽 42 筆，也不是選第 42 個 tactic**。

使用相同的 policy 版本、容量、seed、tactic 名稱及相同順序的輸入 records，應該可以重現相同的選取結果。這讓我們可以保存實驗設定，重新執行並檢查差異。

不過：

- 改變輸入 records 或它們在同一組內的順序，即使 seed 不變，結果仍可能改變。
- 換 seed 不保證樣本一定不同。例如某組只有 3 筆而容量是 7，本來就會全部留下。
- 不要只記 seed；還要記錄程式版本、編譯設定、proof 輸入與執行檔來源。

程式替每個 tactic 的每一組維護自己的亂數狀態，不使用 HOL Light 的全域 `Random` 狀態。因此抽樣不會消耗 proof 程式原本使用的那份全域亂數序列；其他 tactic 或其他組別的到達順序，也不會推進這一組的亂數狀態。

實作上使用 tactic 名稱的 FNV-1a hash 結合 seed 與組別編號，再透過 SplitMix64 產生偽隨機值。理解使用方式不需要先熟悉這兩種演算法，重點是狀態彼此獨立、計算規則明確。

### 7.1 為什麼不能直接隨機數除以 n 取餘數？

有限範圍的隨機值直接取餘數，可能造成不同結果機率不一樣。例如假設原始值只有 0 到 7，直接 `% 3`：

```text
餘數 0：原始值 0、3、6，共 3 個
餘數 1：原始值 1、4、7，共 3 個
餘數 2：原始值 2、5，共 2 個
```

程式使用 rejection sampling：先排除無法均分的尾端，再取餘數。以上教學例子若排除 6、7，剩下 0 到 5，三種餘數就各有兩個來源。實際程式使用較大的整數範圍，不是只有 0 到 7。

## 8. 完整流程：先 filter，再抽樣，再輸出

```text
執行 tactic
   │
   ├─ 失敗 ──────────────────────► 不進入這個成功記錄流程
   │
   ▼ 成功
檢查 goal_before 與每個 goals_after
   │
   ├─ 任一 goal 過大 ────────────► filtered 加 1，不參與抽樣
   │
   ▼ 通過
依 num_subgoals 選擇 0 / 1 / 2+ 組
   │
   ▼
該組 eligible_seen 加 1
   │
   ├─ legacy ────────────────────► 原本的保留規則
   │
   └─ stratified-reservoir ──────► 該組的 reservoir 規則
                                      │
                                      ▼
                                更新保留的 records
                                      │
                                      ▼
                         exptrace_dump：印出並寫入 traces
```

目前 checkout 的大小限制沒有因為新 policy 而改變：

- 任一 goal 的 assumptions 數量大於 150，排除整筆 record。
- 任一 goal 的 conclusion 超過 `is_term_too_large` 的計數上限 1,000，排除整筆 record。

第二項是程式對 term 結構的特定計數方式，例如 numeral 算 1，不是字元數，也不是 token 數。這裡沒有逐一檢查每個 assumption 的 term 大小。

`filtered` 計數只表示這裡被大小檢查排除的 records，不包含 tactic 失敗，也不包含 reservoir 沒有選中的合格 records。

容量是「每個 tactic 名稱、每個 collector 生命週期」的限制。`exptrace_dump` 不會清空 collector；如果同一個 process 連續處理多個 theorem，它們可能共用同一份收集狀態，不能直接把容量解讀成每個 theorem 各 20 筆。

## 9. 這和之前的 lazy arguments 有什麼關係？

兩者解決不同問題：

| 功能 | 主要問題 |
| --- | --- |
| sampling policy | 哪些 records 值得保留？ |
| lazy arguments | 被丟棄的 records 是否還要付出印出 arguments 的成本？ |

新 policy 先決定是否接受候選 record，再計算它的 conclusion 字串長度；arguments 則維持 lazy，等到 dump 真正輸出時才求值。

例如一筆 record 一度被選中，後來又被 reservoir 替換掉，它的 arguments 仍可能從未被印出；但在它被選中的當下，計算 conclusion 字串長度的成本已經發生。

這不是「丟棄的 record 完全沒有成本」：仍然要執行 tactic、檢查 goal 大小、更新計數與進行選擇。接受新 record 時，也會重新整理保留清單；不能把整段實作描述成每次都只做固定的一個操作。

## 10. 程式分別寫在哪裡？

以下行號依整理當日版本，之後修改可能移動。

| 位置 | 工作 |
| --- | --- |
| [`exportTrace.ml:49`](../TacticTrace-sampling/exportTrace.ml#L49) | 編譯時的總容量 `max_num_records` |
| [`exportTrace.ml:133`](../TacticTrace-sampling/exportTrace.ml#L133) | 讀取、驗證並快取 sampling 設定 |
| [`exportTrace.ml:166`](../TacticTrace-sampling/exportTrace.ml#L166) | 定義組別、容量與抽樣狀態 |
| [`exportTrace.ml:226`](../TacticTrace-sampling/exportTrace.ml#L226) | `add_reservoir_record`，組內抽樣與替換 |
| [`exportTrace.ml:256`](../TacticTrace-sampling/exportTrace.ml#L256) | 輸出 sampling metadata |
| [`exportTrace.ml:292`](../TacticTrace-sampling/exportTrace.ml#L292) | `exptrace_add_tac`，大小過濾及 policy 分流 |
| [`exportTrace.ml:365`](../TacticTrace-sampling/exportTrace.ml#L365) | `exptrace_dump`，traces 輸出與路徑隔離 |
| [`run-with-sampling.sh`](../TacticTrace-sampling/run-with-sampling.sh) | 將命令列選項轉為環境變數，執行及檢查輸出 |
| [`docs/trace-sampling.md`](../TacticTrace-sampling/docs/trace-sampling.md) | 專案英文用法與限制 |

舊的 conversion 收集規則沒有改成分層 reservoir；不要把 tactic sampling 的效果推廣成所有 conversions 也使用相同方法。

## 11. 如何選擇方法？

### 11.1 必須先確認執行檔真的包含新 collector

**改了 `exportTrace.ml`，不會讓既有的 `.native` 自動更新。**

Collector 會被放進 instrumented proof source，再編譯進執行檔。因此需要在隔離的 build 位置，用新 collector 重新產生 instrumented source，並完成編譯與連結。只重新編譯 kernel wrapper 不夠。

`TacticTrace-sampling` 是開發 checkout；原本 build 使用的 `$HOLLIGHT_DIR/TacticTrace` 不會自動指向它。不能假設 `/home/tong-nong/hol-light/TacticTrace` 或 Tokyo 的既有 `.native` 已經包含新方法。

不要刪除舊的 `.native`、`.correct` 或 traces 來強迫重建。既有 campaign 的限制也不要順手修改；先確認獨立的部署、重建與執行計畫。

### 11.2 先 preview：不執行 proof

以下 `/path/to/rebuilt-proof.native` 是佔位路徑，必須換成已確認使用新 collector 重建的 proof 執行檔。

```bash
cd /home/tong-nong/TacticTrace-sampling

bash run-with-sampling.sh \
  --trace-sampling stratified-reservoir \
  --trace-sampling-seed 42 \
  --trace-output-root /tmp/tactic-stratified-run1 \
  --dry-run -- /path/to/rebuilt-proof.native
```

| 參數 | 意思 |
| --- | --- |
| `--trace-sampling stratified-reservoir` | 使用新方法 |
| `--trace-sampling-seed 42` | 固定抽樣的偽隨機 seed |
| `--trace-output-root ...` | 這次實驗專用的全新絕對路徑 |
| `--dry-run` | 只檢查 wrapper 參數並印出命令，不建立目錄、不跑 proof |
| `--` | wrapper 的選項到此結束，後面是要執行的命令及其參數 |

`--dry-run` 不會確認執行檔真的已重建，也不能證明接下來一定會產生正確的 traces。

### 11.3 確認重建來源後，執行新方法

```bash
bash run-with-sampling.sh \
  --trace-sampling stratified-reservoir \
  --trace-sampling-seed 42 \
  --trace-output-root /tmp/tactic-stratified-run1 \
  -- /path/to/rebuilt-proof.native
```

Preview 不會建立目錄，因此 preview 後仍可用同一路徑真正執行。真正執行過之後，不論成功或失敗，下次應選新的輸出目錄。

### 11.4 用相同的新版執行檔比較舊方法

```bash
bash run-with-sampling.sh \
  --trace-sampling legacy \
  --trace-output-root /tmp/tactic-legacy-run1 \
  -- /path/to/rebuilt-proof.native
```

`legacy` 仍是預設方法。這也是為什麼 merge 新功能不等於把舊演算法刪掉：程式保留兩條路徑，執行時選擇 policy。

Wrapper 本身不需要 `direnv allow`，因為它直接替子程序設定三個 sampling 環境變數。不過 proof 的其他執行環境需求仍然要自行滿足。

### 11.5 Wrapper 和直接設定環境變數的差別

| 設定 | Collector 直接讀取 | Wrapper 命令列 |
| --- | --- | --- |
| policy | `TRACE_SAMPLING_POLICY`，預設 `legacy` | `--trace-sampling`，預設 `legacy` |
| seed | `TRACE_SAMPLING_SEED`，預設 `0` | `--trace-sampling-seed`，預設 `0` |
| output root | `TRACE_SAMPLING_OUTPUT_ROOT` | `--trace-output-root` |
| 目錄要求 | 必須已存在 | 必須尚未存在，由 wrapper 建立 |
| legacy 是否需要 root | 不一定 | 一定需要，以隔離實驗輸出 |

Seed 範圍是 0 到 2147483647。直接設環境變數必須使用標準十進位表示，例如 `42`，不能是 `+42` 或 `042`；wrapper 會把參數中的前導零去掉。

Collector 在第一次收集 tactic 或 dump 時讀取設定，之後快取，不是每一筆 record 都重讀。因此不能在同一個 collector 生命週期裡靠改環境變數切換方法。

Wrapper 會覆蓋子程序的三個 sampling 變數，不受呼叫端先前 export 的 sampling policy 影響，也不改變呼叫端 shell 的設定。它不會重新編譯，也不會繞過 make 的 `.correct` 快取。

如果 proof 在 Docker 裡執行，應在容器裡使用 wrapper，並提供容器看得到的執行檔與輸出路徑；只在主機 export 變數不代表容器一定收到。

## 12. 輸出檔案和 metadata 怎麼看？

假設 proof 原本呼叫：

```ocaml
exptrace_dump "/old/traces/proof.ml"
```

選擇新 output root 後，會變成：

```text
/tmp/tactic-stratified-run1/
├── proof.ml/
│   ├── CONJ_TAC.json
│   └── ...
└── proof.ml.sampling.json
```

原本 tactic/conversion JSON 的欄位格式保留；額外的 `.sampling.json` 放在 record 目錄旁邊，避免被當成另一個 tactic 的 records。

Metadata 的示意片段如下；tactic 名稱與數字是教學例子，不是正式 proof 的實驗結果：

```json
{
  "policy_version": 1,
  "policy": "stratified-reservoir",
  "seed": 42,
  "total_capacity": 20,
  "bucket_names": ["0", "1", "2+"],
  "bucket_capacities": [7, 7, 6],
  "tactics": {
    "EXAMPLE_TAC": {
      "filtered": 4,
      "buckets": [
        {"name": "0", "eligible_seen": 60, "retained": 7},
        {"name": "1", "eligible_seen": 60, "retained": 7},
        {"name": "2+", "eligible_seen": 60, "retained": 6}
      ]
    }
  }
}
```

這表示 4 筆 records 沒通過大小檢查；通過的三組各遇到 60 筆，最後留下 7、7、6 筆。`eligible_seen` 包含被 reservoir 丟棄的合格 records，`retained` 才是最後留下的筆數。

實際 metadata 還包含 `original_output_path` 與 `actual_output_path`。`legacy` 也可輸出三組的觀察統計，但它沒有固定分組配額，所以 `bucket_capacities` 是 `null`。

有 metadata 不代表已保存完整實驗來源。仍應另外記錄 build commit、local changes、HOL Light 版本、執行檔識別資訊、proof 清單及完整命令。

### 12.1 輸出安全檢查的範圍

Wrapper 拒絕使用已存在的 output root。Collector 也拒絕覆蓋既有的 dump 目錄或 metadata。失敗時會保留部分輸出，不會自動刪掉。

重導向使用原始 dump 路徑的最後一個名稱。如果兩個不同 proof 都要輸出到同一個 root 下的 `proof.ml`，會碰撞而失敗，不會自動合併；應使用不同 roots。

Child command 成功結束後，wrapper 會檢查是否存在可解析的 metadata，且 policy、seed、版本與輸出路徑符合預期。這可以避免「沒有新 collector 輸出，卻誤認為成功」的情況。

但這是**執行後**檢查：舊 `.native` 可能先忽略 sampling 變數、寫到原本的路徑，再被 wrapper 判定失敗。因此一定要先確認 build 來源，不能把 wrapper 當作任意舊執行檔的事前隔離保證。

檢查也不會知道所有預期 proofs 是否都跑完；多個 proofs 的 workload 仍需另外核對。

## 13. 目前解決了什麼，又沒有解決什麼？

### 已提供的能力

- 保留 `legacy`，可以選擇是否使用新方法。
- 每個 tactic 分別為 0、1、2+ subgoals 預留容量。
- 同一組中，後面才出現的合格 records 仍有機會被留下。
- 固定 seed 可重現抽樣；使用獨立亂數狀態。
- 透過隔離輸出與 metadata 檢查實驗設定及收集數量。

### 仍然存在的限制

1. **結構分組不等於語意多樣性。** 同一組可能仍然都是非常相似的 goals。
2. **只處理被執行的 proofs。** 如果 proof 來源只涵蓋一小類程式，新 sampler 不會創造其他來源。
3. **不處理失敗案例。** 無法僅靠成功 records 完整描述失敗條件。
4. **不挽救過濾掉的大型 goals。** 大小限制在抽樣之前就生效。
5. **不在此處去重。** 重複 occurrences 仍可佔用多個位置；它對 occurrences 抽樣，不保證不同內容等機率。
6. **不保證把總容量填滿。** 稀少或不存在的組別會留下空額度。
7. **保留比例不代表原始頻率。** 不能因樣本是 7／7／6，就說 tactic 的三類結果原本同樣常見。
8. **後續選取仍可能破壞多樣性。** Dump 仍按輸入 conclusion 長度排序，Stage 2 若只取檔案前幾筆，仍可能偏向短 records。
9. **尚未證明 description 品質提升。** 演算法測試通過不等於 LLM 實驗成功。

因此，之後可以研究更細的分類特徵或容量分配方式，但那些不屬於目前已實作的功能。

## 14. 後續如何確認它對 description 有幫助？

可以分兩層驗證，不要只看最後保留數量有沒有比較平均。

### 第一層：實作是否照設計運作？

專案提供 focused tests：

```bash
cd /home/tong-nong/TacticTrace-sampling

# Build and test the small collector fixture.
make test-trace-sampling HOLLIGHT_DIR=/home/tong-nong/hol-light

# Test only the command-line wrapper.
python3 -B -m unittest discover -s tests -p test_sampling_runner.py -v
```

這些是合成測試，不是完整 s2n-bignum campaign，也不會呼叫 LLM API。它們用來檢查容量、seed 重現、legacy 相容性、輸出檢查等行為，不能代替真實 proof 的部署驗證。

### 第二層：抽樣資料是否讓 description 更好？

建議建立明確的比較設計：

1. 使用相同 proof 來源、大小限制與編譯容量，比較 `legacy` 與 `stratified-reservoir`。
2. 新方法使用數個事先選定的 seeds，觀察結果是否穩定，不挑選最好看的那個 seed 當唯一結果。
3. 記錄每個 tactic 的候選數、過濾數、各組保留數、去重後數量、record 長度與 proof 來源分布。
4. 產生 description 時固定 prompt、模型及資料預算規則。新方法可能保留較少筆，應記下實際筆數與 tokens，避免把資料量差異直接歸因於抽樣品質。
5. 使用沒有放進生成 prompt 的 records 評估。只在 Stage 2 與 Stage 3 各自隨機抽一次，不能保證不重疊；若要測試跨 proof 的泛化，應明確切分 proof 來源。
6. 比較 description 的正確性、涵蓋範圍與過度推論，並挑一些具體案例人工檢查理由是否合理。

實驗仍應從 trace triples 推論 tactic 行為，不把 HOL Light `Help/` 當作 generation prompt 輸入或評估的正確答案。

以上是後續實驗建議，不表示本文建立時已經執行這些實驗。

## 15. 和這次拆分的 PR 有什麼關係？

目前把工作分成兩個相依的本地分支，每個分支各有三筆自己的 commits：

| 本地分支 | 主要內容 |
| --- | --- |
| `feature/trace-sampling-policy` | Collector 演算法、核心測試、policy 文件 |
| `feature/trace-sampling-runner` | 執行 wrapper、wrapper 測試、命令列使用文件 |

第一部分決定「怎麼抽」；第二部分讓使用者比較方便且明確地「選方法、指定輸出位置並檢查結果」。兩個部分都不會自動把新版部署到其他 checkout 或 Tokyo。

這裡的 PR 1／PR 2 是拆分規畫的名稱，不是 GitHub PR 編號。Commit 與 PR 草稿詳見 [tactictrace-sampling-prs.md](tactictrace-sampling-prs.md)。

## 一句話整理

`stratified-reservoir` 是「每個 tactic 先按結果子目標數分組，再在組內用可重現的隨機方法保留有限 records」。它改善的是收集階段的選取方式；是否讓 description 更完整、更正確，還需要控制條件的後續實驗。
