# 候選池比選法重要：大小還是分布？（2026-11-01／02）

對應的論文小節：`paper/experiments/candidate-pool.tex`（標題 Candidate Pool versus Selector），
在論文 worktree `/home/tong-nong/s2n-bignum-hol-light-llm-failure-prompt-paper`。

## 1. 要回答的問題

論文的貢獻是 cg（coverage-greedy），所以目標是找到一種改法，讓 cg 在 success 紀錄上贏過 r（隨機選）。
之前的結果是 cg 和 r 差不多，甚至 r 略好。這次想知道：
1. 如果候選池變大、裡面的紀錄更多樣，cg（cg-v2）能不能拉開差距？
2. 如果拉不開，分數的差異到底來自哪裡？

## 2. 背景：紀錄要經過兩個階段才會進到 prompt

| | 第一階段：抽樣 → 候選池 | 第二階段：挑選 → 訓練集 |
|---|---|---|
| 什麼時候做 | 跑證明、收集 trace 的時候 | 收集完，離線做 |
| 規則 | 按 subgoal 數分 5 組，每組最多 16 筆，不看 call site | cg、r、cg-v2、cgw 等選法 |
| 數量 | 每個 tactic 每個證明 80 筆，三個證明合計 240 筆 | 從三個證明合起來的池子挑 40 筆（5 組 × 8） |

在程式碼裡，第一階段的名額叫 candidate quotas，第二階段叫 final quotas（`daily.py --two-stage`）。
目前的候選池是 `out/sampling-experiments/mux-add-sub-candidates-20261014/`。

**測試紀錄 C 是另一個抽樣器抽的。** 跑證明時還有一個「獨立評估抽樣器」在看同一串 tactic 執行，
它抽出 C（C0 = mux、C1 = add、C2 = sub），用來給 judge 打分。它用 call-site 規則：
- call site 是 tactic 被呼叫的位置，也就是檔案和行號（紀錄裡的 `user_line_number`）。
- 每個 call site 分到的名額和它執行次數的平方根成正比，每個位置最多 10 筆。
- 每個 tactic 每個證明 40 筆，seed 42。
- 這樣做是為了避免某個很常被呼叫的位置佔滿整個樣本。

## 3. 實驗 lpa1-20261101（付費，US$39.15）

**大候選池的做法：** 第一階段的參數是凍結的不能動，所以改用獨立評估抽樣器重跑一次收集，
把 capacity 從 40 改成 300、seed 從 42 改成 43，再把 C 自己抽到的執行移除。
Tokyo run：`site-strata-pool300-seed43-tokyo-20261101`。

**注意：** 這不是「第一階段多給一點名額」，而是整套抽樣規則都換成跟 C 一樣。所以大小和分布同時改變了。

**設定：**
- 6 個依賴參數的 tactic：CONV_TAC、DISCH_THEN、FIRST_X_ASSUM、MAP_EVERY、MATCH_MP_TAC、TRY。
- 從大候選池用 cg-v2 和 r 各挑一次，每種各 3 個 seed，共 6 份訓練集。
- failure 紀錄跟公開的 r 完全相同。
- 描述用 v3.3 prompt；judge 用 pointwise v5，在 C0–C2 上打分。
- 36 次描述呼叫加 108 次 judge 呼叫，沒有失敗。

## 4. 結果：選法差很少，候選池差比較多

6 個 tactic 的 success 平均分：

| 紀錄 | 大候選池 cg-v2（seed 1/2/3） | 大候選池 r（seed 1/2/3） | 公開的 cg | 公開的 r |
|---|---|---|---|---|
| 全部（570 筆） | 97.96 / 98.12 / 97.67 | 97.61 / 98.03 / 97.55 | 95.76 | 96.35 |
| 目前候選池裡沒有相同紀錄的（467 筆） | 97.72 / 97.96 / 96.99 | 97.05 / 97.73 / 97.11 | 94.56 | 95.91 |
| 兩個候選池都沒有相同紀錄的（252 筆） | 95.17 / 95.47 / 93.14 | 93.21 / 95.21 / 93.21 | 91.73 | 92.30 |

