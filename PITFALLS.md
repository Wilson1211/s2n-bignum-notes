# s2n-bignum + HOL Light 踩坑記錄

2026-09-04 ～ 09-07，Ubuntu 22.04.5 / x86_64 實作過程中實際撞到的問題。
每一條都是**真的發生過**並且找到原因的，不是預防性提醒。

搭配 [README.md](README.md) 使用：README 是「怎麼做」，這份是「做不下去的時候查什麼」。

## 本機環境（判斷某條坑適不適用你）

| 項目 | 值 |
|---|---|
| CPU | AMD Ryzen 7 7735U (8C/16T)，有 BMI2/ADX/AVX2/SHA-NI，**無** AVX-512 |
| RAM | 14 GB |
| `/tmp` | **獨立分割區，只有 3.7 GB** ← 造成多個坑 |
| `/home` | 370 GB |
| 系統 OCaml | `/usr/bin/ocaml` 4.13.1（apt） |
| opam OCaml | `~/.opam/4.14.2` ← 實際使用的 |
| hol-light | git clone，commit `b19af69`（s2n-bignum CI 釘選版） |
| s2n-bignum | **shallow clone**（只有 1 個 commit） |

標記說明：🌍 = 任何人都會遇到　🖥️ = 本機環境特有

---

# A. 建置與效能量測

## A1. 🌍 `make CC=clang` 不會換掉組譯器

**症狀**：想用 clang 建置，`make CC=clang` 看起來成功了，但實際上還是 GNU as 在組譯。

**原因**：`CC` 只用在 C 前置處理階段。真正的組譯器變數是 `ASSEMBLE`（預設 `as`）。

**解法**：

```bash
make ASSEMBLE="clang -c -x assembler"
```

## A2. 🌍 「`_alt` 版本在新 CPU 上比較慢」是錯的

一般說法是 `_alt` 給沒有 BMI2/ADX 的舊 CPU 用，新機器上會比較慢。**SHA-3 是反例**：

```
sha3_keccak4_f1600_alt   345.0 ns
sha3_keccak4_f1600       425.3 ns   ← 非 alt 反而慢 19%
```

因為 SHA-3 的 `_alt` 用的是**不同的向量化策略**，不是「退化版指令序列」。

**結論**：`_alt` 只代表「另一種指令序列」，快慢要實測，不要照抄通則。

## A3. 🌍 Benchmark 不是「several minutes」

上游文件說跑完要 several minutes。**實測 1 小時 50 分鐘**（397 個測項）。

要快速看個大概就縮短重複次數，或只測特定前綴。

---

# B. HOL Light 安裝

## B1. 🌍 `opam install hol_light` 不夠

`tools/build-proof.sh` 不是只呼叫 `hol.sh`，它從 `hol.sh` 的**所在目錄**反推 `HOLLIGHT_DIR`，然後直接伸手進去拿檔案：

```bash
export HOLLIGHT_DIR="$(dirname ${hol_sh_cmd})"
[ ! -f "${HOLLIGHT_DIR}/hol_lib.cmxa" ] && exit 1
ocaml ${HOLLIGHT_DIR}/inline_load.ml ...
ocamlopt.byte -I "${HOLLIGHT_DIR}" ...
```

它需要一個**完整的原始碼樹**（`hol_lib.cmxa` + `inline_load.ml` + `hol_loader.ml` 在同一層），不是裝好的執行檔。

**解法**：`git clone https://github.com/jrh13/hol-light.git ~/hol-light` 然後自己編。

## B2. 🌍 一定要 `HOLLIGHT_USE_MODULE=1`

預設 `make` 只給你 REPL，不會產生 `hol_lib.cmxa`（可連結的函式庫）。

```bash
cd ~/hol-light
make switch-5          # 或用既有的 opam switch
eval $(opam env)
HOLLIGHT_USE_MODULE=1 make
```

