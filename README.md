# s2n-bignum 上手筆記

實際在本機（Ubuntu 22.04 / x86_64 / gcc 11.4 / binutils 2.38）跑通的完整流程。
上游 repo：<https://github.com/awslabs/s2n-bignum>

> **先搞清楚一件事**：s2n-bignum 是**函式庫**，不是可執行程式。
> 所謂「跑起來」＝ 建出 `libs2nbignum.a` → 跑單元測試 → 從 C 程式呼叫它。
> 沒有 `./s2n-bignum` 這種東西可以執行。

### 這份筆記包含的檔案

| 檔案 | 用途 |
|---|---|
| **README.md**（本檔） | 怎麼做 —— 從 clone 到形式驗證的完整流程 |
| **[PITFALLS.md](PITFALLS.md)** | **做不下去的時候查什麼** —— 實際撞到並找到原因的 28 個坑 |
| `demo.c` | 從 C 呼叫 libs2nbignum.a 的可執行範例 |
| `bench-ryzen7735u.log` | 本機 benchmark 完整輸出（397 個測項） |

> 🔧 **卡住了就先翻 [PITFALLS.md](PITFALLS.md)。**
> 那裡面每一條都標了 🌍（任何人都會遇到）或 🖥️（本機環境特有），
> 並且寫成「症狀 → 原因 → 解法」，可以直接用症狀去搜。
>
> 最容易踩到的幾個：`make` 目標少了目錄前綴、執行證明時 stack overflow、
> `/tmp` 空間不足、`ledit` 版本衝突導致 `hol.sh` 崩潰、VSCode 快捷鍵沒反應。

---

## 0. 環境需求

只需要基本的 C 工具鏈，**不用裝任何額外套件**：

```bash
uname -m          # 要是 x86_64 或 aarch64
gcc --version     # 或 clang
as --version      # GNU assembler (binutils)
make --version
```

已驗證可用：gcc 11.4.0、GNU as 2.38、GNU Make 4.3。

---

## 1. Clone 與建置

```bash
git clone https://github.com/awslabs/s2n-bignum.git
cd s2n-bignum
```

**x86_64 機器：**

```bash
(cd x86 && make -j$(nproc))
```

**ARM 機器（aarch64 / Apple Silicon）：** 把 `x86` 換成 `arm` 即可，其餘完全一樣。

```bash
(cd arm && make -j$(nproc))
```

建置產物：

| 檔案 | 說明 |
|---|---|
| `x86/libs2nbignum.a` | 整包靜態函式庫（約 1.7 MB） |
| `x86/generic/bignum_add.o` 等 | 每個函式一個 `.o`，要細粒度連結時用 |

建置過程是把每個 `.S` 丟給 C preprocessor，再用 `tr ';' '\n'` 拆成一行一條指令，最後交給 `as`。
（有些 assembler 不吃「一行多條指令」，所以才要那個 `tr`。）

---

## 2. 跑單元測試

```bash
(cd tests && make go)
```

預期最後一行：

```
All 374 tests run, all passed
```

過程中會看到 `Testing <function> with 100 cases`，涵蓋：

- 各函式對照「概念簡單但慢」的 C 參考實作（虛擬亂數輸入）
- 1900 個 P-384 的 known-value 測試
- X25519 / Ed25519 對照 TweetNaCl

### 測試的其他用法

```bash
cd tests
make test                        # 只編譯出 ./test，不執行

./test bignum_montmul_p256       # 只測單一函式，會印出每筆 OK
./test +500                      # 每個函式跑 500 筆（預設 100）
./test +100 | grep -v OK         # 只看標題行，等同 make go

make complete                    # 500 筆 + 不過濾輸出 + 有 return code（適合 CI）
```

> `make complete` 會走 `ctCheck`（用 valgrind 檢查 constant-time 行為）。
> 本機目前**沒裝 valgrind**，需要的話：`sudo apt install valgrind`。

---

## 3. 從 C 呼叫（重點）

介面全部宣告在 `include/s2n-bignum.h`——這也是最快瀏覽「有哪些函式可用」的地方。

同目錄的 `demo.c` 是已驗證可跑的範例，做兩件事：
1. 4-word（256-bit）大數乘法 `bignum_mul`
2. X25519 `curve25519_x25519_byte`，並比對 RFC 7748 測試向量

編譯與執行（假設 repo 在 `~/s2n-bignum`）：

```bash
cd ~/s2n-bignum
gcc -O2 -I include ~/s2n-bignum-notes/demo.c x86/libs2nbignum.a -o /tmp/demo
/tmp/demo
```

預期輸出：

```
(2^256-1)*3 = 0000...0002fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffd
X25519    = c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552  -> 符合 RFC 7748 ✓
```

也可以用 `-L` / `-l` 的寫法：

```bash
gcc -O2 -I include ~/s2n-bignum-notes/demo.c -L x86 -ls2nbignum -o demo
```

### 呼叫慣例的幾個坑

- 所有數字都是 **little-endian 的 `uint64_t` 陣列**（`bignum_...` 系列），
  低位在 `a[0]`。位元組介面的函式名稱通常帶 `_byte` 或 `..._bytes_...`。
- 帶 `_alt` 後綴的版本是**替代實作**，數學結果完全相同，只是用不同指令組合。
  對 bignum 類函式，`_alt` 通常是給沒有 BMI2/ADX 的舊 CPU 用的，在新機器上比較慢
  （實測見第 4 節）。但這不是通則——SHA-3 的 `_alt` 是不同的向量化策略，
  在這台機器上反而**比較快**。要用哪個請以自己機器的 benchmark 為準。
- 函式名稱含 `VARIABLE_TIME` 的**不是** constant-time（例如 `mlkem_rej_uniform_VARIABLE_TIME`），
  不要拿去處理祕密資料。哪些函式不保證 constant-time 列在 repo 根目錄的 `non_ct_functions.txt`。

---

## 4. 效能量測（benchmark）

### 怎麼跑

```bash
(cd benchmarks && make go)
```

第一次會先把 `benchmark.c` 編譯起來並連結 `../x86/libs2nbignum.a`。

⏱️ **會跑很久**。上游 README 說「several minutes」，但在這台筆電上實測是
**約 1 小時 50 分鐘**（397 個測項，每項 325 萬次呼叫，且 governor 是 `powersave`）。
務必用 `nohup` 或背景執行，並導到檔案再慢慢看：

```bash
cd benchmarks
make benchmark                  # 只編譯，不執行
./benchmark | tee bench.log     # 邊跑邊存檔
```

跟 `tests` 一樣，`benchmarks/Makefile` 會用 `uname -m` 自動決定去 `../x86` 還是 `../arm` 找函式庫。

### 只測特定函式（開發時最實用）

```
用法：./benchmark [-reps] [function_name]
```

```bash
./benchmark bignum_add            # 前綴比對，測所有 bignum_add* 
./benchmark bignum_mul_           # 測所有 bignum_mul_* 
./benchmark -10000 bignum_add     # 指定 inner 重複次數為 10000
./benchmark -                     # 印出用法說明
```

`function_name` 是**前綴比對**，所以 `./benchmark bignum_montmul_p256` 會同時測到
`bignum_montmul_p256` 和 `bignum_montmul_p256_alt`——這正是比較快慢版本的好方法。

### 怎麼讀結果

每行長這樣：

```
bignum_add (4x4->4)             :     2.4 ns each (var  7.0%, corr  0.03) =  423949909 ops/sec
```

| 欄位 | 意義 | 方向 |
|---|---|---|
| `ns each` | 每次呼叫平均奈秒數 | **越小越好** |
| `var` | 變異係數（標準差／平均），跨 bit density 的百分比 | 越小越好 |
| `corr` | 執行時間與輸入 bit density 的**相關係數** | **越接近 0 越好** |
| `ops/sec` | 每秒操作數 = 10⁹ ÷ 平均時間 | 越大越好 |

函式名稱括號裡的是尺寸，例如 `bignum_add (32x32->32)` 表示兩個 32-word 輸入、32-word 輸出。
泛型函式會用好幾種尺寸各測一次。

預設重複次數 = **5（outer）× 65（bit densities）× 10000（inner）= 3,250,000 次**。

結尾會給兩個總結數字：
- `ARITHMEAN`：所有函式平均時間的**算術平均**
- `GEOMEAN`：**幾何平均**——跨數量級差異很大的資料用這個比較有意義

### var / corr 為什麼比速度重要

這才是這份 benchmark 真正的重點。s2n-bignum 的設計原則是 constant-time：
**執行的指令序列與記憶體存取樣式，不能隨被處理的數值而變**。

測法是：對每個 0～64 的「bit density」（每個 64-bit word 平均有幾個 1 bit）
分別產生虛擬亂數輸入並各自計時，然後算出時間與 bit density 的變異係數和相關係數。

- `corr` 接近 0 → 執行時間與資料內容無關，符合 constant-time 預期
- `corr` 明顯偏離 0、`var` 偏大 → 值得追查，但**不一定**是真的洩漏

⚠️ 重要：數字不好看**不等於**有 timing side-channel。上游文件明講，偏差也可能來自
平台雜訊或計時框架本身的誤差。在筆電上尤其如此（見下方我的實測說明）。
真正要檢查 constant-time 要用 valgrind：`(cd tests && make complete)`。

