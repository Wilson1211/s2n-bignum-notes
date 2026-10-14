# TacticTrace 的兩個 PR：等到最後才把 tactic 引數轉成文字

這份筆記寫給**完全沒有背景**的讀者，解釋兩個送到上游 `hol-light/TacticTrace` 的 draft pull request：

| | 標題 | 分支（在 fork `Wilson1211/TacticTrace` 上） |
|---|---|---|
| **PR #1** | [1/2] Defer tactic argument rendering until trace dump | `perf/lazy-tactic-arguments` |
| **PR #2** | [2/2] Add regression coverage for lazy tactic arguments | `perf/lazy-tactic-arguments-tests` |

完整的英文調查過程在 [tracing-overhead.md](tracing-overhead.md)。這裡的數字都出自那份紀錄或兩個 PR 的說明，程式碼片段都是從實際的 diff 或檔案複製過來的。

*寫於 2026-09-22。兩個 PR 都還是 draft，內容可能再變。*

---

## 1. 一句話總結

- **PR #1**：TacticTrace 記錄證明過程時，原本每做出一筆「候選紀錄」就立刻把 tactic 的引數轉成文字，就算那筆紀錄下一刻就被丟掉也照轉。PR #1 改成**先不轉，等最後確定要寫進檔案的紀錄才轉**。在一個測試證明上，時間從 1,549 秒降到 639 秒，輸出檔案一個位元組都沒變。
- **PR #2**：幫 PR #1 加一個自動測試，確保以後沒有人不小心把它改回「立刻轉文字」。

（PR 是 pull request 的縮寫，意思是「請對方把我的修改收進他的專案」的申請，第 2.12 節會再細講。）

下面先把這兩句話裡的每個名詞講清楚，再進入 PR 本身。

---

## 2. 背景名詞

依照閱讀順序排列，前面的名詞會被後面用到。

### 2.1 定理證明器、HOL Light

寫在紙上的數學證明要靠人來檢查，人會看漏。**定理證明器（theorem prover）** 是一種程式，會逐步檢查證明的每一步是否符合邏輯規則，只要有一步不嚴謹就拒絕接受。可以把它想成一位極度嚴格、永遠不會累的數學老師。

**HOL Light** 是其中一個定理證明器。

### 2.2 s2n-bignum 與這個研究專案

**s2n-bignum** 是 AWS 開源的大數運算函式庫（給密碼學用），裡面的程式附有用 HOL Light 寫成的正確性證明。

我們的研究專案要做的事：把這些證明「一步一步」拆開記錄下來，每一步存成（**做之前的狀態、這一步用的指令、做之後的狀態**）三元組，之後交給 LLM，讓它學著用自然語言描述每種指令在做什麼。

### 2.3 目標（goal）與證明狀態

國中幾何題常寫成「**已知**……，**求證**……」。HOL Light 裡的**目標（goal）** 就是這個結構：

- **前提（assumption）**：目前手上已知可以用的事實，是一個清單。
- **結論（conclusion）**：還沒證出來、要證明的那句話。

**證明狀態（proof state）** 就是「目前還剩哪些目標要證」。下面是從 `bignum_mux` 的 trace 裡取出來的一個目標，印成文字的樣子（取自 tracing-overhead.md）：

```
  0 [`forall x y. R x y ==> P x y`]             <- assumption: not counted
  1 [`forall x y. P x y ==> P y x`]             <- assumption: not counted
  2 [`forall x y z. P x y /\ P y z ==> P x z`]  <- assumption: not counted

`forall x y. STC R x y ==> P x y`               <- conclusion: counted, 31 characters
```

上面三行編號的是前提，最後一行是結論。右邊的註解（「not counted」「counted」）跟 3.1 節的排名規則有關，先不用管。

### 2.4 Tactic（策略）

**tactic** 是作用在目標上的一個「解題動作」。做完之後，原本的目標會變成零個或多個比較簡單的新目標；變成零個就代表這個目標證完了。

類比：解題時說「兩邊同除以 2」或「分成 x ≥ 0 和 x < 0 兩種情況討論」，這些都是 tactic。HOL Light 的 tactic 名字通常長得像 `REWRITE_TAC`、`ARITH_TAC`。

所以研究專案要的三元組就是：（做之前的目標，tactic，做之後的目標們）。

### 2.5 Tactic 的引數（argument）

有些 tactic 需要額外的輸入才知道要怎麼做。例如 `REWRITE_TAC`（「用某些定理改寫」）要告訴它**用哪些定理**。這些額外輸入就叫**引數**。

類比：「用畢氏定理改寫」這個動作裡，「畢氏定理」就是引數。

tracing-overhead.md 裡的真實例子：`REWRITE_TAC` 的引數是 `[(|- forall R. STC R = TC (SC R))]`，也就是一個定理。

### 2.6 Conversion（conv）

**conversion** 是另一種工具：它不處理整個目標，而是拿一個式子，產生「這個式子 = 另一個式子」的定理。名字通常以 `_CONV` 結尾。TacticTrace 對 tactic 和 conversion 都會記錄，但**這兩個 PR 只改 tactic 的部分**，conversion 完全沒動。

### 2.7 OCaml

**OCaml** 是一種程式語言。HOL Light 是用 OCaml 寫的，HOL Light 的證明檔本身也是 OCaml 程式，TacticTrace 同樣是 OCaml。本文會出現的 OCaml 寫法：

| 寫法 | 意思 |
|---|---|
| `let x = ... in` | 把某個值取名叫 `x`，後面可以用 |
| `(a, b, c)` | 把三個東西綁成一組（tuple，元組） |
| `f ()` | 呼叫函式 `f`，`()` 代表「不需要額外輸入」 |
| `(* ... *)` | 註解，給人看的，程式不執行 |
| `;;` | 一段頂層程式的結尾 |

### 2.8 「轉成文字」（render / print）為什麼貴

在 HOL Light 執行時，式子（term）和定理（theorem）在記憶體裡**不是文字**，而是一棵樹狀的資料結構。但最後要寫成 JSON 檔，而 JSON 只能放文字，所以需要把樹「印」成文字，這個動作英文叫 render 或 print。負責的函式是 `string_of_term`（式子）和 `string_of_thm`（定理）。

印的時候要走遍整棵樹，決定括號、運算子擺哪、要不要標型別，樹越大越花時間。類比：把一張複雜的電路圖改用文字一條一條描述出來。