沒有 `hol_lib.cmxa` 的話 `build-proof.sh` 第 22 行就直接擋下來。

## B3. 🌍 版本不合 → 錯誤訊息完全誤導

**症狀**：

```
Exception: Failure "x86/tutorial/bignum.ml"
make: *** [Makefile:547: tutorial/bignum.native] Error 2
```

只有檔名，沒有真正的原因。

**原因**：`inline_load.ml:65` 把例外吃掉了：

```ocaml
let fail_if_nonexistent f x = try f x with _ -> failwith x in
```

**怎麼挖出真正的錯誤**：做一份拆掉遮罩的副本。**副本必須放在 `~/hol-light`**，因為 `#use "hol_loader.ml"` 是相對於腳本所在目錄解析的。

```bash
cd ~/hol-light
sed 's/let fail_if_nonexistent f x = try f x with _ -> failwith x in/let fail_if_nonexistent f x = f x in/' \
    inline_load.ml > inline_load_debug.ml
# 然後手動照 build-proof.sh 的方式呼叫 inline_load_debug.ml
```

我的實際案例：真正的例外是 `Not_found`，來自 `x86/proofs/base.ml:24` 的 `loadt "Library/records.ml";;` ——
當時的 hol-light 版本還沒有 `Library/records.ml` 這個檔案。

**解法**：checkout 到 CI 釘選的 commit：

```bash
cd ~/hol-light
git fetch origin
git checkout b19af6934759eed622d7aca25092367f81656eee
make clean && HOLLIGHT_USE_MODULE=1 make
```

（釘選版本寫在 `~/s2n-bignum/.github/workflows/ci.yml` 的 `HOLLIGHT_COMMIT`。）

## B4. 🌍 ⚠️ 判斷版本新舊前一定要先 `git fetch`

**這是我自己犯的錯，記錄下來警惕。**

我看到 `git cat-file -t b19af69...` 在本地失敗，就下結論說「你的版本比 CI 還新」。

**完全相反** —— 那個 commit 只是**還沒被 fetch 下來**。實際上本地版本落後 48 個 commit。

```bash
# 錯誤做法：直接查本地
git cat-file -t <commit>          # 失敗 ≠ 比較新

# 正確做法
git fetch origin
git rev-list --count HEAD..<commit>   # 你落後幾個 commit
git rev-list --count <commit>..HEAD   # 你超前幾個 commit
```

`A..B` 是「B 可達但 A 不可達」的集合。兩個方向都算一次才知道真正的前後關係。

---

# C. 跑證明（`make proofs`）

## C1. 🌍 目標路徑一定要帶子目錄

**症狀**：

```
$ make bignum_montmul_p256.correct
make: *** No rule to make target 'bignum_montmul_p256.correct'.  Stop.
```

**原因**：規則是

```make
.SECONDEXPANSION:
%.native: proofs/$$(*F).ml $(BASE_ML) %.o %.obj
```

`$(*F)` 是 stem 的**檔名部分**（所以證明腳本可以平鋪在 `proofs/`），但 `%.o` 沒有 `F`，必須在**同一路徑**找到。而 `.o` 在子目錄裡。

**解法**：

```bash
make p256/bignum_montmul_p256.correct
```

## C2. 🖥️ `/tmp` 只有 3.7 GB，會被塞爆

`build-proof.sh` 用 `mktemp` 產生暫存檔。**151 個證明就吃掉 3.2 GB**（平均 20 MB，最大 52 MB）。342 個跑完尖峰要 7 GB 以上。

正常情況每編完一個會自己 `rm`，但只要中途被 kill 或 OOM，殘留就會累積。

**解法**：`mktemp` 遵守 `TMPDIR`，改指到 `/home`：

```bash
mkdir -p ~/tmp
cd ~/s2n-bignum/x86
TMPDIR=$HOME/tmp make -j1 proofs
```

**清理殘留**（只刪自己的、只刪 build-proof 的樣式）：

