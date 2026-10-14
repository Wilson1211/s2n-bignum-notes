# TacticTrace sampling：兩個 PR、各三筆 commits

> 2026-09-28 更正提交目的地：下列是舊 TacticTrace 開發分支的紀錄，保留作為實作來源。
> 新的 sampling PR 應送到 EngineeringSoftware，請依照
> [sampling-engineeringsoftware-prs.md](sampling-engineeringsoftware-prs.md)，不要沿用本文件的上游提交規畫。

整理日期：2026-09-27。

這裡的「PR 1／PR 2」是拆分順序，不是 GitHub PR 編號。
目前只有本機分支與 commits，尚未 push 或建立遠端 PR。

工作目錄：`/home/tong-nong/TacticTrace-sampling`。
目前 checkout 在 `feature/trace-sampling-runner`，所以檔案包含兩個 PR 的內容。
`feature/trace-sampling-policy` 仍指向第一個 PR 的完成位置。

## 分支與 commits

PR 1：`feature/trace-sampling-policy`，基於上游 `8cd6a09`。

| Commit | Message | Review 重點 |
| --- | --- | --- |
| `5af489a` | `feat(trace): add opt-in stratified reservoir sampling` | 舊策略預設、分組、亂數、輸出與 metadata |
| `f5c85b8` | `test(trace): cover sampling policies and legacy compatibility` | 核心測試、fixture 與測試整合 |
| `8095110` | `docs(trace): explain sampling policies and runtime configuration` | 不依賴 wrapper 的直接環境變數用法 |

PR 2：`feature/trace-sampling-runner`，基於 PR 1 的 `8095110`。

| Commit | Message | Review 重點 |
| --- | --- | --- |
| `04fccea` | `feat(cli): add an isolated trace sampling runner` | flags、隔離目錄、失敗狀態與完成檢查 |
| `9d2f4ae` | `test(cli): cover sampling runner safeguards` | wrapper 測試及 Makefile 呼叫 |
| `14599c1` | `docs(cli): document isolated sampling experiment commands` | dry-run、正式執行、Docker、限制 |

PR 2 的 Git 歷史包含 PR 1，但相對 PR 1 只有三筆新增 commits。
拆分沒有改變 collector、wrapper 或四份測試／建置程式的內容；其 SHA-256
與拆分前一致。文件依賴和 Makefile 測試呼叫已分成兩階段。

## 遠端 base 的注意事項

- `origin` 是 `hol-light/TacticTrace`；`fork` 是 `Wilson1211/TacticTrace`。
- 查詢時，上游沒有 `feature/trace-sampling-policy` 分支。
- 因此不能假設只把分支 push 到 fork，就能在上游 repo 選它當 base。
- 建議先送 PR 1 到上游 `main`；合併後整理 PR 2，再送到上游 `main`。
- 若 maintainer 願意在上游建立對應 base branch，才可同時送出差異乾淨的
  stacked PR。不要把送到自己 fork 的 PR 誤當成送給上游的 PR。
- PR 1 若以 squash/rebase 合併，PR 2 通常需要 rebase，讓已合併的核心修改
  不再出現在第二個 PR 的差異中。操作前要重新確認遠端狀態。

## PR 1 草稿

Title:

```text
Add opt-in stratified reservoir sampling for tactic traces
```

Body:

```markdown
## Summary

- Keep `legacy` as the default tactic retention policy.
- Add opt-in `stratified-reservoir`, selected through runtime environment variables.
- Use separate reservoirs for 0, 1, and 2+ subgoals, with private deterministic random streams per tactic and bucket.
- Keep the upstream capacity of 20, split 7/7/6 under the new policy. Size filters, conversion retention, and record JSON remain unchanged.
- Add explicit output-root redirection and sampling metadata without overwriting existing dumps or sidecars. Legacy runs without sampling configuration keep their original output behavior.

## Commit guide

1. Implementation: runtime settings, reservoir selection, output isolation, and metadata.
2. Tests: compile this checkout's collector into an isolated HOL Light fixture and include the focused suite in `make test`.
3. Documentation: direct environment-variable usage, reproducibility, and rebuild requirements.

## Validation

- The PR 1 focused target passed after splitting: `make test-trace-sampling HOLLIGHT_DIR=/home/tong-nong/hol-light` (5 collector test methods).
- Focused collector tests cover legacy retained-record and JSON equivalence, fixed quotas, rare and later records, deterministic/private randomness, lazy arguments, size filters, unchanged conversions, metadata, invalid settings, and output collisions.
- No real s2n-bignum campaign or full example-pipeline `make test` run was performed. No remote deployment was performed.

## Review focus and limitations

Please focus on legacy retention equivalence, reservoir acceptance, private random state, and collision-safe output handling.

Proof sources must be regenerated and rebuilt with this collector. Editing the source or rebuilding only the kernel wrapper does not update existing executables. Direct stratified usage requires an existing absolute output root. Fixed quotas may leave capacity unused; more balanced buckets do not establish better descriptions.

A separate follow-up PR adds the command-line runner. This PR does not require it.
```

## PR 2 草稿

以下草稿預設已選好正確 base，讓 PR 只顯示 runner 的三筆新增 commits。

Title:

```text
Add an isolated runner for tactic sampling experiments
```

Body:

```markdown
## Summary

- Add `run-with-sampling.sh` for rebuilt proofs using the selectable sampling collector.
- Validate policy, seed, and a new absolute output root; support a side-effect-free dry run.
- Forward command arguments without shell evaluation and override inherited sampling variables together.
- Preserve a failing command's exit status and partial output.
- Reject apparently successful runs with missing, invalid, or mismatched completion metadata.

## Dependency and commit guide

This builds on the selectable trace sampling collector from the preceding change.

1. Implementation: command-line options, fresh output roots, and completion checks.
2. Tests: runner safeguards, plus the test invocation in the focused sampling target.
3. Documentation: preview and execution examples, Docker paths, and build/output requirements.

## Validation

- All 11 runner test methods pass, including argument forwarding, seed normalization, inherited settings, output protection, command failures, and missing/incomplete/mismatched metadata.
- A stratified end-to-end smoke run passed using this runner and the rebuilt HOL Light fixture.
- No real s2n-bignum campaign or full example-pipeline `make test` run was performed. No remote deployment was performed.

## Review focus and limitations

Please focus on argument/environment forwarding, exclusive output-root creation, exit-status handling, and metadata validation.

The runner requires Bash and Python 3. It does not rebuild proofs or bypass cached `.correct` targets. Metadata is checked after execution, so this is not a preflight guarantee that an arbitrary executable contains the new collector. Verify build provenance first, and run the wrapper inside Docker when using container paths.
```

## 本機驗證紀錄

- 拆分前：collector 五項測試通過；最後小幅修改後重新 build，legacy 比對再通過。
- 拆分前：runner 與新版 HOL Light fixture 的實際整合 smoke test 通過。
- 拆分後：wrapper 11 項測試通過。
- 拆分後：PR 1 專用 target 的完整 collector suite 通過，5 項測試，294.861 秒。
- 分支快照檢查：PR 1 沒有依賴尚未加入的 runner；PR 2 差異限於 runner、
  runner 測試、Makefile 呼叫，以及 README／使用文件。
- 尚未 push、建立 GitHub PR 或 merge；原 campaign 的 artifacts 未更動。