- **選法：** cg-v2 只比 r 高 0.19、0.26、0.71 分。18 個 tactic × seed 組合裡，cg-v2 高 5 個、低 4 個。
  只有 MAP_EVERY（cg-v2 +1.80，但三個 seed 分別 +14、+6、−8）和 DISCH_THEN（−0.94）有差別。
- **候選池：** 6 份大候選池描述在三種紀錄範圍上都贏過公開的 cg 和 r。
  同樣用 r，大候選池比目前候選池高 1.38 分（全部）、1.58 分（兩池都沒有相同紀錄的）。
- **不是因為抄到測試紀錄：** 大候選池的訓練集含有的 C 紀錄副本（24–37 筆）反而比公開的 cg（58）和 r（41）少。

## 5. 分數差距從哪裡來

**幾乎只來自 MATCH_MP_TAC。** 把目前候選池的 3 份描述（公開 cg、公開 r、cgw）和大候選池的 6 份逐個 tactic 對照：

| tactic | 目前候選池 3 份 | 大候選池 6 份的範圍 |
|---|---|---|
| CONV_TAC | 97.73 / 100 / 100 | 全部 100 |
| DISCH_THEN | 96.70 / 91.51 / 92.45 | 93.40–97.64 |
| FIRST_X_ASSUM | 99.48 / 99.48 / 96.65 | 98.71–99.48 |
| MAP_EVERY | 85.78 / 92.24 / 91.01 | 89.87–96.57 |
| MATCH_MP_TAC | 全部 94.85 | 全部 99.26 |
| TRY | 全部 100 | 全部 100 |

只有 MATCH_MP_TAC 兩邊完全分開，其他 tactic 的範圍重疊，差距在單份描述本身的波動之內。

**MATCH_MP_TAC 差在一個行為。** 分數改變的 6 筆紀錄都是同一種情況：
如果定理裡有某個變數沒辦法從目標對應出來，它會在新目標裡變成 `exists`。

例子：用 `CONG_IMP_EQ: ∀x y n. x < n ∧ y < n ∧ (x ≡ y) (mod n) ⇒ x = y` 處理目標 `x = x'`。
`n` 不在結論裡，對應不出來，所以新目標變成 `∃n. x < n ∧ x' < n ∧ (x ≡ x') (mod n)`。

judge 給目前候選池的 3 份描述部分分，理由都是「沒說明未配對的變數會變成存在量詞」。
大候選池的 6 份描述都寫到了。

| | 有這種行為的紀錄 |
|---|---|
| 目前候選池 | 0 / 240 |
| 目前候選池的 3 個訓練集 | 各 0 / 40 |
| 大候選池（已移除 C 的執行） | 54 / 531（約 10%） |
| 大候選池的 6 個訓練集 | 各 4–6 / 40 |
| C | 7 / 68（約 10%） |

## 6. 為什麼目前候選池沒有這種紀錄

第一階段的規則不看 call site，所以紀錄集中在少數幾個呼叫位置。

| tactic | 目前候選池：筆數 / call site 數 / C 的 call site 有出現的比例 | 大候選池：同左 | C：筆數 / call site 數 |
|---|---|---|---|
| CONV_TAC | 240 / 5 / 0.24 | 878 / 367 / 0.71 | 120 / 72 |
| DISCH_THEN | 240 / 79 / 0.14 | 829 / 380 / 0.75 | 118 / 93 |
| FIRST_X_ASSUM | 240 / 66 / 0.15 | 772 / 274 / 0.97 | 117 / 91 |
| MAP_EVERY | 240 / 68 / 0.33 | 653 / 178 / 0.97 | 120 / 87 |
| MATCH_MP_TAC | 240 / 16 / 0.10 | 531 / 328 / 0.51 | 68 / 58 |
| TRY | 240 / 15 / 0.46 | 404 / 36 / 0.99 | 120 / 30 |