```bash
find /tmp -maxdepth 1 -type f -name 'tmp.*' \
     \( -name '*.ml' -o -name '*.cmi' -o -name '*.o' \) \
     -user "$(id -un)" -delete
```

**編譯階段結束後 `~/tmp` 就可以清了** —— `run-proof.sh` 不產生暫存檔。

## C3. 🌍 執行階段 Stack overflow

**症狀**：`.native` 全部編完後，一進入執行階段第一個大證明就掛：

```
../tools/run-proof.sh "curve25519/curve25519_ladderstep.native" ...
Fatal error: exception Stack overflow
make: *** [Makefile:501: curve25519/curve25519_ladderstep.correct] Error 2
```

**原因**：`build-proof.sh:57` 有設大 stack：

```bash
OCAMLRUNPARAM=l=2000000000
```

但 **`l=` 只對 bytecode 直譯器有效**。`.native` 是原生碼，用系統 stack，只認 `ulimit -s`（預設 8192 KB）。而 `run-proof.sh` 完全沒設。

這就是為什麼編譯 342 個都沒事，一執行就爆。

**解法**：

```bash
ulimit -s unlimited        # 硬上限本來就是 unlimited，不用 sudo
make -j1 proofs
```

## C4. 🌍 失敗的 `.correct` 會被 make 當成已完成

延續 C3：證明爆掉後，`run-proof.sh` 已經把（不完整的）輸出寫進 `.correct` 了，而 make **沒有刪掉它**。

```bash
$ make -n curve25519/curve25519_ladderstep.correct
make: 'curve25519/curve25519_ladderstep.correct' is up to date.   ← 陷阱
```

不處理的話，重跑會**靜靜跳過**這個失敗的證明，你最後拿到一份少一個的結果卻沒有任何警告。

**怎麼辨認假的 `.correct`**：看結尾。真正通過的長這樣：

```
Running time: 161.000000 sec, Start unixtime: ..., End unixtime: ...
```

失敗的會斷在計算中間（例如 `687 basis elements and 175595 critical pairs`）。

**解法**：續跑前先刪掉：

```bash
rm curve25519/curve25519_ladderstep.correct
```

## C5. 🌍 所有 `.native` 編完才會開始跑

```make
build_proofs: $(PROOF_BINS);
run_proofs:   build_proofs $(PROOF_LOGS);
proofs:       run_proofs ; ../tools/count-proofs.sh .
```

`build_proofs` 是 `run_proofs` 的前置條件，所以 **342 個 `.native` 全部編完之前，一個 `.correct` 都不會產生**。

看到 `.correct` 數量長時間掛零是正常的，不是當掉。判斷是否還活著要看 CPU 時間和 RSS，不要看 log。

## C6. 🌍 分母是 342 不是 352

```
x86/proofs/*.ml     352 個
make 的 PROOF_BINS   342 個   ← 真正的分母
```

有 10 個 `.ml` 沒有對應的 `.o`。要拿正確數字：

```bash
make -f Makefile -f <(printf 'print-%%:\n\t@echo $($*)\n') print-PROOF_BINS | tr ' ' '\n' | grep -c native
```

（tutorial 也有類似狀況：`safety.ml` 沒有對應的 `.S`。）

## C7. 🌍 靜默階段怎麼確認還活著

`ocamlopt` 編譯大證明時完全不輸出。tail log 會以為當掉了。

```bash
P=$(pgrep -f 'ocamlrun.*ocaml-hol' | head -1)
ps -o pid,etime,time,rss --no-headers -p $P
sleep 10
ps -o pid,etime,time,rss --no-headers -p $P
```

`TIME` 欄在增加 = 正在算。`RSS` 在長 = 正在載入。兩個都不動 = 真的閒置。

記憶體要注意：實測有個 162 KB 的證明腳本讓 `ocamlopt` 吃到 **3.57 GB**，而最大的腳本有 770 KB。14 GB RAM 跑 `-j2` 以上要小心。