TacticTrace 印引數時的規則（出自 `ocamlTypes.ml`，tracing-overhead.md 也有整理）：

- 式子引數：用 `string_of_term` 整個印出來，沒有長度上限。
- 定理引數：先用 `string_of_thm` **整個印出來**，印完發現超過 1,000 個字元，才把它換成 `(omitted thm)`。也就是說，就算最後沒用到那段文字，印的功夫已經花掉了。
- 函式之類印不出來的引數：直接寫固定字串 `(don't know how to express)`，幾乎不花時間。

### 2.9 TacticTrace、trace、紀錄（record）

**TacticTrace** 是上游（原作者）寫的工具。它會改寫一個證明檔，讓裡面**每一次呼叫 tactic 都順便回報**：做之前的目標、引數、做之後的目標。這種「在程式裡插入額外記錄程式碼」的手法叫 **instrumentation（插樁）**。

每一次回報會變成一筆**紀錄（record）**。證明檔的最後一行會被加上 `exptrace_dump "<目錄>";;`，這個函式在整份證明跑完後，替每個 tactic 寫出一個 `<tactic 名字>.json`。這些檔案合起來就叫 **trace**。

本文會一直提到 `exportTrace.ml` 這個檔案裡的三個函式：

| 函式 | 什麼時候跑 | 做什麼 |
|---|---|---|
| `exptrace_add_tac` | 每次 tactic 被呼叫之後 | 決定這筆紀錄要不要留 |
| `all_tac_records_interesting` | 由 `exptrace_add_tac` 呼叫 | 檢查某個 tactic 留下的紀錄是不是「都夠短」 |
| `exptrace_dump` | 整份證明跑完之後，一次 | 把留下來的紀錄寫成 JSON |

### 2.10 延遲求值（lazy evaluation）

先講類比。假設你在旅行時用底片相機拍了幾百張照片，但相簿只放得下 100 張：

- **原本的做法**：每拍一張就立刻送去沖洗。最後只挑 100 張放進相簿，其他幾百張的沖洗費全部白花。
- **延遲的做法**：底片先留著，等相簿要放哪 100 張確定之後，只沖洗那 100 張。

這就是**延遲求值（lazy evaluation）**：一件昂貴的工作先不做，只記下「需要時要怎麼做」，真的需要結果時才做。

OCaml 內建這個功能：

| 寫法 | 意思 |
|---|---|
| `lazy (某個運算)` | 不執行，只做出一張「欠條」：記住之後要執行什麼 |
| `X Lazy.t` | 這張欠條的型別：「一個之後兌現時會得到 `X` 的東西」 |
| `Lazy.force 欠條` | 兌現：真的執行那個運算，拿到結果。第一次兌現後結果會被記住，再兌現也不會重算 |
| `Lazy.from_val 值` | 把一個**已經算好**的值包成欠條的樣子。型別一樣，但運算在包之前就做完了 |

最後一行在第 6.4 節會用到。

### 2.11 回歸測試（regression test）、`assert`

「回歸」（regression）在這裡的意思是**退步**：一個原本修好的行為，因為後來別人改了程式，又壞回去了。**回歸測試**就是一段自動執行的檢查程式，專門盯著某個修好的行為，確保它不會退步。

測試裡常用 **`assert 條件`**：條件成立就繼續往下跑；不成立，程式立刻報錯並中止。測試就是由一連串 `assert` 組成的。

### 2.12 Git 與 GitHub 的名詞

| 名詞 | 白話解釋 |
|---|---|
| repository（repo） | 一個專案的所有檔案加上完整修改歷史 |
| commit | 一次存檔：一組修改加上一段說明，有一串代號（hash），例如 `c388c96` |
| branch（分支） | 一條有名字的 commit 序列，可以在上面做實驗而不影響主線 `main` |
| diff | 兩個版本之間「哪幾行被刪、哪幾行被加」的清單。`-` 開頭是刪掉的，`+` 開頭是加上的 |
| upstream（上游） | 原作者的專案，這裡是 `hol-light/TacticTrace` |
| fork | 在 GitHub 上把別人的 repo 複製一份到自己帳號下，這裡是 `Wilson1211/TacticTrace` |
| pull request（PR） | 從自己的 fork 向上游提出「請把這個分支的修改收進你的某個分支」的申請，上游可以審查、留言、決定要不要合併（merge） |
| base branch | PR 要合併進去的那個分支，兩個 PR 都是 `main` |
| draft PR | 標記為「還沒準備好合併」的 PR，可以先讓人看 |
| stacked PR（疊起來的 PR） | 後一個 PR 建立在前一個 PR 的修改之上，必須先合併前一個 |
| force-push | 用改寫過的歷史覆蓋遠端分支，commit 的 hash 會因此改變 |

### 2.13 Makefile 與 target

`make` 是一個「照食譜做菜」的工具。**Makefile** 是食譜本，裡面每一道食譜叫一個 **target**，寫著「要做出這個，需要先有哪些東西，然後執行哪些指令」。

在終端機打 `make test`，就是執行名叫 `test` 的 target。如果 `test` 寫著它依賴另一個 target，`make` 會先把那個做好。

---

## 3. 問題：為什麼 trace 這麼慢

### 3.1 TacticTrace 怎麼決定留哪些紀錄（原作者的設計，兩個 PR 都沒改）

一個大證明會呼叫同一個 tactic 成千上萬次，全部記下來檔案會爆掉。所以 TacticTrace 對**每個 tactic 最多只留 `max_num_records` 筆**。上游預設是 20，我們的放寬設定是 100。

那要留哪幾筆？原作者的標準是「**做之前那個目標的結論，印成文字越短越好**」。程式如下（`exportTrace.ml`）：

```ocaml
  let mk_tac_record_interestingness (tr:tac_record) =
    {
      input_concl_str_len = String.length (string_of_term (snd tr.goal_before))
    }
```

逐段讀：`tr.goal_before` 是做之前的目標，`snd` 取出它的結論，`string_of_term` 印成文字，`String.length` 數字元數。得到的整數 `input_concl_str_len` 就是這筆紀錄的**排名分數**，越小越好。注意：前提、做之後的目標、**引數**，全都不影響排名。

每次呼叫 tactic 後，`exptrace_add_tac` 依序做這些判斷（步驟編號沿用 tracing-overhead.md）：