### 清理

```bash
(cd benchmarks && make clean)
```

---

## 4b. 本機實測結果（2026-09-04）

完整輸出存在同目錄的 **`bench-ryzen7735u.log`**（443 行）。

**測試環境**

| 項目 | 值 |
|---|---|
| CPU | AMD Ryzen 7 7735U（Zen 3+，8C/16T，400–4819 MHz） |
| 指令集 | BMI2 ✓、ADX ✓、AVX2 ✓、SHA-NI ✓、**AVX-512 ✗** |
| governor | `powersave` ← **筆電降頻，絕對數字會偏低且不穩** |
| 耗時 | 約 1 小時 50 分鐘 |

> 因為是筆電 + `powersave`，**絕對數字不要拿去跟論文或雲端機器比**。
> 有意義的是**同一次執行內函式之間的相對比較**。

**總結**

```
ARITHMEAN (397 tests)    : 21791.7 ns      ← 被 bignum_modexp 之類的極端值拉高
GEOMEAN   (397 tests)    :    35.5 ns      ← 這個比較有代表性
```

### 高階密碼運算（一次完整操作的成本）

| 函式 | ns/call | ops/sec |
|---|---:|---:|
| `curve25519_x25519base`（產生公鑰） | 5,774 | 173,192 |
| `edwards25519_scalarmulbase`（Ed25519 簽章用） | 5,756 | 173,747 |
| `p256_scalarmulbase` (block size 6) | 7,576 | 132,004 |
| `curve25519_x25519`（ECDH 共享祕密） | 19,704 | 50,750 |
| `edwards25519_scalarmuldouble`（Ed25519 驗章用） | 26,552 | 37,662 |
| `sm2_montjscalarmul` | 31,618 | 31,627 |
| `p256_scalarmul` | 34,435 | 29,040 |
| `p384_montjscalarmul` | 116,391 | 8,592 |
| `p521_jscalarmul` | 190,325 | 5,254 |

直觀換算：X25519 金鑰交換約 **20 µs**，P-521 純量乘法約 **190 µs**——差了快 10 倍。

### 底層運算（單位是奈秒）

| 函式 | ns/call |
|---|---:|
| `bignum_add_p256k1` | 1.6 |
| `bignum_add_p256` / `_sm2` / `_p25519` | 1.8 |
| `bignum_add (4x4->4)` | 2.4 |
| `mlkem_mulcache_compute` | 3.3 |
| `bignum_montmul_p256` | 9.9 |
| `bignum_montmul_p384` | 23.7 |
| `bignum_montmul_p521` | 33.5 |
| `mlkem_ntt` | 43.4 |
| `mldsa_ntt` | 150.2 |
| `sha3_keccak_f1600` | 226.2 |

### `_alt` 版本的實測差異

這台機器**有** BMI2/ADX，所以 bignum 類的 `_alt` 一律較慢：

| 函式 | 一般版 | `_alt` | `_alt` 慢多少 |
|---|---:|---:|---:|
| `bignum_montmul_p256` | 9.9 | 13.1 | +32% |
| `bignum_montmul_p384` | 23.7 | 28.4 | +20% |
| `bignum_montmul_p521` | 33.5 | 44.4 | +33% |
| `curve25519_x25519` | 19,704 | 23,931 | +21% |
| `p256_scalarmul` | 34,435 | 40,264 | +17% |
| `p521_jscalarmul` | 190,325 | 236,577 | +24% |

**但 SHA-3 相反**：

| 函式 | ns/call |
|---|---:|
| `sha3_keccak4_f1600` | 425.3 |
| `sha3_keccak4_f1600_alt` | **345.0**（快 19%） |

所以「`_alt` 比較慢」不是通則，要以自己機器的實測為準。

### corr 欄位抓到了什麼（最有意思的部分）

絕大多數函式的 `corr` 都在 ±0.3 以內，符合 constant-time 預期。**兩個明顯的例外**：

```
mlkem_rej_uniform_VARIABLE_TIME (1200 bytes):  71.8 ns  (var 39.0%, corr  0.89)
mldsa_rej_uniform                           :  36.7 ns  (var 17.2%, corr  0.61)
```

`corr 0.89` 表示執行時間與輸入資料的 bit density **高度相關**——時間洩漏了資料內容。

**這不是 bug，是設計如此**：函式名稱裡的 `VARIABLE_TIME` 就是在明講這件事。
rejection sampling 本質上就是「不合格就重抽」，迴圈次數必然取決於資料。
它們用在 ML-KEM／ML-DSA 中處理**公開**資料（從種子展開矩陣）的地方，所以沒問題。

這組數字剛好示範了 benchmark 的 `corr` 欄位確實能反映真實的資料相依性——
可以拿它當作 sanity check 的基準線。哪些函式不保證 constant-time，權威清單在 `non_ct_functions.txt`。

### 32 個測項顯示 `*** NOT APPLICABLE ***`

這是**正常的**，不是錯誤。代表該函式在目前平台上不適用，兩種情況：

1. **ARM 專屬**：`aes_xts_encrypt`/`decrypt`、`sha3_keccak2_f1600`、
   `sha3_keccak_f1600_alt` 等需要 ARM 的 SHA3／AES 擴充指令
2. **x86 上未提供該變體**：部分 `mldsa_*`（`mldsa_decompose_*`、`mldsa_chknorm`、
   `mldsa_polyz_unpack_*`、`mldsa_rej_uniform_*_VARIABLE_TIME`）、
   `bignum_copy_row_from_table_*`、`bignum_emontredc_8n_cdiff`

在 ARM 機器上跑會看到不同的子集被標成 NOT APPLICABLE。

### 自己複製這些數字

```bash
cd ~/s2n-bignum/benchmarks
make benchmark

# 快速比較 alt vs 非 alt（前綴比對，幾秒鐘就好）
./benchmark bignum_montmul_p256
./benchmark curve25519_x25519

# 縮短重複次數，快速看個大概
./benchmark -1000 bignum_montmul

# 完整重跑並存檔（很久）
nohup ./benchmark > bench.log 2>&1 &

# 從 log 撈出最慢的 10 個
awk -F: '/ns each/{split($2,a," ");printf "%12.1f  %s\n",a[1],$1}' bench.log | sort -rn | head -10

# 撈出 |corr| 偏大的（可能有資料相依性的）
awk -F'corr' '/ns each/{split($2,a,")");c=a[1]+0;if(c>0.4||c<-0.4){split($0,n,":");printf "%6.2f  %s\n",c,n[1]}}' bench.log
```

---

## 5. 形式驗證（HOL Light）——這才是這個 repo 最特別的地方

每個函式都附一份 HOL Light 的機器檢查證明，證明的是「**實際建置出來的 object file**，
在處理器的形式模型上，對**所有輸入**都滿足數學規格」——不是只對測試案例成立。

> 以下步驟**我沒有實際跑過**，是從 repo 的 `.github/workflows/ci.yml`（官方 CI 的權威配方）、
> `tools/build-proof.sh`、`tools/run-proof.sh` 和 `x86/Makefile` 逐條讀出來的。

### 先有心理準備：規模

| 項目 | 數字 |
|---|---|
| 要證明的 spec 數量 | **1758** 條（`x86/proofs/specifications.txt`） |
| 證明腳本數量 | 352 個 `.ml`（`x86/proofs/`，共 31 MB） |
| 最大的證明腳本 | `p384_montjscalarmul_alt.ml`，**789 KB** |
| 跑完全部 | **數小時到數天**，視機器而定 |

⚠️ **這台機器的 RAM 是瓶頸**：總共 14 GB、目前可用約 4 GB。
每個證明是獨立的 OCaml native 程式，大的會吃掉好幾 GB。
**不要用 `make -j16`**，會 OOM。建議從 `-j2` 開始試。

### 步驟 1：安裝系統套件

官方 CI 用的清單（Ubuntu）：

```bash
sudo apt update
sudo apt install libpcre2-dev ocaml libstring-shellquote-perl libgmp-dev xdot
```

這台機器**已經有**：OCaml 4.14.2、camlp5 8.00.04、opam 2.1.2。
但還是建議把上面那行跑過，補齊 `libpcre2-dev` / `libgmp-dev` 等。

### 步驟 2：安裝 / 確認 opam

CI 是裝官方 script 的最新版：

```bash
wget https://raw.githubusercontent.com/ocaml/opam/master/shell/install.sh
chmod +x install.sh
echo "/usr/local/bin" | sh ./install.sh
opam init --disable-sandboxing
```

你已經有 opam 2.1.2 了，可以先直接用；如果後面 `make switch-5` 出問題再回來升級。

> `--disable-sandboxing` 是 CI 在容器裡的做法。在自己的桌機上通常**不需要**關 sandbox，
> 可以先試 `opam init` 就好。

### 步驟 3：編譯 HOL Light（**這步有個關鍵陷阱**）

> 已經裝過 hol-light 的話，先看下面的**步驟 3b**，多半不用重來一次。