## C8. 🌍 shallow clone 讓 git log 失去意義

```bash
$ git log --oneline -- x86/proofs | wc -l
1
```

因為 `.git/shallow` 存在，本地只有 1 個 commit。**不要用 `git log` 判斷證明的作者或年代**。要真實歷史：

```bash
git fetch --unshallow
```

---

# D. 互動模式與 VSCode

## D1. 🖥️ `ledit` 讓 `hol.sh` 直接崩潰

**症狀**：

```
$ ./hol.sh
Fatal error: cannot load shared library dllunix
Reason: ~/.opam/4.14.2/lib/ocaml/stublibs/dllunix.so: undefined symbol: caml_atfork_hook
```

**原因**：跟 HOL Light 無關。

```
/usr/bin/ledit  →  #!/usr/bin/ocamlrun     系統 OCaml 4.13.1
CAML_LD_LIBRARY_PATH → ~/.opam/4.14.2/...  opam OCaml 4.14.2
```

`ledit` 用 4.13.1 的 runtime，卻被 opam 的環境變數導去載 4.14.2 的 `dllunix.so`，
而 `caml_atfork_hook` 是 4.14 才加的符號。

單獨跑 `ledit echo hi` 也會炸。`hol.sh:59-61` 預設用 ledit，所以被牽連。

**解法**（擇一）：

```bash
export LINE_EDITOR=rlwrap    # rlwrap 是 C 寫的，沒有 OCaml 版本問題
opam install ledit           # 或裝一個 4.14.2 版的蓋掉 /usr/bin/ledit
```

## D2. 🌍 cwd 必須是 s2n-bignum 根目錄

`load_path` 的第一項是 `.`（當前目錄），所以 `needs "x86/proofs/base.ml"` 是相對於 cwd。
在 `x86/` 底下啟動會變成找 `x86/x86/proofs/base.ml`。

**解法**：寫一個 wrapper 一次解決 D1 + D2：

```bash
cat > ~/hol-light/hol-s2n.sh <<'EOF'
#!/bin/bash
export LINE_EDITOR=rlwrap
cd "$HOME/s2n-bignum" || exit 1
exec "$HOME/hol-light/hol.sh" "$@"
EOF
chmod +x ~/hol-light/hol-s2n.sh
```

VSCode 擴充的 `hol-light.exePaths` 就指向這個。

## D3. 🌍 載入 `base.ml` 要 5 分 44 秒

```
REPL 冷啟動（載 hol.ml）        58 秒
needs "x86/proofs/base.ml"    344 秒
────────────────────────────────────
從零到可以開始證明            6 分 42 秒
```

實測 `401.57s user / 99% cpu` —— 完全單執行緒，多核幫不上忙。

**實務含義**：REPL 開了就不要關。改檔案重送 statement 就好，不要重啟。

想省掉的話 HOL Light 有 DMTCP checkpoint（`make-checkpoint.sh`），但要 `sudo apt install dmtcp`。

## D4. 🌍 REPL 沒有連結 `Unix` / `Thread`

