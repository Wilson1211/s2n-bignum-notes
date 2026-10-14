# Sampling：送到 EngineeringSoftware 的兩個 PR

整理日期：2026-09-28。

這份文件取代先前把 sampling PR 送到 `hol-light/TacticTrace` 的提交方向。
Lazy approach 的兩個上游 PR 是另一條工作線，不在這次 sampling PR 中處理。

## 正確位置與目的地

- 工作目錄：`/home/tong-nong/s2n-bignum-hol-light-llm-sampling`
- Repository：`EngineeringSoftware/s2n-bignum-hol-light-llm`
- 此工作目錄的 `origin`：`https://github.com/EngineeringSoftware/s2n-bignum-hol-light-llm.git`
- 起點：`28b0666`，已包含 record-setting-paths PR #32。
- 原本 `/home/tong-nong/TacticTrace-sampling` 與 Wilson1211 fork 裡的分支保留作為實作來源／備份，不刪除、不作為這次 PR 的 head。

兩個 repository 可以有同名本機分支；執行指令前要先 `cd` 到上面的正確工作目錄。

## 已整理的本機 commits

PR 1：

| Commit | Message |
| --- | --- |
| `fc1c1dd` | `feat(trace): add isolated sampling collector preparation` |
| `481c284` | `test(trace): cover sampling policies and isolated fixture builds` |
| `5207f94` | `docs(trace): explain opt-in sampling setup and provenance` |

PR 2 相對 PR 1 的三筆新增 commits：

| Commit | Message |
| --- | --- |
| `9196f29` | `feat(cli): add isolated trace sampling runner` |
| `7e45a41` | `test(cli): cover sampling runner safeguards` |
| `f089f9f` | `docs(cli): explain sampling runs and container boundaries` |

## 本次驗證結果

- 準備工具／fixture build 的離線安全測試：8 項通過。
- 使用實際套用 patch 的 collector 重新 inline-load、compile、link：成功。
- Collector native suite：5 項通過，268.698 秒。
- Runner 離線測試：11 項通過；`bash -n` 通過。
- Runner 搭配本次新編譯 fixture 的整合 smoke test：通過，seed 42、capacity 20、7／7／6 配額。
- 兩個 PR 範圍的 `git diff --check` 通過；工作目錄乾淨。
- 沒有執行真實 s2n campaign、Docker deployment 或付費模型呼叫。

保留的本機驗證資料：

- Collector checkout：`/tmp/s2n-sampling-pr1-validation.nzCt1p/tactictrace`
- Fixture：`/tmp/s2n-sampling-pr1-validation.nzCt1p/build/trace_sampling.native`
- Runner metadata：`/tmp/s2n-sampling-runner-smoke.IAcGEP/output/proof.sampling.json`

`/tmp` 內容可能被系統清理；它們不是正式實驗資料或長期保存位置。

## 為什麼這次是 patch？

EngineeringSoftware repo 沒有追蹤 TacticTrace 原始碼。原本 setup 會另外下載
HOL Light 並建置其中的 TacticTrace，所以不能把另一個 repo 的 commits 直接送過來。

本次整合把既有 sampling collector 修改存成
`utils/patch/tactictrace-sampling.patch`，並提供明確選用的準備工具。
工具只在全新 checkout 套用 patch，不覆寫使用者的 source checkout，也不自動修改
現有 campaign、Docker defaults 或 setup 流程。

Patch 的基準是 TacticTrace `8cd6a0953c7836e038ae943b8c7973e2121cde74`。
它已包含合併過的 lazy 核心功能，不包含 June 留言的那個 lazy 測試 PR。
基準容量是 20、分組為 7／7／6，不是把既有 relaxed campaign 的容量改成 20。

## 分支與 PR 依賴

| 項目 | Head branch | Base branch |
| --- | --- | --- |
| PR 1：collector 實驗整合 | `feature/trace-sampling-policy` | `main` |
| PR 2：runner | `feature/trace-sampling-runner` | `feature/trace-sampling-policy` |

兩個分支都推到 EngineeringSoftware 同一個 repo，第二個 PR 才能直接選第一個
分支當 base。PR 2 相對 PR 1 只增加 runner、測試及文件，不應重複顯示 collector 修改。

先 review／merge PR 1。它 merge 後，先檢查 PR 2 的 base 及 diff；若第一個以
squash 或 rebase 合併，通常需要整理第二個分支，再把 base 改成 `main`。
不要假設 GitHub 已自動處理，也不要直接先 merge PR 2。