```
[1] 做之前或做之後的目標太大（前提太多或結論太大）？ ── 是 ─► 不記
        │ 否
[2] 這個 tactic 的紀錄還沒滿 max_num_records 筆？ ────── 是 ─► 做出完整紀錄，加進去
        │ 否（已滿）
[3] 留下的每一筆，結論都短於 100 個字元？ ─────────── 是 ─► 不記，而且從此這份清單永遠不會再變
        │ 否（至少一筆 ≥ 100）
[4] 做出完整紀錄 → 和原本的 N 筆一起共 N+1 筆 → 按排名分數排序 → 丟掉最長的那筆

        …… 整份證明跑完 ……

[5] exptrace_dump：把每個 tactic 留下的紀錄排序後寫成 <tactic>.json
```

第 [4] 步被丟掉的，可能是**剛做出來的新紀錄**，也可能是**某筆舊紀錄**。

「判斷紀錄夠不夠短」的就是 `all_tac_records_interesting`（這是 PR #1 之後的版本，差別在第 4 節說明）：

```ocaml
  let all_tac_records_interesting
      (tr: (tac_record * record_args Lazy.t * tac_record_interestingness) list): bool =
    let interesting_concl_strlen = 100 in
    List.for_all (fun (_,_,i) -> i.input_concl_str_len < interesting_concl_strlen)
      tr
```

`List.for_all` 檢查清單裡**每一筆**的排名分數是否都小於 100。

### 3.2 一個小例子

為了好算，假設上限是 3 筆（實際是 20 或 100），數字是舉例用的：

| 時間點 | 發生什麼 | 留下的紀錄（結論長度） | 這一步有沒有印引數 |
|---|---|---|---|
| 1–3 | A(40)、B(120)、C(200) 依序進來，還沒滿，直接加 | A40, B120, C200 | 有，印了 A、B、C |
| 4 | D(80) 進來。已滿，B、C 都 ≥ 100，走第 [4] 步：排序成 A40, D80, B120, C200，丟掉 C | A40, D80, B120 | 有，印了 D；**C 之前印的白費了** |
| 5 | E(300) 進來。走第 [4] 步：排序後 E 最長，丟掉 E 自己 | A40, D80, B120 | 有，印了 E；**E 剛印完就丟掉** |
| 6 | F(60) 進來。走第 [4] 步：丟掉 B | A40, F60, D80 | 有，印了 F；**B 之前印的白費了** |
| 7 之後 | 留下的三筆都 < 100，走第 [3] 步：什麼都不做 | A40, F60, D80（不再變動） | 沒有 |

總共印了 6 次引數（A–F），最後只有 3 筆（A、D、F）寫進檔案，另外 3 次（B、C、E）全是白工。

### 3.3 真實情況有多糟

在真正的 s2n-bignum 證明裡，上面的「白工」會被放大很多倍：

- **很多 tactic 永遠到不了第 [3] 步。** 在 `mldsa_caddq` 這個證明裡，70 個填滿清單的 tactic 中，有 24 個最後留下的紀錄仍然不是全都短於 100 字元，所以它們之後的每一次呼叫都會走進第 [4] 步。
- **引數可能很大。** 定理和式子引數是整個印出來的（見 2.8 節），ML-DSA 這類向量運算的證明狀態又特別龐大。

實測結果（`mldsa_caddq`，放寬設定，出自 tracing-overhead.md）：

| 設定 | 時間 |
|---|---:|
| 完全不做 trace | 203 秒 |
| 開 trace（改動前） | 1,549 秒 |
| 開 trace，留下的紀錄完全相同，但引數一律不印（實驗用，引數欄位留空） | 644 秒 |

在 1,549 秒裡，約 896 秒（58%）可以歸到「替換」流程（主要是第 [4] 步）。光是「不印引數」這一項，就把時間降到 644 秒。結論是：**時間幾乎都花在替還沒確定要留的候選紀錄印引數**。

補充一點背景：這段程式是原作者的，不是我們寫的。上游預設的 `max_assumptions = 150` 會在第 [1] 步把大部分 ML-DSA 目標直接擋掉，所以問題在上游不明顯。我們為了收集資料把上限放寬（`max_num_records` 20 → 100、`max_assumptions` 150 → 100,000、`maxcnt` 1,000 → 1,000,000），才讓大量目標走到第 [4] 步，問題因此浮現。

### 3.4 原作者其實已經延後了一半

上游原始檔案第 20 行有這個註解：

```ocaml
  (* Separate record_args to lazily evaluate this (otherwise it takes too long) *)
```

意思是：「把 `record_args` 拆出來，好讓它延遲計算（不然太花時間）」。

原作者確實做了一部分延遲：引數不是直接傳進 `exptrace_add_tac`，而是傳一個小函式 `re_arg_gen`，**呼叫它的時候才會把引數印成文字**。在 TacticTrace 自動產生的包裝程式碼裡，它就是那段 `fun () -> { ... }`。

問題在於原本的程式在第 [2] 步和第 [4] 步「做出完整紀錄」時就立刻呼叫它：

```ocaml
  let mk_full_rec() = (re, re_arg_gen(), mk_i()) in
```

所以原本的延遲只省到第 [1] 步和第 [3] 步（這兩步根本不做紀錄）；第 [4] 步仍然是「先印，再排序，再丟」。PR #1 把延遲再往後推，一路推到第 [5] 步。

---

## 4. PR #1 在改什麼

### 4.1 概觀

| commit | 說明 |
|---|---|
| `c388c96` Defer tactic argument rendering until trace dump | 核心修改 |
| `9f33164` Explain lazy tactic argument retention | 只加三行白話註解，不改行為 |

只改一個檔案：`exportTrace.ml`。整個 diff 分成四處。

### 4.2 第一處：型別宣告改成「欠條」

```diff
   let all_tac_records_interesting
-      (tr: (tac_record * record_args * tac_record_interestingness) list): bool =
+      (tr: (tac_record * record_args Lazy.t * tac_record_interestingness) list): bool =
```

```diff
   let tac_logs
     :(string,
-        (tac_record * record_args * tac_record_interestingness) list)
+        (tac_record * record_args Lazy.t * tac_record_interestingness) list)
       Hashtbl.t =
+    (* Tactic arguments stay lazy while records compete for retention.
+       Conversion records remain eager below. *)
     Hashtbl.create 128
```

背景：每一筆 tactic 紀錄在記憶體裡是一個三元組：

1. `tac_record`：做之前的目標、做之後的目標、行號等等（這些都還是樹狀資料，沒有印成文字）。
2. `record_args`：引數（原本已經是印好的文字）。
3. `tac_record_interestingness`：排名分數（一個整數）。