```ocaml
Unix.time();;    (* Error: Reference to undefined global `Unix' *)
Thread.self();;  (* Error: Unbound module Thread *)
```

但編譯出來的 `.native` **有**（`build-proof.sh:60` 的 `-package zarith,unix -linkpkg`）。

所以 `build-proof.sh` 樣板裡的計時：

```ocaml
let s2n_bignum_build_proof_start_time = Unix.time();;
```

**只在編譯路徑成立**。互動模式要計時請用 `Sys.time()`（Stdlib 內建）。

## D5. 🌍 順序式，不是位置式

REPL 只有**一個當前狀態**，由你送了什麼、什麼順序決定。游標移到第 90 行**不代表**狀態在第 90 行。

跳著送的典型後果：

```
Error: Unbound value SOME_FLAGS
```

（`SOME_FLAGS` 定義在 `x86/proofs/x86.ml:3902`，要靠 `base.ml:59` 載進來。）

跟 Lean 4 的差別：Lean 的 server 增量 elaborate 整份檔案，維護每個位置的狀態，游標移到哪就顯示哪。
HOL Light 的檔案**是一支 OCaml 程式**，沒辦法「只重算第 90 行」。

比較貼切的比喻是 Jupyter notebook：cell 要照順序跑，跳著跑會進到不一致的狀態，而它不會阻止你。

## D6. 🌍 goal 顯示被型別標註淹沒

```ocaml
print_types_of_subterms := 0;;   (* printer.ml:154 *)
p();;
```

`0` = 不印型別，`1`（預設）= 有推導出的型別變數時才印，`2` = 全印。

## D7. 🌍 擴充只關聯 `.hl`，不認 `.ml`

**症狀**：`Alt+E` 完全沒反應，也不報錯。

**原因**：

```
languages:  id: hol-light-ocaml   extensions: ['.hl']
alt+e  when: editorTextFocus && editorLangId == hol-light-ocaml
```

`.ml` 被當成 Plain Text 開，`when` 條件不成立。

**解法**：狀態列語言模式 → `HOL Light`，或執行 `HOL Light: Associate .ml Files with HOL Light`，
或設定 `"files.associations": { "*.ml": "hol-light-ocaml" }`。

## D8. 🌍 沒有 `when` 的使用者 keybinding 會蓋掉擴充

使用者自訂 keybinding 優先權高於擴充預設值。一條沒有 `when` 的規則**永遠命中**。

**解法**：給自己的規則加排除條件，而不是刪掉：

```json
{ "key": "alt+e", "command": "workbench.action.showAllEditors",
  "when": "editorLangId != hol-light-ocaml" }