```bash
cd ~
git clone https://github.com/jrh13/hol-light.git
cd hol-light

# CI 固定在這個 commit——想跟官方完全一致就 checkout 它
git checkout b19af6934759eed622d7aca25092367f81656eee

make switch-5          # 建立 OCaml 5.x 的 opam switch（裝在 hol-light/_opam）
eval $(opam env)
ocamlc -version        # 確認切過去了
camlp5 -v

HOLLIGHT_USE_MODULE=1 make    # ← 關鍵！
```

🔴 **`HOLLIGHT_USE_MODULE=1` 不能省。**
少了它不會產生 `hol_lib.cmxa`，而 `tools/build-proof.sh` 開頭就在檢查這個檔案：

```
hol_lib.cmxa does not exist in HOLLIGHT_DIR('...').
Did you compile HOL Light with HOLLIGHT_USE_MODULE set to 1?
```

看到這個錯誤就是這步漏了，要回來重編。

> 上游 README 只說「OPAM 版本可能太舊，要裝 GitHub 最新版」，
> 但沒強調 `HOLLIGHT_USE_MODULE=1`——這是從 CI 和 build script 裡才看得到的。
> 另外 CI 跑的是 **Ubuntu 24.04**，你這台是 22.04，`make switch-5` 這步是最可能出狀況的地方。

### 步驟 3b：**如果你已經有一份能用的 hol-light**

先檢查缺的到底是什麼：

```bash
ls -l ~/hol-light/hol_lib.cmxa
```

- **有** → 環境已經可用，直接跳到步驟 4
- **沒有** → 你八成是用預設的 `make` 編的（`HOLLIGHT_USE_MODULE` 預設是 `0`），
  `hol.sh` 互動模式會正常，但 s2n-bignum 的證明編不起來

⚠️ **不用重新 clone，也不用 `make switch-5`**，但**一定要先確認版本夠新**（見下）。

#### 先做版本檢查（這步不能跳，實測踩過）

s2n-bignum 的 `x86/proofs/base.ml` 會 `loadt "Library/records.ml"`。
這個檔案是 HOL Light **後來才加入**的，舊版沒有，會導致證明編譯失敗。

```bash
cd ~/hol-light
ls Library/records.ml || echo ">>> HOL Light 太舊，必須更新 <<<"
```

🔴 **不要用「我的 commit 日期比較新／`git cat-file` 找不到 CI 那個 commit」來判斷版本新舊。**
本地 clone 沒有 fetch 過的話，本來就找不到較新的 commit，看起來會像是「你的比較新」——
實測就是這樣誤判的。正確做法是先 fetch 再比：

```bash
cd ~/hol-light
git fetch origin
git log -1 --format='%h %ci' HEAD
git log -1 --format='%h %ci' b19af6934759eed622d7aca25092367f81656eee
git rev-list --count HEAD..b19af6934759eed622d7aca25092367f81656eee   # 落後幾個 commit
```

#### 更新到 CI 釘選版本並重編

```bash
cd ~/hol-light
git fetch origin
git checkout b19af6934759eed622d7aca25092367f81656eee
make clean                      # 換 commit 後一定要清，避免混到舊版產物
HOLLIGHT_USE_MODULE=1 make
```

如果版本已經夠新（`Library/records.ml` 存在），只要補模組模式即可：

```bash
cd ~/hol-light
HOLLIGHT_USE_MODULE=1 make
```

為什麼這樣就夠（`hol-light/Makefile` 的邏輯）：

| 行號 | 內容 |
|---|---|
| 42 | `HOLLIGHT_USE_MODULE?=0` ← 預設關閉，這就是缺 `.cmxa` 的原因 |
| 46 | `default: update_database.ml pa_j.cmo hol.sh` ← 預設只建這些 |
| 156 | 開啟後 `default` 才加上 `hol_lib.cma hol_lib.cmxa unit_tests.byte unit_tests.native` |
| 146 | 開啟後 `hol.sh` 多一個 `hol_lib.cmo` 相依，所以 `hol.sh` 會被重新產生 |
| 132 | 偵測到 OCaml 5.x 或 **4.14** 就用 `hol_4.14.sh` 樣板 ← 4.14.2 是支援的 |

用 `make -n` 可以先確認它打算做什麼再真的跑：

```bash
cd ~/hol-light && HOLLIGHT_USE_MODULE=1 make -n | head -20
```

**兩個副作用要知道：**

1. 你原本的 `hol.sh` 會被覆寫（裡面的 `export HOLLIGHT_USE_MODULE=0` 變成 `1`）。
   互動模式仍然可用，官方 CI 就是這樣跑的。
2. `hol-light/Makefile:36-41` 明講：開啟這個選項會**擴大 trusted base**，
   把 inliner 腳本 `inline_load.ml` 納入信任範圍。對這個以保證性為賣點的專案來說，
   這是有意識的取捨——但這也正是官方 CI 採用的做法。

**需要的相依套件**（用 `ocamlfind list` 確認）：`zarith`、`unix`、`camlp5`，
外加原生編譯器 `ocamlopt`。缺了就回步驟 1 補。

#### 步驟 3d：升級到 latest（或在版本之間切換）

CI 釘選版適合「先把 s2n-bignum 跑起來」，但如果要驗證**最新的 hol-light 跟 s2n-bignum 相不相容**
（或上游有你需要的修正），就得升級。整套流程如下。

##### ① 先記錄目前狀態（回退用）

```bash
cd ~/hol-light
git rev-parse HEAD                      # 存起來，這是你的回退點
git log -1 --format='%h %ad %s' --date=short
ls -la hol.sh hol_lib.cmxa pa_j.cmo ocaml-hol
```

##### ② 確認執行中的 REPL 會受什麼影響

```bash
pgrep -af 'ocaml-hol'
ss -ltnp | grep 2012                    # 有沒有跑著的 goal view server
```

`make clean` 刪掉檔案**不會**影響已在執行的行程（Linux 會保留 inode），
所以載了 `base.ml` 的 REPL 可以繼續用完。但它是**舊版建的**——
要測新版就得關掉重開，代價是再等 6 分 42 秒。

##### ③ 保護未追蹤檔案

```bash
cd ~/hol-light
git status --short                      # ?? 開頭的都是未追蹤
cp hol-s2n.sh /tmp/hol-s2n.sh.bak       # VSCode 啟動器，務必保留
```

`make clean` 不會刪 `hol-s2n.sh`，但先備份不吃虧。

##### ④ 切到 master 並對齊上游

如果你當初是 `git checkout <sha>` 釘版本，現在是 **detached HEAD**——
沒有「目前的分支」，HEAD 直接指向那個 commit，所以不能直接 `git pull`：

```bash
cd ~/hol-light
git status -sb | head -1                # 顯示 "## HEAD (no branch)" 就是 detached
```

先切回分支再拉：

```bash
git checkout master
git pull
```

這是正常情況下該用的做法。本地 `master` 通常從 clone 之後就沒動過，`git pull` 會直接 fast-forward。

**只有在 `master` 上有你自己的 commit 時才需要多想**——那時 `git pull` 會停下來要求 merge 或 rebase，
該怎麼處理由你決定。

> ⚠️ 不要習慣性用 `git checkout -B master origin/master`。
> `-B` 是**強制重設**，master 上若有本地 commit 會被直接丟掉且不提示。
> 它只適合「我確定要放棄本地 master」的情況，不該當預設。

確認：

```bash
git log -1 --format='%h %ad %s' --date=short
git rev-list --count HEAD..origin/master    # 要是 0
```

##### ⑤ 清乾淨再重建

```bash
cd ~/hol-light
eval $(opam env)
make clean
HOLLIGHT_USE_MODULE=1 make
```

🔴 **`make clean` 不能省。** 舊版留下的 `.cmo` / `.cmi` 跟新原始碼混在一起會產生難以理解的錯誤。

🔴 **`HOLLIGHT_USE_MODULE=1` 一樣不能省**，否則不會產生 `hol_lib.cmxa`。

實測 `make clean` + 完整重建約 **1 分 23 秒**（Ryzen 7735U，OCaml 4.14.2）——
比想像中快，因為真正耗時的是 `hol_lib_inlined.ml` 那一次原生編譯。

想留下記錄的話：

```bash
cd ~/hol-light && eval $(opam env)
nohup bash -c 'make clean && time HOLLIGHT_USE_MODULE=1 make' > ~/hol-light-rebuild.log 2>&1 &
tail -f ~/hol-light-rebuild.log
```

##### ⑥ 驗證

```bash
ls -la ~/hol-light/hol_lib.cmxa         # 必須存在，時間戳是剛剛

cd ~/s2n-bignum/x86
make tutorial -j2                       # HOLDIR 預設就是 ~/hol-light
```

`make tutorial` 11/11 全過 = 新版跟 s2n-bignum 相容。

**掛掉的話先查 hol-light 的 commit log**，找有沒有動到 `x86/proofs/base.ml` 載入的檔案。
例如 2026-08-31 的 `745d5ab "Make define_record_type idempotent"` 就動到 `Library/records.ml`，
而 `base.ml:24` 正是 `loadt "Library/records.ml";;`。

```bash
cd ~/hol-light
git log --oneline <舊commit>..HEAD -- Library/ iterate.ml pa_j/
```