`tac_logs` 是一張**雜湊表（`Hashtbl`）**，可以想成通訊錄：用 tactic 的名字查到它的紀錄清單。

OCaml 會在編譯時檢查型別，所以第 2 個欄位從「印好的引數」變成「引數的欠條」（`record_args Lazy.t`）之後，所有明確寫出這個型別的地方都得跟著改：

- `tac_logs`：那張表本身。
- `all_tac_records_interesting`：它只看第 3 個欄位（`(_,_,i)` 的 `i`），完全不碰引數，所以只是型別標註跟著改，行為不變。

新加的註解（來自 `9f33164`）翻成中文是：「在紀錄互相競爭名額的期間，tactic 的引數保持延遲；conversion 的紀錄在下面仍然是立刻計算。」

### 4.3 第二處：做紀錄時不再印引數（核心）

```diff
-  let mk_full_rec() = (re, re_arg_gen(), mk_i()) in
+  (* Do not call re_arg_gen here: the retention logic may discard this record. *)
+  let mk_full_rec() = (re, lazy (re_arg_gen()), mk_i()) in
```

這是整個 PR 最重要的一行。`mk_full_rec()` 做出上面說的三元組：

| 欄位 | 改之前 | 改之後 |
|---|---|---|
| `re` | 紀錄本體 | 不變 |
| 引數 | `re_arg_gen()`：**現在就呼叫**，印成文字 | `lazy (re_arg_gen())`：**不呼叫**，只做出欠條 |
| `mk_i()` | 現在就算排名分數 | 不變，仍然現在算，因為第 [4] 步排序需要它 |

新註解的意思是：「不要在這裡呼叫 `re_arg_gen`：保留規則可能會把這筆紀錄丟掉。」

修改後完整的 `exptrace_add_tac` 長這樣，可以對照 3.1 節的第 [1]–[4] 步：

```ocaml
let exptrace_add_tac (tactic_name:string)
        (re:ExportTrace.tac_record)
        (re_arg_gen:unit -> ExportTrace.record_args)=
  if ExportTrace.is_goal_too_large re.goal_before ||
    List.exists ExportTrace.is_goal_too_large re.goals_after
  then () (* too large goal to register :( *) else

  let logs = ExportTrace.tac_logs in
  (* Lazily calculate interestingness of this tac_record 're'. *)
  let mk_i () = ExportTrace.mk_tac_record_interestingness re in

  (* Do not call re_arg_gen here: the retention logic may discard this record. *)
  let mk_full_rec() = (re, lazy (re_arg_gen()), mk_i()) in

  match Hashtbl.find_opt logs tactic_name with
  | None ->
    Hashtbl.add logs tactic_name [mk_full_rec()]
  | Some records ->
    if List.length records < ExportTrace.max_num_records then
      Hashtbl.replace logs tactic_name (mk_full_rec()::records)
    else if ExportTrace.all_tac_records_interesting records then
      () (* no need to update records *)
    else begin
      assert (List.length records = ExportTrace.max_num_records);
      let new_records = List.sort
          (fun (_,_,i1) (_,_,i2) -> ExportTrace.compare_tac_interestingness i1 i2)
          (mk_full_rec()::records) in
      let new_records = rev (tl (rev new_records)) in
      Hashtbl.replace logs tactic_name new_records
    end;;
```

對照：

- `if ExportTrace.is_goal_too_large ...`：第 [1] 步，目標太大就不記。
- `| None ->`：這個 tactic 第一次出現，做一筆加進去（算第 [2] 步）。
- `if List.length records < ExportTrace.max_num_records`：第 [2] 步，還沒滿就加。
- `else if ExportTrace.all_tac_records_interesting records`：第 [3] 步，全都夠短就不動。
- `else begin ... end`：第 [4] 步。`List.sort` 按排名分數由短到長排序；`rev (tl (rev ...))` 是「反轉、去掉第一個、再反轉回來」，等於**去掉最後一個（最長的）**。

排序和丟棄的邏輯一行都沒改，改的只有 `mk_full_rec` 裡引數的那一格。

### 4.4 第三處：寫檔時才兌現欠條

```diff
-      List.iteri (fun i ((r:ExportTrace.tac_record),(r_args:ExportTrace.record_args),_) ->
+      List.iteri (fun i ((r:ExportTrace.tac_record),r_args_lazy,_) ->
+          (* Render arguments only after this record has survived retention. *)
+          let r_args:ExportTrace.record_args = Lazy.force r_args_lazy in
```

這段在 `exptrace_dump` 裡，也就是整份證明跑完後的第 [5] 步。`List.iteri` 對清單裡每一筆紀錄做一次後面的事。

- 改之前：直接把第 2 個欄位取名 `r_args`，它本來就是印好的文字。
- 改之後：先把第 2 個欄位取名 `r_args_lazy`（欠條），再用 `Lazy.force` 兌現，得到的結果仍然取名 `r_args`、型別也一樣是 `record_args`。

因為名字和型別都和以前一樣，後面把 `r_args.names`、`r_args.values` 等寫進 JSON 的幾十行程式完全不用改。

新註解的意思是：「只有在這筆紀錄撐過保留規則之後，才把引數轉成文字。」

### 4.5 第四處：原本那行註解

```diff
-  (* Separate record_args to lazily evaluate this (otherwise it takes too long) *)
+  (* Keep record_args separate so tactic records can render them lazily. *)
```

新的意思是：「把 `record_args` 分開放，讓 tactic 紀錄可以延遲轉成文字。」把原作者的意圖改寫成符合新程式的描述。這一行是在核心 commit `c388c96` 裡改的，另外三行新註解在 `9f33164`。

### 4.6 沒有改的地方：conversion

`exptrace_add_conv`（conversion 的版本）還是原樣，做紀錄時立刻印引數：

```ocaml
  let mk_full_rec() = (re, re_arg_gen(), mk_i()) in
```

### 4.7 改前改後，四種情況對照

| 情況 | 改之前 | PR #1 之後 |
|---|---|---|
| [1] 目標太大 | 不記，不印 | 一樣 |
| [2] 清單還沒滿 | 做紀錄，**立刻印引數** | 做紀錄，引數存成欠條 |
| [3] 已滿且都夠短 | 不記，不印 | 一樣 |
| [4] 已滿且有長的 | 做紀錄，**立刻印引數**，排序，丟最長的 | 做紀錄，引數存成欠條，排序，丟最長的 |
| [5] 寫檔 | 複製之前印好的文字 | 對留下來的每一筆 `Lazy.force`，這時才印 |