```

`editorLangId != ...` 在非 HOL Light 檔案、以及焦點不在編輯器時都成立，所以原本的行為不受影響。

## D9. 🖥️ ⭐ AutoKey 在 X11 層攔截，VSCode 根本收不到

**這是最難查的一個，前面 D7/D8 都修好了還是沒反應。**

**症狀**：`Alt+G` 有反應，`Alt+E` 和 `Alt+L` 完全沒有。

**原因**：AutoKey 用 X11 keyboard grab，在應用程式**之前**攔截。

```
<alt>+e  →  cut          ← 搶走
<alt>+l  →  GoForward    ← 搶走
<alt>+g  →  (沒設定)      ← 所以只有這個能用
```

「只有 Alt+G 能用」就是最關鍵的線索 —— 一個鍵能用代表語言模式和 VSCode 設定都對，
那另外兩個一定是被更外層的東西吃掉了。

**解法**：AutoKey 每個項目都有視窗過濾器，把 VSCode 加進排除清單。

```
~/.config/autokey/data/My Phrases/.cut.json
~/.config/autokey/data/My Phrases/.GoForward.json
```

```diff
- "regex": "^(?!Terminal$)(?!.*Gnome-terminal).+$"
+ "regex": "^(?!Terminal$)(?!.*Gnome-terminal)(?!.*Code).+$"
```

（VSCode 的 `WM_CLASS` 是 `code` / `Code`，標題是 `... - Visual Studio Code`，`(?!.*Code)` 兩者都涵蓋。）

改完要**重啟 AutoKey**才生效：

```bash
pkill -f autokey-gtk && autokey-gtk &
```

**代價**：VSCode 裡就沒有這些 Emacs 式操作了。其他應用程式完全不受影響。

### 本機最終的放行清單

同樣的改法要套六次。改完的完整清單（`grep -l Code ~/.config/autokey/data/My\ Phrases/.*.json` 可驗證）：

```
<alt>+d   deleteCharForward
<alt>+e   cut
<alt>+j   GoBack
<alt>+l   GoForward
<alt>+n   pagedown
<alt>+o   pageup
```

### HOL Light 快捷鍵在本機的最終狀態

| 鍵 | 功能 | 曾被什麼擋住 |
|---|---|---|
| `Alt+E` | Send Statement | AutoKey `cut` |
| `Alt+A` | 送游標前所有 statement | — |
| `Alt+G` | Set Goal | — |
| `Alt+L` | Execute Tactic | AutoKey `GoForward` |
| `Alt+M` | 多行 tactic | VSCode `gotoLine`（加 `when` 條件） |
| `Alt+N` | 多行 tactic，游標不動 | AutoKey `pagedown` |
| `Alt+R` | Select Tactic | — |
| `Alt+O` | Rotate Subgoals | AutoKey `pageup` |
| `Alt+B` | 退一步 | — |
| `Alt+P` | 印目前 goal | VSCode `quickOpen`（加 `when` 條件） |
| `Alt+D` | Remove Highlighting | **AutoKey `deleteCharForward` + VSCode `deleteRight`（兩層）** |
| `Alt+J` | Jump to Highlighted | AutoKey `GoBack` |
| `Alt+S` | Search Theorems | — |
| `Alt+C` | 送 ^C 中斷 | — |

`Alt+D` 是唯一被兩層同時擋住的——先解 VSCode 的 `when` 條件還是沒用，
因為 AutoKey 在更外層。**這正是 D8 修完仍然無效的原因**，順序是：
先確認事件有沒有進到 VSCode（用下面的萬用診斷），再往內層查。

### 完整還原

```bash
tar xzf ~/autokey-backup-<時間戳>.tar.gz -C ~/.config
pkill -f autokey-gtk && autokey-gtk &
```

（每次修改前都會先 `tar czf ~/autokey-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C ~/.config autokey`。）

### 查不出來時的萬用診斷

```
Ctrl+Shift+P → Developer: Toggle Keyboard Shortcuts Troubleshooting
```

之後每次按鍵都會記錄到 Output 面板：

| Output | 意義 |
|---|---|
| 沒有 `Received keydown` | 被更外層攔截（AutoKey / 輸入法 / WM） |
| 有 keydown，`No keybinding entries matched` | `when` 條件不成立 |
| 有 keydown，`matched hol-light.*` | 指令有觸發，問題在擴充內部 |

## D10. 🌍 goal 側欄需要 Server，不是讀終端機輸出

**症狀**：一切正常，但 goal 側欄永遠空白，所有輸出只出現在終端機。

**原因**：擴充的 readme 明講 **The goal view requires an active HOL Light server**。
側欄不是靠解析終端機文字，而是靠一個跑在 REPL 裡的 JSON server（`ocaml/server2.ml`）。

**解法**：

```
Ctrl+Shift+P → HOL Light: Start Server
```

（或點右下角狀態列的 `Start Server`。）

- server 起在**現有的 REPL 裡面**，`base.ml` 和目前的 goal 全部保留，不用重跑 6 分鐘
- 會多開一個 `HOL Light (client)` 終端機，之後指令走它
- 額外好處：送出的 statement 會依成功/失敗塗成淡綠 / 淡紅

**驗證 server 真的起來了**：

```bash
ss -ltnp | grep 2012
# LISTEN 127.0.0.1:2012  users:(("ocaml-hol",pid=...,fd=3))
```

**注意**：`server2.ml` 需要 `Unix` 和 `Thread`（見 D4），你**手動 loadt 會失敗**。
擴充會自己先送 `#directory` + `#load "unix.cma"` + `#load "threads.cma"`，所以要用它的指令。

### server 的生命週期（實測踩過兩次）

server 不是獨立行程，它跑在**主 REPL 裡面**（`ss -ltnp` 會看到 `users:(("ocaml-hol",pid=<REPL的pid>,fd=3))`）。所以：

