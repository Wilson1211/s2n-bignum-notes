執行 proof
  ↓ collector 收集並限制保留的 records
data/raw/
  ↓ 跨 proofs 合併同一個 tactic 的 records
data/merged/
  ↓ 完全去重
data/dedup/
  ↓ similarity check、各組配額與空缺遞補
data/sampling/
  │
  ├─ 篩選決定與統計 → metrics/selection/
  │
  ↓ 準備實際要送給 LLM 的 records 和 prompt
data/generation/
  ↓ LLM 生成
llm_output/descriptions/
  │
  │                  選定用來評分的 records
  │                            ↓
  │                    data/evaluation/
  │                            │
  └────────────┬───────────────┘
               ↓ LLM judge
      metrics/judge_responses/
               ↓ 將回答整理成逐筆分數
      metrics/record_scores/
               ↓ 按 tactic／description 彙整
      metrics/tactic_scores/

data/metadata/：記錄上述各階段的來源、設定與檔案關係





順序	資料夾	裡面存什麼
1	data/raw/	Collector 跑完 proof 後輸出的 records。已經受到 collector 的大小、容量與選取規則限制，因此不是執行過程中的所有 records。
2	data/merged/	把不同 proofs 中同一個 tactic 的候選 records 集合在一起，此階段仍可包含重複資料。
3	data/dedup/	依既有 record identity 規則，移除完全重複後的 records。尚未做後面的 similarity 與最終配額選擇。
4	data/sampling/	經過 similarity check、分組配額與遞補後，最後選出的 records，供 description generation 使用。
4 的紀錄	metrics/selection/	為什麼保留或排除某筆 record、相似度比較、各組數量與篩選設定。這不是 LLM 對 description 的評分。
5	data/generation/	實際生成請求：包含送進 LLM 的 records、prompt 和相關設定。若生成時另外抽樣或截斷，這裡記錄實際使用的版本。
6	llm_output/descriptions/	LLM 產生的 descriptions，以及生成嘗試與狀態等紀錄。
7	data/evaluation/	Judge 使用的 records、候選 descriptions 的對應資訊與評分任務。放在這裡不代表它們與生成資料沒有重疊，是否獨立要看實驗設計。
8	metrics/judge_responses/	保存 judge 的回答，包括逐筆判斷、理由、用量和呼叫錯誤。
9	metrics/record_scores/	把有效回答整理成每筆 record 對每份 description 的分數與理由。目前這個 judge 的對應是 full=1、partial=0.5、none=0。
10	metrics/tactic_scores/	將逐筆分數彙整成每個 tactic／description 的結果，供比較、報表與表格使用。
全流程	data/metadata/	s2n-bignum commit、實驗設定、來源檔案、雜湊、搬移對照等追溯資訊。各資料清單的 index 也可以與 records 放在同一階段資料夾。