在論文用的 29 個 tactic 上，C 紀錄的 call site 有出現在目前候選池裡的比例平均只有 0.46，
其中 19 個 tactic 低於一半。

## 7. 是大小還是分布？→ 是分布

**做法：** 從大候選池每個證明隨機抽 80 筆，做成跟目前候選池一樣大（240 筆）的池子，
再模擬 r 從裡面挑 40 筆，重複 300 次。不用呼叫模型。

| | 目前候選池（240） | 大候選池縮成 240 | 大候選池全部 |
|---|---|---|---|
| MATCH_MP_TAC 訓練集裡有這種行為的筆數 | 0 | 4.23 | 4.36 |
| CONV_TAC：C 紀錄的 call site 出現在訓練集的比例 | 0.21 | 0.34 | 0.35 |
| DISCH_THEN：同上 | 0.07 | 0.14 | 0.14 |
| MATCH_MP_TAC：同上 | 0.09 | 0.21 | 0.22 |
| TRY：同上 | 0.39 | 0.76 | 0.72 |

縮小後的池子跟完整的大候選池幾乎一樣，每個 tactic 最多差 0.04。

**為什麼：** r 是隨機挑。從一個池子挑，和從它的隨機子集挑，抽到的東西分布相同。
所以池子大不大不重要，重要的是池子裡有什麼。大候選池好，是因為它的 call site 分布跟 C 一樣分散。

## 8. 這代表什麼

- 目前候選池裡完全沒有某些行為，不管怎麼改 cg 都挑不到。瓶頸在第一階段，不在第二階段。
- 換成跟 C 同分布的池子後，這類行為約佔 10%，r 隨機挑就能抽到 4–6 筆，cg 也就沒有優勢。
- cg 要贏 r，只可能出現在「某種行為在池子裡很少見、r 常常抽不到」的情況。
- 論文方面：公開的 cg 和 r 都是從分布跟 C 不同的池子挑訓練紀錄。

## 9. 限制

- 「縮成 240」是用隨機子集模擬的，不是真的用 call-site 規則只抽 80 筆，也沒有拿去給 judge 打分。
  如果要更硬的證據，可以在 Tokyo 用 call-site 規則實際收集一次每個證明 80 筆的池子（不用錢，約 10 分鐘）。
- 分數上只有 MATCH_MP_TAC 看得到效果。其他 tactic 的訓練集也確實更接近 C，但分數差距被描述本身的波動蓋過。
- 大候選池和 C 用同一套規則抽，所以有一部分提升可能只是「訓練和測試分布一致」。
  換一個用不同規則抽的測試集，提升可能會變小。
- 只測了 6 個依賴參數的 tactic。

## 10. 資料和腳本在哪

- lpa1 報告：`out/metrics/tactic_scores/lpa1-20261101__combined-independent-with-ps3.md`
- 大候選池（本機副本）：`out/sampling-experiments/site-strata-pool300-seed43-tokyo-20261101/`
- 實驗腳本：cg-features worktree 的 `experiments/sampling/prepare_lpa_arms.py`、`lpa1-20261101-commands.sh`（還沒 commit）
- 分析腳本（在 session 的 scratchpad，是暫存位置，之後可能會消失）：
  `/tmp/claude-1000/-home-tong-nong-s2n-bignum-hol-light-llm/b85fead1-d94d-4489-a7d0-cf062a95a2b7/scratchpad/v2/`
  裡的 `lpacheck.py`、`lpacheck2.py`、`sitecheck.py`、`sitecheck2.py`、`mmp.py`、`mmp2.py`、`sites29b.py`、`sizesim.py`
- LaTeX：`paper/experiments/candidate-pool.tex`，以及 `paper/tables/table-candidate-pool-{scores,per-tactic,existential,call-sites,size}.tex`