| 動作 | 後果 |
|---|---|
| 關掉 **client** 分頁 | server 停止 → 側欄死掉，但 REPL 和 `base.ml` 還在 |
| 關掉 **主 REPL** 分頁 | 全部消失 → 628 MB 狀態沒了，重建要 6 分 42 秒 |
| 開新的 REPL session | **server 不會自動跟過來，要重跑 `Start Server`** |

**症狀**：一切照做但側欄就是不更新 —— 先查 `ss -ltnp | grep 2012`，沒有 LISTEN 就是 server 沒開。

**建議順序**：`New REPL` → **`Start Server`** → 才載 `base.ml`。
提前開的好處是載入階段就有淡綠/淡紅回饋，而且 server 起不來會立刻發現，不會白等 6 分鐘。

完整的操作流程見 [README.md](README.md) 步驟 5b。

## D11. 🌍 `Alt+G` 選取範圍要剛好

擴充把選取內容包成 `g( ... );;`。選多了就會變成：

```
    CONV_TAC WORD_RULE);;);;
                       ^^
Parse error: [and_let_binding] expected after [first_let_binding]
```

選取必須**剛好**是反引號到反引號（不含後面的逗號）。

term 裡如果有 `//` 註解，自動偵測常常失敗，得用滑鼠精確選取 —— 或者乾脆直接在終端機打 `g \`...\`;;`。

## D12. 🖥️ 每次執行 tactic 畫面就跳到終端機分頁

**原因**：`terminal.integrated.defaultLocation: "editor"` 讓終端機變成編輯器分頁，
擴充呼叫 `terminal.show()` 揭示終端機時就把當前分頁切走了。（鍵盤焦點沒被搶，只是畫面被蓋。）

**解法**：把 `HOL Light client` 分頁**拖到編輯器右半邊**自成群組。

```
┌──────────────┬──────────────┬──────────┐
│  simple.ml   │  HOL Light   │  Goal    │
│              │  client      │  側欄     │
└──────────────┴──────────────┴──────────┘
```

`show()` 只會在右邊群組裡切換，左邊的檔案不動。不用改設定，三樣東西同時可見。

（或改 `"terminal.integrated.defaultLocation": "view"` 放回底部面板，但會影響所有終端機習慣，
而且現有的終端機不會自動搬家。）

---

# E. 關鍵數字速查

| 項目 | 數值 |
|---|---|
| Benchmark 全跑 | 1 小時 50 分（397 測項） |
| REPL 冷啟動 | 58 秒 |
| `needs "x86/proofs/base.ml"` | 5 分 44 秒（單執行緒） |
| 單一證明執行（p256 montmul） | 161 秒 |
| 一個 `.native` 大小 | 約 24 MB |
| 151 個證明的 `/tmp` 用量 | 3.2 GB |
| x86 證明腳本 | 352 個 / 596,292 行 |
| x86 組語 `.S` | 343 個 / 215,277 行 |
| 證明 : 組語 行數比 | **2.8 : 1** |
| x86 語意模型 | 11,152 行（`decode.ml` 3,525 + `x86.ml` 6,435 + `instruction.ml` 635 + `elf.ml` 557） |

---

# F. 互動證明的最小指令集

快捷鍵是**擴充**的慣例，換編輯器就不一樣。真正跨平台通用的是 HOL Light 自己的 REPL 指令（`tactics.ml`）：

| 指令 | 功能 | 擴充預設鍵 |
|---|---|---|
| `g \`...\`;;` | 設定 goal | `Alt+G` |
| `e (TACTIC);;` | 執行一個 tactic | `Alt+L` |
| `b();;` | 退回上一步 | `Alt+B` |
| `p();;` | 重印目前 goal | `Alt+P` |
| `r n;;` | 輪換 subgoal | `Alt+O` |
| `top_thm();;` | 取出證好的定理 | — |

**寫文件請用左邊這組。** 快捷鍵只是把這些字串貼進終端機的自動化。

離開 REPL：`#quit;;` 或 Ctrl+D。