##### ⑦ 回退

```bash
cd ~/hol-light
git checkout <步驟①記下的 sha>
make clean && HOLLIGHT_USE_MODULE=1 make
```

s2n-bignum 那邊**不用動**——已經編好的 `.native` 是靜態連結的獨立執行檔，
換 hol-light 不會讓它們失效。只有重新編譯某個 `.native` 時才會用到新的 `hol_lib.cmxa`。

##### 想同時保留兩個版本

不想動現有環境的話，開第二份 clone，用環境變數指定：

```bash
git clone https://github.com/jrh13/hol-light.git ~/hol-light-latest
cd ~/hol-light-latest && eval $(opam env) && HOLLIGHT_USE_MODULE=1 make

cd ~/s2n-bignum/x86
HOLDIR=$HOME/hol-light-latest make tutorial -j2
```

`x86/Makefile:479` 是 `HOLDIR?=$(HOME)/hol-light`，用 `?=` 所以環境變數蓋得掉。
好處是原本的環境完全不動，出事刪掉資料夾就好；代價是多一份磁碟和一次建置時間。

### 3c：確認裝好了 —— 以及**怎麼離開互動模式**

要快速確認 HOL Light 本身沒問題，可以進互動模式看看：

```bash
cd ~/hol-light
./hol.sh
```

載入完（會跑一陣子）之後會停在 `#` 提示符，這是 **OCaml toplevel**，代表 HOL Light 正常。
可以隨手驗一下：

```
# ARITH_RULE `2 + 2 = 4`;;
```

**離開的方法**（三選一）：

| 方式 | 說明 |
|---|---|
| **Ctrl-D** | 送出 EOF，最省事 |
| `#quit;;` | OCaml toplevel 的 directive |
| `exit 0;;` | 直接結束行程 |

三個容易踩到的點：

1. **`#quit;;` 前面那個 `#` 要自己打。** 畫面上會出現兩個 `#`——第一個是提示符，
   第二個是你輸入的。OCaml toplevel 的 directive 都以 `#` 開頭。
2. **結尾的 `;;` 不能省。** OCaml toplevel 要看到它才會開始執行。
3. **Ctrl-C 不會離開**，它只中斷目前正在跑的運算。卡在長時間的證明時可以用它中斷，
   但要退出還是得用上面三種之一。

> 附帶說明：s2n-bignum 的證明流程**完全不走互動模式**。
> 它是用 `tools/build-proof.sh` 把每個證明編成獨立的原生執行檔再跑
> （所以才需要 `hol_lib.cmxa`）。互動模式只用來確認環境是通的，
> 或是自己動手玩 HOL Light 的時候用。

### 步驟 4：設定 HOLDIR

```bash
export HOLDIR=$HOME/hol-light
```

`x86/Makefile` 的預設值就是 `$(HOME)/hol-light`，所以 clone 在家目錄的話其實可以不設。
Makefile 會用 `$(HOLDIR)/hol.sh` 當進入點。

### 步驟 5：**先跑 tutorial**（強烈建議的起點）

不要一開始就攻大函式。repo 附了完整教學，而且 CI 有獨立 job 在跑它：

```bash
cd ~/s2n-bignum/x86
ulimit -s unlimited
make tutorial -j2 2>&1 | tee ~/tutorial.log
```

#### 這條指令每個部分在做什麼

```
make tutorial -j2 2>&1 | tee ~/tutorial.log
└──┬──────────┘ └┬┘ └─┬─┘   └───────┬─────┘
   │             │    │             └ 同時寫到終端機和檔案
   │             │    └ stderr 併入 stdout，一起進管線
   │             └ 同時跑 2 個編譯行程
   └ 用當前目錄的 Makefile 建 tutorial 這個目標
```

##### `make tutorial` —— `tutorial` 是 target，不是資料夾裡的 Makefile

`x86/tutorial/` **沒有** Makefile。你跑的是 `x86/Makefile`，`tutorial` 是它裡面的一個目標：

```make
TUTORIAL_PROOFS = $(wildcard tutorial/*.ml)          # 第 424 行
tutorial/%.native: tutorial/%.ml tutorial/%.o        # 第 547 行
    ../tools/build-proof.sh "$<" "$(HOLLIGHT)" "$@"
```

所以**必須在 `~/s2n-bignum/x86` 底下執行**，進到 `tutorial/` 再跑 `make` 是找不到東西的。

##### `-j2` —— 2 個**行程**，不是 threads

make 不用 thread，它 fork 出獨立行程同時執行不同的 recipe。
所以會有兩個 `build-proof.sh` → 兩個 `ocamlopt` 同時跑。

這個區別在記憶體上很重要：兩個 `ocamlopt` 是**兩份獨立的記憶體空間**，
各自可能吃到 GB 級（實測單一行程曾達 3.57 GB）。14 GB RAM 的機器 `-j2` 是合理上限。

##### `2>&1` —— 順序有意義

```
fd 0 = stdin    fd 1 = stdout    fd 2 = stderr
```

`2>&1` = 把 fd 2 指到「fd 1 **目前**指向的地方」。

| 寫法 | 結果 |
|---|---|
| `make 2>&1 \| tee log` | 管線先建立（fd 1 → 管線），再把 fd 2 指過去 → 兩者都進 tee ✅ |
| `make > log 2>&1` | 同樣正確 ✅ |
| `make 2>&1 > log` | ❌ 此時 fd 1 還是終端機，stderr 留在終端機，只有 stdout 進檔案 |

> 真實案例：`tools/run-proof.sh:24` 就是寫成 `"$native_path" 2>&1 > "$output_path"`，
> 所以證明失敗時 `Fatal error: exception Stack overflow` 跑到 `proofs.log`，
> 而不是 `.correct` 檔裡——找錯誤訊息時會找不到。

##### `tee` —— 名字來自水管的 T 形接頭

一路進，兩路出：

```
                    ┌──→ 終端機（即時看得到）
make 的輸出 ──→ tee ┤
                    └──→ ~/tutorial.log（存檔）
```

沒有它就只能二選一：

```bash
make tutorial -j2                      # 看得到，關掉終端機就沒了
make tutorial -j2 > log 2>&1           # 存下來了，過程中什麼都看不到
make tutorial -j2 2>&1 | tee log       # 兩者兼得 ✅
```

跑五分鐘以上的東西用 `tee` 很值得。加 `-a` 是 append 不覆蓋。

##### `ulimit -s unlimited` —— 只影響當前 shell

**單一行程能用多少 stack 記憶體**，單位 KB。

```
soft (實際生效)  8192 KB = 8 MB     ← 預設，證明跑大的會爆
hard (上限)      unlimited          ← 你能自己調到多高
```

soft 可以自己往上調到 hard 為止，**不用 sudo**。

作用範圍實測：

| 情況 | 結果 |
|---|---|
| 同一個 shell 裡執行的指令 | 繼承 ✅ |
| `nohup ... &` 背景執行 | 繼承 ✅ |
| 關掉 terminal 再開 | **恢復 8192** |
| 重開機 | **恢復 8192** |
| 另開一個 terminal 分頁 | **是 8192**，不會跟著 |

🔴 **所以必須跟 `make` 在同一個 shell。** 在 A 分頁設定、B 分頁跑 make 是無效的，
VSCode 整合終端機每個新分頁都是新 shell。

不建議寫進 `~/.zshrc` ——stack 無上限時，失控的遞迴會一路吃記憶體直到 OOM killer 出手，
而不是乾淨地丟 `Stack overflow`。要常駐的話用有界的大值比較穩：

```bash
ulimit -s 1048576      # 1 GB
```

##### 什麼時候需要 `TMPDIR=$HOME/tmp`

**跑 tutorial 不需要。** 每個證明約產生 16 MB 暫存，11 個約 180 MB，
而 `build-proof.sh` 每編完一個就會自己 `rm` 掉，峰值只有同時進行的那幾個。

需要的是**全套 342 個證明**（見步驟 7）——那會用到 5 GB 以上，
而 `/tmp` 若是獨立分割區（本機只有 3.7 GB）就會塞爆。

`x86/tutorial/` 的內容（多數 `.ml` 配一個同名 `.S`，`safety.ml` 例外，它借用既有的函式）：

**單元推理（unary reasoning）**
1. `simple.ml` — 驗證線性程式的簡單算術性質
2. `sequence.ml` — 把程式切成小塊分別驗證
3. `branch.ml` — 有條件分支的程式
4. `memory.ml` — 操作記憶體的程式
5. `loop.ml` — 有迴圈的程式
6. `bignum.ml` — 為大數程式寫規格並證明
7. `safety.ml` — 驗證安全性質（constant-time + 記憶體安全）

**關係推理（relational reasoning）**
1. `rel_simp.ml` — 證明兩個簡單程式等價
2. `rel_equivtac.ml` — 證明有小差異的兩個程式等價
3. `rel_reordertac.ml` — 證明指令重排後的程式與原程式等價

這組 tutorial 跑得完，代表整套環境是通的。詳見 `x86/tutorial/README.md`。

### 步驟 5b：VSCode 互動模式 —— 一步一步走完 `simple.ml`