## 推送命令

尚未執行以下 push 或建立 GitHub PR。兩個分支應各有三筆自己的 commits。

```bash
cd /home/tong-nong/s2n-bignum-hol-light-llm-sampling

# Confirm this origin is EngineeringSoftware, not hol-light.
git remote -v
git status --short

# Upload both branches to the same EngineeringSoftware repository.
git push -u origin feature/trace-sampling-policy
git push -u origin feature/trace-sampling-runner
```

如果 push 顯示權限不足，先停止，不要改推到原本的 `Wilson1211/TacticTrace`。
那是另一個 repository，不能取代這次的目的地。

## PR 1

建立頁面：

```bash
xdg-open 'https://github.com/EngineeringSoftware/s2n-bignum-hol-light-llm/compare/main...feature/trace-sampling-policy?expand=1'
```

Title：

```text
[1/2] Add an opt-in trace sampling collector experiment
```

Body：

```markdown
## Summary

- Keep the Stage 1 sampling experiment in this research repository as a local TacticTrace patch.
- Add a preparation helper that reads a pinned committed baseline and applies the patch only in a fresh isolated checkout. Preserve source edits and existing proof artifacts.
- Keep legacy retention as the default and add opt-in stratified reservoir sampling by 0, 1, and 2+ subgoals, with deterministic private random streams and sampling metadata.
- Keep the pinned upstream limits unchanged: capacity 20 split 7/7/6. This does not alter the frozen relaxed campaign or deploy into an existing HOL Light checkout.

## Commit guide

1. Collector patch and isolated preparation helper.
2. Preparation safety tests, native collector fixture, and inline-load build helper.
3. Experiment usage, source provenance, limits, and rebuild documentation.

## Prerequisite and scope

The patch is based on TacticTrace 8cd6a0953c7836e038ae943b8c7973e2121cde74,
which already includes lazy tactic arguments. This is separate from the upstream
lazy-argument test PR and does not submit sampling to hol-light/TacticTrace.

No normal setup, Docker defaults, existing campaign limits, or LLM prompts are
changed. Real proofs require an explicit isolated deployment and fresh build.
Balanced buckets are not a demonstrated improvement in description quality.

## Validation

- All 8 preparation/build safety unit tests pass.
- Patched collector built using hol.sh inline-load, compile and link.
- All 5 focused native test methods pass (268.698 seconds), covering legacy equivalence, bucket quotas, reproducibility,
  conversions, lazy arguments, invalid settings and output collision protection.
- No real s2n-bignum campaign, Docker deployment, or paid API experiment.

The follow-up PR adds a command-line runner; this PR does not require it.
```

## PR 2

建立頁面：

```bash
xdg-open 'https://github.com/EngineeringSoftware/s2n-bignum-hol-light-llm/compare/feature/trace-sampling-policy...feature/trace-sampling-runner?expand=1'
```

Title：

```text
[2/2] Add a runner for isolated trace sampling experiments
```

Body 中把 `#XXX` 換成第一個 PR 的實際編號：

```markdown
## Dependency

Depends on #XXX. This PR targets feature/trace-sampling-policy so that its diff
contains only the runner changes. Please merge the collector PR first; I will
then check the base/diff and update this branch before merging it into main.

## Summary

- Add scripts/run-with-sampling.sh for proofs rebuilt with the experimental collector.
- Validate policy, seed and fresh output roots; provide a side-effect-free preview.
- Forward command arguments literally, set the sampling environment only for the
  child, and preserve failed commands' exit status and partial output.
- Validate completion metadata after execution.
- Document local usage and running the wrapper inside the existing container.

## Commit guide

1. Command-line runner.
2. Offline runner safeguard tests.
3. Usage examples, container boundaries and build prerequisites.

## Validation

- All 11 runner unit tests pass; Bash syntax check passes.
- End-to-end smoke test passes with the newly built synthetic HOL Light fixture.
- No real s2n proof campaign, Docker deployment, or paid model calls.

## Limits

This does not rebuild proofs or invalidate cached .correct targets. Metadata
validation is after execution, not a preflight sandbox: an old executable can
ignore the variables and write to its old output path. Verify build provenance
first. Existing Docker/setup defaults and campaign artifacts remain unchanged.
```