被丟掉的紀錄，它的欠條從頭到尾沒被兌現，所以一次都不會印。回到相機的比喻：只沖洗放進相簿的那些。

---

## 5. 這樣改安全嗎

### 5.1 留下的紀錄為什麼不會變

決定留哪幾筆，只看排名分數（做之前目標的結論長度），**從來不看引數**。PR #1 沒有碰排名分數、排序、丟棄任何一行，只改變引數「什麼時候」被印，所以留下的紀錄必定是同一批。引數最後是由同一個 `re_arg_gen` 印出來的，只是晚一點印。

### 5.2 實測結果

下游 s2n-bignum 實驗，放寬設定，每個數字都是單次執行（出自 tracing-overhead.md，PR #1 的說明也引用了同一組數字）：

| 證明 | 改動前 | PR #1 之後 | 輸出比對 |
|---|---:|---:|---|
| `mldsa_caddq` | 1,549 秒 | **639 秒**（快 2.4 倍） | 414 個 trace 檔全部逐位元組相同 |
| `bignum_mux` | 160 秒 | 162 秒 | 352 個 trace 檔全部逐位元組相同 |

參考：`mldsa_caddq` 完全不做 trace 是 203 秒。

`bignum_mux` 沒有變快是預期中的：它是純量運算的小證明，證明狀態小，而且 49 個填滿清單的 tactic 中有 41 個最後都落在「全部夠短」的狀態，很少走到第 [4] 步。160 對 162 這種幾秒的差距，在單次量測裡沒有意義。

### 5.3 其他驗證

- PR #1 的說明：用 OCaml 5.4 建好 `tracer` 和 `types_test`，把上游原有的 tactic 與 conversion 範例跑完整流程，產生的 trace 和 `examples/*.answer`（預先存好的標準答案）比對，兩組都一致。
- PR #2 的專門測試（第 6 節）：2026-09-22 在本機以 `make HOLLIGHT_DIR=$HOME/hol-light test-lazy-tactic-args` 重跑，通過，約 10 秒。

### 5.4 範圍：只改 tactic

conversion 的引數仍然是立刻印。在 `mldsa_caddq` 上，所有 conversion 記錄加起來花 172 秒，比 tactic 的問題小很多。conversion 要不要比照辦理，留給之後另外討論。

### 5.5 已知風險：印的「時間點」不同了

HOL Light 把式子印成文字時，會依照**印的當下**的顯示設定。證明進行到一半，這些設定是可以改的：

- `override_interface`：讓某個常數改用另一個符號顯示。s2n-bignum 的 `x86/proofs/instruction.ml` 第 413 行有 `override_interface("%", Register)`，之後 `Register` 會印成 `%`（依 tracing-overhead.md 的紀錄）。
- `parse_as_infix`：讓某個函式改成寫在兩個引數中間（像 `a + b` 這樣）。s2n-bignum 的 `common/` 底下有幾處這種宣告。

所以可能出現這種情況：某個 tactic 在設定改變**之前**被記錄，引數裡剛好有受影響的常數。

- 改之前：引數在 tactic 執行當下印，用的是舊設定。
- PR #1 之後：引數在證明結束時印，用的是新設定，文字可能不一樣。

目前兩個證明比對下來完全相同，但這只是**證據，不是保證**：每個證明最後留下哪些紀錄都不一樣，只比過兩個，不能推論所有證明都沒事。這是 PR #1 維持 draft 的原因之一，讓上游審查者先判斷這個取捨能不能接受、需不需要更多驗證。

---

## 6. PR #2 在改什麼

### 6.1 概觀

| commit | 改了什麼 |
|---|---|
| `3fcf21d` Test lazy tactic argument rendering | 新增 `tests/lazy_tactic_args.ml`；`Makefile` 加上測試 target；`.gitignore` 忽略測試產生的檔案 |
| `ca05028` Document the lazy argument regression test | `README.md` 加 5 行說明 |
| `c5dab00` Keep the lazy regression fixture bounded | 讓測試資料的大小固定，不隨上限變大（見 6.4 節） |
| `f1af563` Explain the lazy argument regression test | 在測試檔、`Makefile`、`.gitignore`、`README.md` 加上白話註解與範圍說明 |

（hash 是 2026-09-22 force-push 之後的值，之後再 force-push 會改變。）

PR #2 沒有再改任何 trace 的實作，只加測試、建置設定和文件。

### 6.2 測試的想法：簽到簿

要證明「引數沒有太早被印」，得能**看得到**印引數的函式什麼時候被執行。測試的做法：

1. 準備一本**簽到簿**（`forced_args`）。
2. 用假的「印引數函式」取代真的，每個假函式有自己的名字（label），**一被執行就在簽到簿上簽名**，而且不做任何昂貴的事。
3. 直接呼叫 `exptrace_add_tac` 和 `exptrace_dump`，在每個階段檢查簽到簿。

測試檔是 `tests/lazy_tactic_args.ml`，下面逐段讀。

### 6.3 逐段讀測試

**第一段：簽到簿和假的印引數函式**

```ocaml
(* Verify that tactic argument rendering is deferred until trace dumping. *)

unset_jrh_lexer;;
open ExportTrace;;

let test_tactic_name = "__lazy_tactic_args_test__";;

(* This list makes argument rendering observable without doing expensive work. *)
let forced_args = ref [];;

let make_args label () =
  forced_args := label :: !forced_args;
  {
    names = [label];
    types = ["test"];
    values = [label];
    exprs = [label];
  };;
```

- `unset_jrh_lexer` / 後面的 `set_jrh_lexer`：切換 HOL Light 對 OCaml 語法的特殊讀法，`exportTrace.ml` 自己也在開頭和結尾做同樣的切換。細節不影響理解測試。
- `test_tactic_name`：取一個不可能和真 tactic 撞名的假名字。
- `forced_args` 就是簽到簿。`ref []` 是一個「可以改內容的盒子」，一開始裝空清單。
- `make_args label ()`：被執行時，先把 `label` 加到簽到簿最前面（`forced_args := label :: !forced_args`），再回傳一組假引數。
- 小技巧：`make_args "某名字"` 只給第一個輸入時，得到的是一個「還差一個 `()` 才會執行」的函式，型別剛好就是 `exptrace_add_tac` 要的 `re_arg_gen`。