`make tutorial` 是一口氣跑完，看不到中間過程。想理解證明**怎麼一步步長出來**，
就要用互動模式：設定一個目標，然後一個動作一個動作把它消掉。

以下用 `x86/tutorial/simple.ml` 當例子。它證的是這兩條指令：

```asm
add  %rax, %rbx      ; rbx = rbx + rax
sub  %rax, %rbx      ; rbx = rbx - rax
```

跑完 `rbx` 回到原值——人一看就知道，但「顯然」不是證明。要交代溢位、
要涵蓋全部 2^64 種輸入，這正是機器檢查該做的事。

#### 一次性設定

**① 啟動器**（避開 `ledit` 版本衝突，並固定 cwd 在 repo 根目錄）

```bash
cat > ~/hol-light/hol-s2n.sh <<'EOF'
#!/bin/bash
export LINE_EDITOR=rlwrap
cd "$HOME/s2n-bignum" || exit 1
exec "$HOME/hol-light/hol.sh" "$@"
EOF
chmod +x ~/hol-light/hol-s2n.sh
```

**② VSCode 設定**（`Ctrl+Shift+P` → `Preferences: Open User Settings (JSON)`）

```json
"hol-light.exePaths": ["/home/<你>/hol-light/hol-s2n.sh"],
"hol-light.path": "/home/<你>/hol-light",
"hol-light.rootPaths": [".", "{hol}", "{workspace}"],
"hol-light.autoIndex": true
```

**③ 擴充**：安裝 `monadius.hol-light-simple`

**④ 檔案關聯**：擴充只認 `.hl`，不認 `.ml`。執行
`HOL Light: Associate .ml Files with HOL Light`，或在狀態列把語言模式切成 `HOL Light`。
**沒切的話所有快捷鍵都會靜默失效**（`when: editorLangId == hol-light-ocaml` 不成立）。

**⑤ 用 `code ~/s2n-bignum` 開整個資料夾**，不是單開一個檔案（`{workspace}` 才解析得出來，
Ctrl+Click 跳定義才會動）。

#### 三個鍵在做什麼（白話）

把 HOL Light 想成一個**很龜毛的助教**，他手上有一張「還沒證完的清單」。
你不能直接給答案，只能一次說一個動作，他照做，然後把新的清單給你看。清單變空就是證完了。

三個鍵就是你跟他對話的三種話：

| 鍵 | 白話 | 對應的 REPL 指令 |
|---|---|---|
| **`Alt+E`** | 「**先把這段讀進去**」 | （直接送出該段原文） |
| **`Alt+G`** | 「**這就是我要你證的東西**」 | ``g `...`;;`` |
| **`Alt+L`** | 「**做這個動作**」 | `e (TACTIC);;` |

**`Alt+E` = 準備材料。**
用在 `needs "..."`、`let simple_mc = ...` 這種**還不是證明**的東西——
載入定義、宣告機器碼、建立工具。助教只是把它記下來，清單不會有任何變化。
擴充以 `;;` 為界，抓游標所在的**整段**（可能跨很多行），送完游標自動跳到下一段。

**`Alt+G` = 出題，整個過程只按一次。**
把游標所在的反引號 term 交給助教，他把它寫成待證清單的第一項。
側欄從這一刻才會出現 `1 subgoal`。
（有選取範圍時送選取的內容，所以選過頭會出錯——見 PITFALLS D11。）

**`Alt+L` = 解題，之後九成時間都在按它。**
抓游標所在的**那一行** tactic 送出去，助教照做並回報新的清單，
然後游標**自動跳到下一行**——所以連按就是一路往下走。
做不到的動作他會拒絕，清單原封不動。

按錯了想回頭：**`Alt+B`**（退一步）、**`Alt+P`**（重印目前清單）。

一句話判斷該按哪個：

> 還沒設 goal → `Alt+E`（準備）或 `Alt+G`（出題）
> 已經有 goal → `Alt+L`（一路按到 `No subgoals`）

#### 每次開工的標準流程

順序**不能跳**——REPL 只有一個當前狀態，由你送過什麼決定，跟游標在第幾行無關。

| # | 動作 | 等待 | 你應該看到 |
|---|---|---|---|
| 1 | `Ctrl+Shift+P` → `HOL Light: New HOL Light REPL Session`，選 `hol-s2n.sh` | 58 秒 | 終端機出現 `#` |
| 2 | `Ctrl+Shift+P` → **`HOL Light: Start Server`** | 數秒 | 多開一個 `HOL Light (client)` 分頁 |
| 3 | `Ctrl+Shift+P` → `HOL Light: Show HOL Light Goals` | — | 側欄出現（此時還是空的） |
| 4 | 第 13 行 `needs "x86/proofs/base.ml";;` → **`Alt+E`** | **5 分 44 秒** | 狂刷 `Searching with limit ...` |
| 5 | 第 22 行 `let simple_mc = new_definition ...` → **`Alt+E`** | 秒回 | 機器碼位元組序列 |
| 6 | 第 41 行 `let EXEC = X86_MK_EXEC_RULE simple_mc;;` → **`Alt+E`** | 秒回 | 兩條指令的解碼定理 |
| 7 | 第 65–82 行反引號 term → **`Alt+G`** | 秒回 | 側欄出現 `1 subgoal` |
| 8 | 第 85 行起每行 tactic → **`Alt+L`** 連按 | 各數秒 | 側欄逐步縮小到 `No subgoals` |

**第 2 步不能省，也不能延後。** goal 側欄是靠一個跑在 REPL 裡的 JSON server 餵資料的，
不是解析終端機文字。沒開 server 側欄永遠空白，所有輸出只會出現在終端機。
提前到第 4 步之前開，好處是從載入階段就有淡綠/淡紅的成功失敗回饋，而且萬一 server 起不來，
在這裡就發現了，不會白等 6 分鐘。

想讓畫面乾淨一點，在終端機先下：

```ocaml
print_types_of_subterms := 0;;
```

#### 第 8 步逐行會看到什麼

| 行 | tactic | 清單怎麼變 |
|---|---|---|
| 85 | `REPEAT STRIP_TAC` | `forall pc a b` 消失，變成固定但任意的值 |
| 88 | `REWRITE_TAC [SOME_FLAGS]` | 展開成 `[CF; PF; AF; ZF; SF; OF]` |
| 90 | `ENSURES_INIT_TAC "s0"` | 出現起始狀態 `s0` 的假設 |
| 93 | `X86_STEPS_TAC EXEC (1--2)` | **重點**：符號執行兩條指令，出現 `s1`、`s2` |
| 95 | `ENSURES_FINAL_STATE_TAC` | 剩下純粹的 word 等式 |
| 98 | `ASM_REWRITE_TAC[]` | 用假設代入 |
| 102 | `CONV_TAC WORD_RULE` | **`No subgoals`** |

第 93 行是整個 tutorial 的核心。你會看到 `rbx` 的符號值一路演變：

```
s0:  b
s1:  word_add (word b) (word a)                  ← add 之後
s2:  word_sub (word_add (word b) (word a)) (word a)   ← sub 之後
```

`a`、`b` 全程都是符號，沒有具體數值——所以這一次執行**涵蓋全部 2^64 × 2^64 種輸入**。
最後 `WORD_RULE` 確認 `(b + a) - a = b` 在模 2^64 下恆成立，溢位的疑慮就是在這裡消掉的。

收尾取出定理：

```ocaml
let SIMPLE_SPEC = top_thm();;
```

結果跟 `simple.ml` 第 64 行 `prove(...)` 一口氣做完的完全相同，只是你手動走了一遍。

#### `simple.ml` 逐行解說

上面那張表是「操作時看到什麼」，這一節是「檔案本身每一行在做什麼」。

##### 第 13 行：載入 x86 形式模型

```ocaml
needs "x86/proofs/base.ml";;
```

`needs` 讀入並執行一個檔案，已經讀過就跳過。`base.ml` 只有 67 行，工作是把
`x86/proofs/x86.ml`（6,435 行，每條指令的語意）和 `decode.ml`（3,525 行，位元組→指令）等載進來。
沒有這步，後面所有名字（`ensures`、`read`、`RIP`、`MAYCHANGE`）都不存在。

##### 第 15–21 行：被驗證的程式

```
0:   48 01 c3    add    %rax,%rbx
3:   48 29 c3    sub    %rax,%rbx
```

兩條指令各 3 個位元組，共 **6** 個——後面 `pc+6` 就是這個數字。

##### 第 22–25 行：把機器碼命名

```ocaml
let simple_mc = new_definition `simple_mc = [
    word 0x48; word 0x01; word 0xc3;
    word 0x48; word 0x29; word 0xc3
  ]:((8)word)list`;;
```

`new_definition` 建立一個新常數。`simple_mc` 是一個 8 位元字的串列（`((8)word)list`）。
`word` 把自然數轉成定長位元向量，寬度由型別標註 `(8)word` 決定。

**這步只是命名，不證明任何事，清單不會變化。**

第 27–37 行是註解掉的替代寫法 `define_assert_from_elf`，它會**直接讀 `.o` 檔**驗證位元組相符。
正式證明腳本（如 `bignum_montmul_p256.ml`）用的是那個，這裡為教學簡化成手寫。