**第二段：做假紀錄的工具**

```ocaml
let make_record_from_term n term =
  {
    definition_line_number = ("lazy_tactic_args.ml",n);
    user_line_number = ("lazy_tactic_args.ml",n);
    goal_before = ([],term);
    goals_after = [];
    num_subgoals = 0;
  };;

let test_max_num_records = ExportTrace.max_num_records;;
let test_tac_logs = ExportTrace.tac_logs;;
let test_all_tac_records_interesting = ExportTrace.all_tac_records_interesting;;
```

- `make_record_from_term` 做一筆假紀錄：做之前的目標沒有前提（`[]`），結論是給定的 `term`；做之後沒有目標。
- `test_max_num_records` 直接讀 `exportTrace.ml` 裡的上限。上游是 20，放寬版是 100，測試會自動配合。這一點和 6.5 節有關。

**第三段：做出「很長的結論」**

```ocaml
set_jrh_lexer;;

let rec nested_conj n =
  if n = 0 then `T`
  else mk_conj (`T`,nested_conj (n - 1));;

let make_record n = make_record_from_term n (nested_conj n);;
```

- 在 HOL Light 裡，反引號包起來的 `` `T` `` 是邏輯上的「真」。`mk_conj` 做出「且」（HOL Light 寫成 `/\`）。
- `nested_conj n` 做出「T 且 T 且 …… 且 T」，共有 n 個「且」。n 越大，印出來的結論越長。
- `make_record n`：一筆結論深度為 n 的假紀錄。

**第四段：把名額填滿，檢查「加入時沒印」**

```ocaml
let retained_labels =
  List.init test_max_num_records (fun i -> "retained-" ^ string_of_int i);;

(* Reuse one fixed goal so the fixture stays small if the record limit grows. *)
let retained_record = make_record 50;;

List.iteri
  (fun _ label ->
    exptrace_add_tac test_tactic_name retained_record (make_args label))
  retained_labels;;

(* Adding records must not render arguments, even for records being retained. *)
assert (!forced_args = []);;
assert
  (not
    (test_all_tac_records_interesting
      (Hashtbl.find test_tac_logs test_tactic_name)));;
```

- `retained_labels` 是 `"retained-0"`、`"retained-1"`……共 `max_num_records` 個名字。
- `retained_record` 是**一筆**深度 50 的假紀錄，所有要留下的紀錄都共用它。
- 迴圈呼叫 `exptrace_add_tac` 共 `max_num_records` 次，每次配一個不同名字的假印引數函式。跑完後這個假 tactic 的清單剛好滿了。
- **第一個 `assert`**：簽到簿必須是空的。也就是說，做紀錄、加進清單的時候，一個引數都沒被印。
- **第二個 `assert`**：清單「不是全部夠短」。這確認深度 50 的結論印出來確實 ≥ 100 字元，所以下一筆進來時會走第 [4] 步（排序並丟棄），而不是被第 [3] 步略過。

**第五段：送一筆一定會被丟掉的候選**

```ocaml
(* All retained goals exceed the interestingness cutoff, so this candidate is
   compared with them and then discarded as the longest goal. *)
let dropped_label = "dropped";;
exptrace_add_tac test_tactic_name (make_record 200) (make_args dropped_label);;
assert (!forced_args = []);;
```

- 深度 200 的結論比留下的每一筆（深度 50）都長。它會走第 [4] 步：和清單一起排序，然後因為最長而被丟掉。
- `assert`：簽到簿仍然是空的。在改動前的程式裡，這一步的 `mk_full_rec()` 會先執行 `"dropped"` 的印引數函式，再把它丟掉，這正是 PR #1 要消除的浪費。

**第六段：寫檔**

```ocaml
let dump_dir = Filename.temp_file "tactictrace-lazy-args-" ".outdir";;
Sys.remove dump_dir;;
exptrace_dump dump_dir;;
```

`exptrace_dump` 會自己建立目錄，所以需要一個「保證沒人用過、目前也不存在」的名字。`Filename.temp_file` 會建一個名字獨一無二的暫存檔，馬上刪掉，就得到一個空出來的名字。

**第七段：檢查「寫檔時剛好印一次」**

```ocaml
(* Dumping renders each retained record once and never renders the discarded
   candidate. *)
assert (List.length !forced_args = test_max_num_records);;
List.iter
  (fun label ->
    assert (List.length (List.filter ((=) label) !forced_args) = 1))
  retained_labels;;
assert (not (List.mem dropped_label !forced_args));;
```

三個檢查：

1. 簽到簿上的簽名總數 = 留下的紀錄數。
2. 每個 `"retained-i"` 剛好出現**一次**：每筆留下的紀錄都有印，而且沒有重複印。
3. `"dropped"` 從沒出現：被丟掉的那筆從頭到尾沒印過。

**第八段：清理**

```ocaml
Sys.remove (Filename.concat dump_dir (test_tactic_name ^ ".json"));;
Sys.rmdir dump_dir;;
```

把剛寫出來的 JSON 和目錄刪掉，不留垃圾。

### 6.4 如果有人把 PR #1 改回去，測試抓得到嗎

抓得到。改動前的程式在第四段第一次呼叫 `exptrace_add_tac` 時就會執行 `re_arg_gen()`，簽到簿不再是空的，第一個 `assert` 就會失敗。

2026-09-22 在本機做過一次「故意改壞」的檢查（mutation check）：把 `lazy (re_arg_gen())` 換成 `Lazy.from_val (re_arg_gen())`。`Lazy.from_val` 的型別一樣是欠條，但裡面的 `re_arg_gen()` 在包起來**之前**就執行了，等於模擬改動前「立刻印」的行為。結果測試在第一個 `assert` 失敗，程式以 exit code 2 結束。

### 6.5 為什麼測試資料要「bounded」（commit `c5dab00`）

這個 commit 前後的差別：

```diff
+let retained_record = make_record 50;;
+
 List.iteri
-  (fun i label ->
-    exptrace_add_tac test_tactic_name (make_record (50 + i)) (make_args label))
+  (fun _ label ->
+    exptrace_add_tac test_tactic_name retained_record (make_args label))
   retained_labels;;
```

- **改之前**：第 i 筆紀錄的深度是 50 + i，每筆都不同。上限 20 時最深 69，上限 100 時最深 149。上限越大，測試做出來的式子就越深、越多。
- **改之後**：所有留下的紀錄共用同一筆深度 50 的紀錄，不管上限多少都一樣大。（`(fun _ label -> ...)` 裡的 `_` 表示不再需要編號 i。）

為什麼要這樣改？PR #2 的說明寫的是：在把保留上限設得很大的下游環境裡，原本的寫法會造成異常的記憶體和 stack 用量。

- stack（堆疊）是程式處理「一層套一層」的結構時，用來記住「做到哪一層」的空間。式子套得太深，這個空間就會用光，程式當掉。
- 測試直接讀 `exportTrace.ml` 裡的上限（6.3 節第二段），所以下游如果把上限調得很大，測試做出來的式子也跟著變深。本專案早期的 tutorial 證明就用過 `max_num_records = 10000`（依 tracing-overhead.md）。

另外，從程式碼可以推出第二個問題（這點是我讀程式推論的，PR 說明沒有寫，也沒有實際跑過）：舊寫法下如果上限超過 150 左右，會有留下的紀錄深度達到或超過 200，那筆深度 200 的 `"dropped"` 就不再是最長的，也就不會被丟掉，第七段的檢查會因為測試本身的設計而失敗。改成固定深度 50 之後，這個問題也一併消失。

### 6.6 `Makefile` 的修改

```diff
 TEST_OUTPUTS = $(TESTS:.ml=.outdir)
+LAZY_TACTIC_ARGS_TEST = tests/lazy_tactic_args.native
```

定義一個變數：測試程式編譯好之後的執行檔路徑。

```diff
-test: $(TEST_OUTPUTS)
+test: $(TEST_OUTPUTS) test-lazy-tactic-args
 	HOLLIGHT_DIR=$(HOLLIGHT_DIR) ./check-answers.sh
```

`make test` 原本只跑範例並比對標準答案，現在多依賴一個 target `test-lazy-tactic-args`，所以跑 `make test` 會順便跑新測試。

修改後的其餘部分（含 `f1af563` 加的註解）：

```make
# This fixture calls the trace API directly, so it can observe exactly when an
# argument generator runs without going through the AST instrumentation.
test-lazy-tactic-args: $(LAZY_TACTIC_ARGS_TEST)
	./$(LAZY_TACTIC_ARGS_TEST) > tests/lazy_tactic_args.hollog

# Build one HOL Light program containing both the trace code and the fixture.
tests/lazy_tactic_args_wrapped.ml: exportTrace.ml tests/lazy_tactic_args.ml
	{ \
	  echo 'open Hol_lib;;'; \
	  echo 'open Hol_loader;;'; \
	  cat exportTrace.ml; \
	  cat tests/lazy_tactic_args.ml; \
	} > $@

$(LAZY_TACTIC_ARGS_TEST): tests/lazy_tactic_args_wrapped.ml
	$(HOLLIGHT_DIR)/hol.sh compile $< -o tests/lazy_tactic_args.cmx
	$(HOLLIGHT_DIR)/hol.sh link tests/lazy_tactic_args.cmx -o $@
```

由下往上看，這是三道串起來的食譜：

1. **`tests/lazy_tactic_args_wrapped.ml`**：把兩行 `open`、`exportTrace.ml` 全文、測試檔全文，依序接成一個檔案。這樣測試就能直接使用 `exptrace_add_tac` 等函式。
2. **`tests/lazy_tactic_args.native`**：用 HOL Light 的 `hol.sh compile` 和 `hol.sh link` 把上面那個檔案編譯成可以直接執行的程式，做法和原本的範例一樣。
3. **`test-lazy-tactic-args`**：執行那個程式，輸出存到 `tests/lazy_tactic_args.hollog`。任何一個 `assert` 失敗，程式就會以錯誤結束，`make` 也就回報失敗。

第一段註解的意思：「這個測試直接呼叫 trace 的函式，所以能精確觀察印引數函式什麼時候被執行，不必經過 AST instrumentation。」補充說明：正常流程中，TacticTrace 會用 `tracer` 把證明檔的程式碼解析成樹狀結構（AST，抽象語法樹），再自動插入記錄用的程式碼（2.9 節的插樁）。測試跳過這一整段，自己呼叫 `exptrace_add_tac`，自己提供假的印引數函式，才能裝上簽到簿。

第二段註解的意思：「建出一個同時包含 trace 程式碼和測試資料的 HOL Light 程式。」

最後，`clean`（清掉所有建置產物的 target）加了一行，刪除測試產生的檔案；`.PHONY` 加上 `test-lazy-tactic-args`，告訴 `make` 這是一個動作名稱，不是一個檔案：

```diff
+	rm -f tests/lazy_tactic_args_wrapped.ml tests/lazy_tactic_args.cm* tests/lazy_tactic_args.o tests/lazy_tactic_args.hollog $(LAZY_TACTIC_ARGS_TEST)
 