##### 第 41 行：位元組解碼成指令

```ocaml
let EXEC = X86_MK_EXEC_RULE simple_mc;;
```

套用 `decode.ml` 的規則，產生**一組定理**——每個程式計數器位置一條，
內容是「偏移 0 的這 3 個位元組解碼成 `ADD (%rbx) (%rax)`」。
`EXEC` 之後餵給 `X86_STEPS_TAC`。同樣不改變清單。

##### 第 64 行：`prove` 是 OCaml 函式呼叫

```ocaml
let SIMPLE_SPEC = prove(`...命題...`, ...tactic...);;
```

型別 `term * tactic -> thm`。逗號前是命題，逗號後是證明它的動作序列。

##### 第 65 行：全稱量詞

```ocaml
`forall pc a b.
```

`pc` 是載入位址，`a`、`b` 是 `rax`、`rbx` 的初始值，三個都是**任意自然數**。
所以命題涵蓋所有載入位址與所有暫存器內容。

##### 第 66 行：`ensures` 的意思

```ocaml
  ensures x86
```

定義在 `common/relational.ml:1198`：

```ocaml
ensures step precondition postcondition frame <=>
    forall s. precondition s
        ==> eventually step (\s'. postcondition s' /\ frame s s') s
```

白話：**對每個滿足前置條件的狀態 `s`，用 `step` 走下去，最終會到達一個同時滿足
後置條件、且與 `s` 的差異在 `frame` 允許範圍內的狀態。**

`x86` 就是那個 `step`，即 `x86.ml` 定義的「執行一條 x86 指令」轉移關係。
後面接的三個參數正好對應下面三塊。

##### 第 68–77 行：前置條件

```ocaml
    (\s. bytes_loaded s (word pc) simple_mc /\
         read RIP s = word pc /\
         read RAX s = word a /\
         read RBX s = word b)
```

`\s. ...` 是 lambda，`s` 是一個 x86 狀態（暫存器 + 記憶體 + flags 的完整快照）。

| 條件 | 意思 |
|---|---|
| `bytes_loaded s (word pc) simple_mc` | 位址 `pc` 開始的記憶體確實放著那 6 個位元組 |
| `read RIP s = word pc` | 程式計數器指向 `pc`，準備執行第一條指令 |
| `read RAX s = word a` | `rax` 的值是 `a` |
| `read RBX s = word b` | `rbx` 的值是 `b` |

`RIP` 不是變數而是一個**存取器**（component），描述「狀態的哪個部分」，`read` 用它取值。
這個設計讓暫存器和記憶體共用同一套語法。

##### 第 79–80 行：後置條件

```ocaml
    (\s. read RIP s = word (pc+6) /\
         read RBX s = word b)
```

| 條件 | 意思 |
|---|---|
| `read RIP s = word (pc+6)` | 兩條指令都執行完了 |
| `read RBX s = word b` | `rbx` 回到初始值 ← **真正要證的東西** |

第一個條件不能省。少了它，「程式跑到一半就停下來」也會滿足後置條件，證明就沒有意義。

##### 第 82 行：frame（可變動範圍）

```ocaml
    (MAYCHANGE [RIP;RBX] ,, MAYCHANGE SOME_FLAGS ,, MAYCHANGE [events])
```

`MAYCHANGE` 定義在 `relational.ml:615`，`,,`（關係合成）在 `relational.ml:26`：

```ocaml
MAYCHANGE [] = (=)
MAYCHANGE (CONS c cs) = ASSIGNS c ,, MAYCHANGE cs

(r1 ,, r2) = \s0 s2. ?s1. r1 s0 s1 /\ r2 s1 s2
```

合起來：**結束狀態必須可以由起始狀態，透過「只對這些位置賦值」得到。**

關鍵是 `MAYCHANGE [] = (=)`——空清單代表狀態必須完全相等。所以**沒列進去的東西一個都不准變**：
`rax`、其他所有暫存器、整個記憶體，全部原封不動。

這一行的份量跟後置條件一樣重，它排除了「算對了但偷改別的地方」。

`SOME_FLAGS` 是 `[CF; PF; AF; ZF; SF; OF]`（定義在 `x86.ml:3902`），
因為 `add`/`sub` 一定會改 flags。`events` 是微架構事件，給 constant-time 分析用。

##### 第 85–102 行：七個動作

**第 85 行 `REPEAT STRIP_TAC`**
剝掉最外層結構：`forall pc a b` 去掉，三者變成**固定但任意**的值
（證明對它們不做任何假設，所以結論對所有值成立）；蘊含式左邊搬進假設。

**第 88 行 `REWRITE_TAC [SOME_FLAGS]`**
展開成 `[CF; PF; AF; ZF; SF; OF]`。第 86–87 行註解說明了原因：
後面的 `ENSURES_FINAL_STATE_TAC` 看不懂 `MAYCHANGE` 裡的未展開常數。

**第 90 行 `ENSURES_INIT_TAC "s0"`**
展開 `ensures` 的定義，引入具體起始狀態命名為 `s0`，把前置條件放進假設：

```
read RIP s0 = word pc
read RAX s0 = word a
read RBX s0 = word b
bytes_loaded s0 (word pc) simple_mc
```

**第 93 行 `X86_STEPS_TAC EXEC (1--2)`——核心**

符號執行第 1 到第 2 條指令。用 `EXEC` 的解碼定理配合 `x86.ml` 的語意逐步推出新狀態：

```
s0:  rbx = word b
     ↓ add %rax,%rbx
s1:  rbx = word_add (word b) (word a)
     ↓ sub %rax,%rbx
s2:  rbx = word_sub (word_add (word b) (word a)) (word a)
```

`a`、`b` 全程是**符號**，沒有代入具體數值——所以這一次推導涵蓋 2^64 × 2^64 種輸入組合。
`word_add`／`word_sub` 是模 2^64 的加減，**溢位行為已內建在定義裡，不是被忽略**。

把 `(1--2)` 改成 `(1--1)` 就只走一條，可以看清楚單步效果。

**第 95 行 `ENSURES_FINAL_STATE_TAC`**
宣告 `s2` 是最終狀態，攤開後置條件與 frame 的要求。能自動消掉的
（如 `read RIP s2 = word (pc+6)`，因為 `s2` 的 RIP 是推導出的具體值）就消掉。

**第 98 行 `ASM_REWRITE_TAC[]`**
用假設清單裡的等式改寫目標。`[]` 表示不額外提供定理，只用假設。

**第 102 行 `CONV_TAC WORD_RULE`**
剩下的目標是（第 99–101 行註解寫得很清楚）：

```
word_sub (word_add (word b) (word a)) (word a) = word b
```

`WORD_RULE` 是內建的位元向量自動決策程序，證明它對所有 64 位元 `a`、`b` 成立。
**溢位的疑慮在這一步被消掉**——模 2^64 的加減互為反運算，不管有沒有繞過 2^64 都成立。

清單變空，`No subgoals`。

##### 第 104–121 行：除錯開關

```ocaml
x86_print_log := true;;
```

打開後 `X86_STEPS_TAC` 會印出每步執行哪條指令、位在哪個 PC、花多少 CPU 時間。
第 93 行卡住時用得上。

註解也提到一個重要細節：**符號模擬器會丟棄「輸入沒有符號表達式」的指令輸出**。
如果某條指令讀了假設裡沒描述的暫存器，它的結果不會被追蹤——這個旗標可以列出被丟棄的指令。

##### 為什麼要證這麼「顯然」的事

`add` 再 `sub` 回到原值，直覺上不需要證明。這個例子的價值在於用最小規模，
把 s2n-bignum 所有正式證明的**完整骨架**走了一遍：
前置條件、後置條件、frame、符號執行、最後歸約到一個純數學命題。

`bignum_montmul_p256.ml` 有 40 KB、`p384_montjscalarmul_alt.ml` 有 13,848 行，
但結構完全一樣，只是指令從 2 條變成幾百條，最後那個數學命題從 `(b+a)-a = b`
變成 Montgomery 約簡的正確性。

#### 版面建議

`terminal.integrated.defaultLocation` 若設成 `"editor"`，每次 `Alt+L` 畫面都會跳到終端機分頁。
把 `HOL Light client` 分頁**拖到編輯器右半邊**自成群組即可，不用改設定：

```
┌──────────────┬──────────────┬──────────┐
│  simple.ml   │  HOL Light   │  Goal    │
│              │  client      │  側欄     │
└──────────────┴──────────────┴──────────┘
```

#### 收工前的注意事項

```bash
ss -ltnp | grep 2012      # 有 LISTEN 就代表 server 活著
```

- **兩個分頁都不要關**。關 client → server 停止（側欄死掉）；關主 REPL → 628 MB 的狀態全沒，重建要 6 分 42 秒。
- **server 不會跨 REPL**。每開一個新的 REPL session 都要重跑一次 `Start Server`。
- 改了檔案要重跑，用 `Alt+E` 重送該段就好，**不要重啟 REPL**。

#### 快捷鍵總表

`monadius.hol-light-simple` 的全部預設鍵：

| 鍵 | 功能 | 什麼時候用 |
|---|---|---|
| **`Alt+E`** | Send Current Statement | 送 `needs` / `let ...` 這類頂層 statement |
| `Alt+A` | Send All Statements before Cursor | 從檔案開頭重放到游標位置 |
| **`Alt+G`** | Set Current Term as a Goal | 把反引號 term 設成待證目標，一次 |
| **`Alt+L`** | Execute Current Tactic | 送一行 tactic，游標自動跳下一行 |
| `Alt+M` | Execute Current Tactic (Multiple Lines) | tactic 跨多行時（正式證明的常態） |
| `Alt+N` | 同上，但游標不移動 | 想反覆執行同一個 tactic |
| `Alt+R` | Select Tactic at Cursor Position | 只選取不執行，確認範圍後再 `Alt+L` |
| `Alt+O` | Rotate Subgoals | `THENL` 產生多個 subgoal 時輪換 |
| `Alt+B` | Revert One Proof Step | 退回上一步 |
| `Alt+P` | Print Current Goal | 重印目前的 goalstack |
| `Alt+D` | Remove Highlighting | 清掉送出文字的顏色標記 |
| `Alt+J` | Jump to Highlighted Text | 跳到最後送出的位置 |
| `Alt+S` | Search Theorems | 搜尋定理（需要 server） |
| `Alt+C` | Send ^C to REPL | 中斷跑太久的 tactic |

> ⚠️ 這些鍵**很容易被系統其他層攔截**——使用者自訂的 VSCode keybinding、
> AutoKey 之類的 X11 熱鍵工具、輸入法。按了沒反應且沒有錯誤訊息時，
> 見 [PITFALLS.md](PITFALLS.md) **D7 / D8 / D9**（含一個萬用診斷方法）。

#### 跨編輯器通用的指令

快捷鍵是這個擴充的慣例，換編輯器就不一樣。HOL Light 自己的介面（`tactics.ml`）是：

| 指令 | 功能 | 擴充預設鍵 |
|---|---|---|
| `g \`...\`;;` | 設定 goal | `Alt+G` |
| `e (TACTIC);;` | 執行一個 tactic | `Alt+L` |
| `b();;` | 退回上一步 | `Alt+B` |
| `p();;` | 重印目前 goal | `Alt+P` |
| `r n;;` | 輪換 subgoal | `Alt+O` |
| `top_thm();;` | 取出定理 | — |

**寫文件、或在別台機器操作時用這組。** 快捷鍵只是把這些字串貼進終端機的自動化，
在任何 HOL Light 環境（純終端機、遠端機器、其他編輯器）都成立。

> 按鍵沒反應、側欄不更新、`ledit` 崩潰等問題，見 [PITFALLS.md](PITFALLS.md) D 章。

#### 套用到正式證明（`x86/proofs/`）的四個差異

同樣三個鍵在任何 HOL Light `.ml` 檔案都能用，**其他 10 個 tutorial 完全照這個模式走**。
但套到 `x86/proofs/` 的正式證明會撞到四件事。

以 `x86/proofs/bignum_montmul_p256.ml`（800 行）為對照：

```
頂層 let 定義   22 個
prove 呼叫      15 個      ← 不是 1 個
THENL 分支      12 處
```

##### ① `Alt+E` 照用，但東西多很多

22 個頂層定義逐個 `Alt+E` 即可，機制跟 tutorial 的三行一樣：

```ocaml
let bignum_montmul_p256_mc = ...                    (* 讀 .o 的機器碼 *)
let bignum_montmul_p256_tmc = define_trimmed ...
let BIGNUM_MONTMUL_P256_EXEC = X86_MK_CORE_EXEC_RULE ...
let p_256 = new_definition `p_256 = 1157920892...`
```

**前提**：`define_assert_from_elf` 會實際讀 `x86/p256/bignum_montmul_p256.o`，
所以那個 `.o` 要先 `make` 出來，而且 cwd 必須在 repo 根目錄（wrapper 已處理）。

##### ② 一個檔案有 15 個定理，不是 1 個

```
226:  BIGNUM_MONTMUL_P256_CORRECT              指令層
318:  ..._NOIBT_SUBROUTINE_CORRECT             無 IBT landing pad 版
344:  ..._SUBROUTINE_CORRECT                   SysV ABI
374:  BIGNUM_AMONTMUL_P256_CORRECT             almost-Montgomery 版
522:  ..._WINDOWS_...                          Windows ABI
634:  BIGNUM_MONTMUL_P256_SAFE                 記憶體安全
```

每個都要各自 `Alt+G` 設 goal、各自走完。而且後面的定理常常**依賴前面證好的**
（`..._SUBROUTINE_CORRECT` 用到 `..._CORRECT`），所以前面的不能跳過——
要嘛 `Alt+E` 整段跑完，要嘛也逐步走一遍。

##### ③ `Alt+L` 會壞掉——tactic 大量跨行

tutorial 每個 tactic 剛好一行，正式證明不是：

```ocaml
  ASM_CASES_TAC `a * b <= 2 EXP 256 * p_256` THENL
   [ASM_REWRITE_TAC[]; X86_SIM_TAC BIGNUM_MONTMUL_P256_EXEC (1--114)] THEN
```

這是**一個** tactic 跨兩行。更深的巢狀：

```ocaml
  SUBGOAL_THEN
   `t < 2 * p_256 /\ (2 EXP 256 * t == a * b) (mod p_256)`
  STRIP_ASSUME_TAC THENL
   [ACCUMULATOR_POP_ASSUM_LIST
     (STRIP_ASSUME_TAC o end_itlist CONJ o DECARRY_RULE) THEN
    CONJ_TAC THENL
     [FIRST_X_ASSUM(MATCH_MP_TAC o MATCH_MP (ARITH_RULE
        `ab <= 2 EXP 256 * p
         ==> 2 EXP 256 * t < ab + 2 EXP 256 * p ==> t < 2 * p`)) THEN
      ...
```

`Alt+L` 只抓一行，送出去是語法不完整的片段，直接報錯。

**改用這兩個鍵**：

| 做法 | 按鍵 | 說明 |
|---|---|---|
| **直接送** | **`Alt+M`** | Execute Current Tactic (Multiple Lines)——往下抓完整的跨行 tactic |
| **先看再送** | **`Alt+R`** → **`Alt+L`** | `Alt+R` 只是把 tactic 範圍**選取起來**（不執行），肉眼確認框對了再按 `Alt+L` 送出 |

`Alt+M` 的抓取上限由 `hol-light.tacticMaxLines` 控制，預設 30 行。

第二種做法之所以是接 `Alt+L` 而不是 `Alt+M`：擴充在**有選取範圍**時會直接送出選取的內容，
不再做跨行邊界的自動偵測——範圍已經由 `Alt+R` 決定好了。
（`Alt+M` 在有選取時行為相同，但既然範圍已定，用哪個都一樣，`Alt+L` 比較直覺。）

##### ④ `THENL` 讓「順序」不再是視覺順序

```ocaml
  ASM_CASES_TAC `...` THENL
   [ 分支A ; 分支B ]
```

`ASM_CASES_TAC` 把一個目標拆成**兩個 subgoal**，`[...]` 裡的兩個 tactic 分別對應。

逐步走時你會看到 `2 subgoals (2 total)`，但畫面只展開第一個。
要處理第二個得用 **`Alt+O`**（`r 1;;`）輪換。檔案裡的視覺排列跟實際要走的順序對不起來。

這個檔案有 12 處 `THENL`，`p384_montjscalarmul_alt.ml`（13,848 行）只會更多。

##### 實務建議

| 目的 | 做法 |
|---|---|
| **學習** | 走完 11 個 tutorial。它們就是為逐步操作設計的，`Alt+L` 一行一行都成立 |
| **看懂某個正式證明** | `Alt+E` 把前面的定義與引理整段跑完，只對**你關心的那個定理**用 `Alt+G` + `Alt+M` |
| **只想驗證正確性** | **不要用互動模式**。`make p256/bignum_montmul_p256.correct`——編譯成原生碼跑，161 秒；互動模式是 bytecode，慢很多 |

還有一個現實限制：某些單一 tactic 就要跑好幾分鐘
（`X86_ACCSTEPS_TAC ... (1--96)` 要模擬 96 條指令），
而 `curve25519_ladderstep` 的 Gröbner basis 計算在預設 8 MB stack 下會直接 overflow
（見 [PITFALLS.md](PITFALLS.md) C3）。互動模式沒有 `ulimit -s unlimited` 的保護，
大證明不適合這樣玩。

### 步驟 6：證明單一函式
-＿
```bash
cd ~/s2n-bignum/x86
make p256/bignum_montmul_p256.correct
```

🔴 **目標一定要帶目錄前綴。** 寫成 `make bignum_montmul_p256.correct` 會得到：

```
make: *** No rule to make target 'bignum_montmul_p256.correct'.  Stop.
```

原因在模式規則（`x86/Makefile:497`）：

```make
%.native: proofs/$$(*F).ml $(BASE_ML) %.o %.obj
```

`%.o` 是**與目標同路徑**的物件檔。函式的 `.o` 放在各自的子目錄
（`p256/`、`p384/`、`curve25519/`、`generic/`…），`x86/` 根目錄下沒有，
所以 `%` 匹配不到規則。注意 `proofs/$$(*F).ml` 用的是 `$(*F)`（只取檔名部分），
所以證明腳本統一在 `proofs/` 底下，但物件檔要照子目錄走。

不確定某個函式在哪個目錄，就用 find：

```bash
cd ~/s2n-bignum/x86
find . -name 'bignum_montmul_p256.o'      # → ./p256/bignum_montmul_p256.o
```

或反過來從證明腳本找對應的物件檔：

```bash
ls proofs/ | grep montmul_p256            # 證明腳本一律在 proofs/
find . -name "$(basename proofs/bignum_montmul_p256.ml .ml).o"
```

背後發生的事（`x86/Makefile:497,501`）：

```
proofs/bignum_montmul_p256.ml  ─┐
p256/bignum_montmul_p256.o      ├─► tools/build-proof.sh ─► ....native （編成原生執行檔）
p256/bignum_montmul_p256.obj   ─┘                                │
                                                                 ▼
                                          tools/run-proof.sh ─► ....correct （執行 + 檢查 log）
```

- `.native` 是用 `ocamlfind ocamlopt` 編出來的**原生執行檔**，不是直譯執行，所以第一次編很慢
- `.correct` 是執行 `.native` 後的輸出 log；`run-proof.sh` 會 grep `error:` / `exception:`，
  有命中就回傳非 0
- 那個 `.obj` 是 **Windows ABI 版本的 object file**，證明會一併檢查它——
  所以證明流程需要 `.o` 和 `.obj` 兩個都在

**注意**：有些證明會依賴其他證明當引理，例如
`curve25519/curve25519_x25519.native` 依賴 `curve25519/bignum_inv_p25519.native`。
Makefile 已經寫好這些相依，直接 make 目標即可。

### 步驟 7：跑全部證明

```bash
cd ~/s2n-bignum/x86
nohup make -j2 proofs > proofs.log 2>&1 &   # RAM 只有 14G，別用 -j16
tail -f proofs.log
```

`proofs` target 跑完會自動呼叫 `tools/count-proofs.sh`，它會：

- 數出 `*/*.correct` 裡實際證出來的 `*_SUBROUTINE_CORRECT` / `*_SUBROUTINE_SAFE` 定理
- 跟 `proofs/specifications.txt` 的 1758 條比對
- 印出 `Total # SUBROUTINE_CORRECT: <實際>/<應有>` 並 `diff` 出差在哪

### 步驟 8（可選）：指令語意測試

```bash
cd ~/s2n-bignum/x86
make sematest
```

這個不是證明函式，而是拿 HOL Light 裡的 x86 指令**形式模型**去跟真實 CPU 對拍，
確認模型描述的指令行為與硬體一致。`NUM_CORES_FOR_SEMATEST` 可以控制平行度。

### 怎麼讀證明腳本（當作最嚴謹的 API 文件）

```bash
head -60 ~/s2n-bignum/x86/proofs/bignum_montmul_p256.ml
```

腳本開頭是被驗證的機器碼位元組序列——**不是憑空假設**，證明過程會實際跟 `.o` 對照，
確認就是 build 出來的那份。後面的 `ensures` 區塊精確寫出：

- 前置條件（暫存器/記憶體的初始狀態、ABI 參數位置、不重疊假設）
- 後置條件（回傳時的數學性質）
- `MAYCHANGE`（哪些暫存器、flags、記憶體區段可能被改動）

這比任何文字說明都精確，遇到 API 語意有疑問時查這裡最可靠。

### HOL Light 相關疑難排解

> 這裡只列最常見的幾個。安裝、跑證明、互動模式的完整踩坑記錄見
> **[PITFALLS.md](PITFALLS.md)** B / C / D 章。


**`hol_lib.cmxa does not exist in HOLLIGHT_DIR(...)`**
步驟 3 漏了 `HOLLIGHT_USE_MODULE=1`。回去重編 HOL Light。

**`make switch-5` 失敗**
你在 Ubuntu 22.04，CI 用的是 24.04。試著先升級 opam（步驟 2 的官方 script），
再 `opam update` 後重試。

**證明跑到一半被 OOM killer 砍掉**
降低平行度（`-j1` 或 `-j2`），或先避開最大的那幾個
（`p384_montjscalarmul*`、`edwards25519_scalarmuldouble*`）。
用 `dmesg | grep -i "killed process"` 可以確認是不是 OOM。

**`Exception: Failure "x86/tutorial/xxx.ml"` 或 `Failure "x86/proofs/xxx.ml"`**
這個訊息**沒有告訴你真正的原因**。`hol-light/inline_load.ml` 裡有一行：

```ocaml
let fail_if_nonexistent f x = try f x with _ -> failwith x in
```

它把巢狀 `loadt` 的任何例外都吞掉、只重拋最外層的檔名。要看到真正的例外，
複製一份不吞例外的版本（**必須放在 hol-light 目錄下**，因為腳本裡的
`#use "hol_loader.ml"` 是相對於腳本所在目錄解析的）：

```bash
sed 's/let fail_if_nonexistent f x = try f x with _ -> failwith x in/let fail_if_nonexistent f x = f x in/' \
  ~/hol-light/inline_load.ml > ~/hol-light/inline_load_verbose.ml

cat > /tmp/tmpl.ml <<'EOF'
let s2n_bignum_build_proof_start_time = Unix.time();;
loadt "x86/tutorial/bignum.ml";;
check_axioms ();;
EOF

cd ~/s2n-bignum
HOLLIGHT_DIR=$HOME/hol-light ocaml ~/hol-light/inline_load_verbose.ml /tmp/tmpl.ml /tmp/out.ml
rm ~/hol-light/inline_load_verbose.ml
```

真正的例外就會顯示出來。另外 `/tmp/out.ml` 是**部分寫出**的結果，
`tail -20 /tmp/out.ml` 可以看到它處理到哪個檔案、哪一行才爆掉——這是最快的定位方式。

**實測遇過的案例**：`Exception: Not_found`，出在 `x86/proofs/base.ml:24`
的 `loadt "Library/records.ml";;`，原因是 HOL Light 版本太舊、根本沒有那個檔案。
解法見步驟 3b 的版本檢查。

**想確認整體進度**
`find x86 -name '*.correct' | wc -l` 看已完成幾個；
`ls -l x86/*/*.native` 看已編譯幾個。

## 6. 其他變體

| 需求 | 做法 |
|---|---|
| AT&T 語法組合語言 | 用 `x86_att/` 目錄，同樣的程式碼、不同語法，某些 assembler 需要 |
| Windows ABI | 建置時加 `-DWINDOWS_ABI=1`；x86+Windows 用的是非標準 ABI |
| 產生 Windows ABI 的 `.obj` | `(cd x86 && make winobj)`（主要給證明檢查用） |

---

## 7. 清理

```bash
(cd x86 && make clean)          # 刪 libs2nbignum.a、*.o、*.obj、*.correct、*.native
(cd tests && make clean)
(cd benchmarks && make clean)
```

---

## 疑難排解

> 這一節收的是建置與執行階段的常見問題。
> **更完整的清單（含 HOL Light、跑證明、VSCode 互動模式）在 [PITFALLS.md](PITFALLS.md)。**


**`make` 在某個 `.S` 卡住 / assembler 報錯**
多半是 binutils 太舊，不認得新指令（例如 SHA-3、ML-KEM 用到的 AVX-512 相關）。
升級 binutils，或改用 clang 當組譯器（`CC` 只影響前處理，真正組譯的是 `ASSEMBLE`）：

```bash
make ASSEMBLE="clang -c -x assembler"
```

**測試 link 失敗 `cannot find -ls2nbignum`**
表示第 1 步的 `make` 沒成功，或者你在 ARM 機器上建了 `x86/`。
`tests/Makefile` 會依 `$(ARCH)` 去 `../x86` 或 `../arm` 找函式庫。

**跑出 SIGILL（非法指令）**
你的 CPU 不支援某些指令。改用 `_alt` 版本的函式。

---

## 我實際跑過的結果（2026-09-04，Ubuntu 22.04 / x86_64）

- `x86/` 建置：成功，產出 `libs2nbignum.a` 1,730,818 bytes
- `tests/ make go`：**All 374 tests run, all passed**
- `demo.c` 連結執行：X25519 結果符合 RFC 7748 測試向量
- `benchmarks/ make go`：完成，耗時約 1 小時 50 分鐘，GEOMEAN 35.5 ns（397 個測項）
  完整輸出見 `bench-ryzen7735u.log`，摘要見第 4b 節
- HOL Light 形式驗證：**未執行**——第 5 節的步驟是從官方 CI 設定與 build script
  逐條讀出來的，尚未在這台機器上實跑驗證

**現有環境（跟 HOL Light 有關的部分）**

| 工具 | 狀態 |
|---|---|
| OCaml | 4.14.2 已安裝 |
| camlp5 | 8.00.04 已安裝 |
| opam | 2.1.2 已安裝 |
| HOL Light | 未安裝 |
| RAM | 14 GB 總量／約 4 GB 可用 ← 跑證明時的主要限制 |
| /home 剩餘空間 | 156 GB（充足） |