-.PHONY: all clean test
+.PHONY: all clean test test-lazy-tactic-args
```

### 6.7 `.gitignore` 的修改

`.gitignore` 列出「git 不要追蹤的檔案」。編譯和執行測試會產生中間檔，這些不該被提交進 repo：

```
# Files created when the focused lazy-argument test is compiled and run.
tests/*_wrapped.ml
tests/*.cm*
tests/*.hollog
tests/*.native
tests/*.o
```

第一行註解（`f1af563` 加的）的意思是：「編譯並執行這個延遲引數測試時產生的檔案。」下面五行是 `3fcf21d` 加的：接起來的原始檔、編譯中間檔、執行紀錄、執行檔、目的檔。

### 6.8 `README.md` 的修改

在「Testing」一節，`make test` 的說明後面加了一段（前四行是 `ca05028`，最後一句是 `f1af563` 補的）：

> It also runs a focused regression test for lazy tactic argument rendering. The test checks that arguments are not rendered while records are added, retained arguments are rendered once during the dump, and a discarded candidate is never rendered. It covers tactic records only; conversion argument rendering remains eager and is covered by the existing conversion answer tests.

中文：「它也會執行一個針對『延遲轉換 tactic 引數』的專門回歸測試。測試檢查：加入紀錄時不會轉換引數；寫檔時留下來的引數各轉換一次；被丟掉的候選永遠不會被轉換。它只涵蓋 tactic 紀錄；conversion 的引數仍然是立刻轉換，由原有的 conversion 標準答案測試涵蓋。」

---

## 7. 為什麼拆成兩個 PR、目前狀態

### 7.1 為什麼拆

- **審查比較好做。** PR #1 只改一個檔案，審查者可以單獨判斷「這個核心改動對不對、第 5.5 節的風險能不能接受」，不必同時看測試和建置設定。
- **測試依賴 PR #1。** 測試檢查的就是 PR #1 的行為，沒有 PR #1，它一定會失敗（第 6.4 節）。所以 PR #2 疊在 PR #1 上面，是一組 stacked PR。
- **一開始提的是三個 PR**：核心修改／測試加 Makefile／README。但 README 那部分只有 5 行，獨立成一個 PR 不划算，就併進 PR #2，最後定為兩個。

### 7.2 為什麼兩個 PR 的 base 都是 `main`

照理說，PR #2 應該以 PR #1 的分支為 base，這樣 GitHub 只會顯示 PR #2 自己的修改。但 PR 的 base 必須是**上游 repo 裡的分支**，而 PR #1 的分支 `perf/lazy-tactic-arguments` 只存在於 fork，上游沒有。所以 PR #2 只能也以 `main` 為 base。

後果：

- **現在**：GitHub 上 PR #2 的 diff 包含 PR #1 的兩個 commit，顯示 6 個 commit、5 個檔案，其中 `exportTrace.ml` 其實是 PR #1 的。
- **PR #1 合併之後**：要看上游用哪一種方式合併。
  - **一般的 merge commit**：那兩個 commit 原封不動進了 `main`，GitHub 會自動把它們從 PR #2 的顯示中拿掉，PR #2 就縮成只剩自己的 4 個 commit、4 個檔案。
  - **squash 或 rebase**：`main` 裡放的是內容相同但 hash 不同的新 commit，GitHub 認不出它們是同一批修改，PR #2 仍會顯示 `exportTrace.ml` 的修改。這時要把 PR #2 自己的 4 個 commit 接到新的 `main` 上，再 force-push：

    ```bash
    git fetch origin
    git rebase --onto origin/main perf/lazy-tactic-arguments perf/lazy-tactic-arguments-tests
    git push --force-with-lease fork perf/lazy-tactic-arguments-tests
    ```

  上游 `main` 目前的 7 個 commit 都是直接 push 的，還沒有任何 PR 被合併過（2026-09-22 查），所以還不知道他們會用哪一種方式。兩個 PR 的說明都寫「GitHub 會自動拿掉」，其實只在第一種情況成立。

### 7.3 目前狀態（2026-09-22）

| | PR #1 | PR #2 |
|---|---|---|
| 狀態 | open，draft | open，draft |
| base | `main` | `main` |
| GitHub 顯示的 commit | 2 | 6（2 個是 PR #1 的 + 4 個自己的） |
| GitHub 顯示的檔案 | 1：`exportTrace.ml` | 5（含 PR #1 的 `exportTrace.ml`）；自己的是 `tests/lazy_tactic_args.ml`、`Makefile`、`.gitignore`、`README.md` |
| 為什麼還是 draft | 第 5.5 節的印表設定風險，等審查者判斷，可能需要更多驗證 | 等 PR #1 先合併 |

小出入：PR #1 的說明寫「one commit and one changed file」，但它實際上有兩個 commit（第二個 `9f33164` 只加註解）。檔案確實只有一個。

另外，PR #2 的說明提到：在目前這種 repo 沒有放在 `$HOLLIGHT_DIR/TacticTrace` 底下的配置中，本機跑原有的標準答案比對時，差異只在記錄下來的路徑；上游的 CI 使用標準配置，不受影響。

---

## 8. 自己動手看

以下指令都只讀資料，不會改動 repo。repo 在 `/home/tong-nong/TacticTrace`。

**看 PR #1 有哪些 commit、改了什麼：**

```bash
git -C /home/tong-nong/TacticTrace log --oneline origin/main..perf/lazy-tactic-arguments
git -C /home/tong-nong/TacticTrace diff origin/main...perf/lazy-tactic-arguments
git -C /home/tong-nong/TacticTrace show c388c96    # 核心修改
git -C /home/tong-nong/TacticTrace show 9f33164    # 只加註解
```

**看修改後完整的 `exportTrace.ml`**（`exptrace_add_tac`、`all_tac_records_interesting`、`exptrace_dump` 都在裡面）：

```bash
git -C /home/tong-nong/TacticTrace show perf/lazy-tactic-arguments:exportTrace.ml
```

**只看 PR #2 自己的修改**（不含 PR #1 的部分）：

```bash
git -C /home/tong-nong/TacticTrace log --format='%h %s' perf/lazy-tactic-arguments..perf/lazy-tactic-arguments-tests
git -C /home/tong-nong/TacticTrace diff perf/lazy-tactic-arguments...perf/lazy-tactic-arguments-tests
```

**看 GitHub 目前顯示的 PR #2**（含 PR #1 的 commit）：

```bash
git -C /home/tong-nong/TacticTrace diff origin/main...perf/lazy-tactic-arguments-tests
```

**讀測試檔：**

```bash
git -C /home/tong-nong/TacticTrace show perf/lazy-tactic-arguments-tests:tests/lazy_tactic_args.ml
```

兩個點和三個點的差別：

- `A..B`（用在 `log`）：列出「B 有、A 沒有」的 commit。
- `A...B`（用在 `diff`）：從 A 和 B 的共同祖先算起，B 這邊改了什麼。GitHub 的 PR diff 就是這樣算的。

**看 PR 的說明文字和狀態**（網頁：<https://github.com/hol-light/TacticTrace/pull/1>、<https://github.com/hol-light/TacticTrace/pull/2>）：

```bash
curl -s https://api.github.com/repos/hol-light/TacticTrace/pulls/1 | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["title"], d["draft"]); print(d["body"])'
curl -s https://api.github.com/repos/hol-light/TacticTrace/pulls/2/commits | python3 -c 'import json,sys; [print(c["sha"][:7], c["commit"]["message"].splitlines()[0]) for c in json.load(sys.stdin)]'
```

**實際跑測試**：需要和 `make test` 一樣的 HOL Light 環境（以 `HOLLIGHT_USE_MODULE=1` 建置），並用 `HOLLIGHT_DIR` 指向它。2026-09-22 用的指令：

```bash
make HOLLIGHT_DIR=$HOME/hol-light test-lazy-tactic-args
```

會在 `tests/` 底下產生編譯產物，這些都已被 `.gitignore` 忽略。`make clean` 可以清掉它們，但也會一併清掉 `tracer` 等其他建置產物。
