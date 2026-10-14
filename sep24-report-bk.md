# Weekly Progress — September 24, 2026

## 1. Record-grounded description evaluation

The evaluator checks whether a description explains the behavior shown in a
record: the goal before, tactic arguments, and goals after. It does not only
compare the wording of two descriptions.

For each tactic, the new experiment compares:

- A description generated from our relaxed-setting traces.
- A description generated from official-setting traces.
- The corresponding HOL Light Help text.

Help is another candidate to evaluate, not the correct answer. It is not given
to the description-generation prompt. All three candidates are judged against
the same records within a call.

### Experiment design

- Relaxed and official records are evaluated in separate API calls.
- The three descriptions are labeled A/B/C. One seeded order is chosen for each
  tactic and kept the same across its settings and batches. 
- We sample up to eight records per tactic per setting, from proofs present in
  both trace collections. This is a shared-proof filter, not a record intersection.
- Full record fields are kept. The planner splits large prompts into smaller
  batches and rejects a single record that exceeds the configured prompt-size
  bound, rather than silently cutting it.
- The judge scores each description on each record: `full = 1`, `partial = 0.5`,
  and `none = 0`. Non-full scores require a reason.
- We first average records within each tactic/setting, then give each tactic
  equal weight. Overall comparisons average the two setting means equally.

### Evaluation flow

The two record settings stay separate. The same three descriptions and the same
A/B/C mapping are used on both sides for a given tactic.

```text
Two generated-description files + two record indexes
        │
        ▼
 [0] Find tactics with both descriptions and usable records
        │ keep records from proofs traced in both settings
        ▼
     69 eligible tactics before the Help check
        │
        ▼
 [1] Is matching Help text available?
        ├─ no ─────────────────────► exclude 94 tactics, not score them as zero
        ▼ yes
     69 tactics enter the experiment
        │
        ▼
 [2] For each tactic, prepare three candidate descriptions
     relaxed-generated + official-generated + Help
        │ hide source labels; choose one seeded A/B/C order
        ▼
 [3] Sample records and save the fixed plan
        │
        ├──────────────────────────────────────┐
        ▼                                      ▼
 Relaxed records                         Official records
 up to 8 sampled                         up to 8 sampled
        │                                      │
        ▼                                      ▼
 Split into batches if needed            Split into batches if needed
 keep full record fields                 keep full record fields
        │                                      │
        ▼                                      ▼
 [4a] Judge A, B, C                       [4b] Judge A, B, C
      on relaxed records                      on official records
        │                                      │
        └──────────────────┬───────────────────┘
                           ▼
 [5] Save per-record verdicts and reasons
     then build six description-by-setting score cells
```

The two judge branches are independent API calls, not one combined prompt.
If one record plus the descriptions exceeds the prompt-size guard, preparation
stops with an error instead of cutting the record. In this completed run, each
setting fit in one batch: 69 tactics × 2 settings = 138 calls.

### How scores become the report

```text
One description + one evaluated record
        │
        ▼
 Judge verdict: full = 1, partial = 0.5, none = 0
        │ partial / none also includes a reason
        ▼
 All batches for this tactic and record setting completed?
        ├─ no ─────────────────────► score stays missing, not zero
        ▼ yes
 Mean across records = this tactic/setting score
        │
        ├─ mean across tactics ────► one cell in the six-cell results table
        │
        ▼
 Both settings completed for this tactic?
        ├─ no ─────────────────────► leave out of overall paired comparisons
        ▼ yes
 Average relaxed-setting and official-setting scores equally
        │
        ▼
 Subtract one description's score from another's, within each tactic
        │
        ▼
 Average these differences across complete tactics
        │
        ▼
 Overall paired difference and bootstrap interval
```

### Completed sampled run

Run name: `help-separated-pilot-run1`. The plan was created on September 23.
These numbers come from its saved `manifest.json` and `summary.json`.

| Item | Result |
|---|---:|
| Generated descriptions available: relaxed / official | 167 / 206 |
| Eligible tactics before requiring Help | 163 |
| Tactics excluded because usable Help was missing | 94 |
| Tactics evaluated and completed | 69 / 69 |
| Shared proofs used for sampling | 25 |
| Sampled record instances across both settings | 1,008 |
| Truncated records | 0 |
| Completed API calls | 138 / 138 |
| API errors / response-parsing errors | 0 / 0 |
| Input / output tokens | 1,027,890 / 96,331 |
| Estimated model cost | $7.55 |

The 1,008 records are counted within their respective settings. A record that
appears in both settings is evaluated separately in each setting. This run
completed its sampled plan; it did not evaluate every record in the corpus.

### Description scores

All cells below cover the same 69 tactics. Scores range from 0 to 1.

| Description source | Relaxed records | Official records |
|---|---:|---:|
| Relaxed-generated | 0.9886 | 0.9886 |
| Official-generated | 0.9571 | 0.9788 |
| HOL Light Help | 0.8569 | 0.8614 |

| Overall paired difference | Mean difference | Bootstrap 95% interval |
|---|---:|---|
| Relaxed-generated minus official-generated | +0.0207 | [0.0007, 0.0444] |
| Relaxed-generated minus Help | +0.1294 | [0.0855, 0.1771] |
| Official-generated minus Help | +0.1088 | [0.0611, 0.1577] |

On this sample, relaxed-generated descriptions received the highest average
coverage score. Both generated sources scored above Help under this rubric.
The relaxed-versus-official difference is small; its paired sign-test p-value
is 0.1892 among 21 non-tied tactics, so the bootstrap interval alone should not
be presented as a clear overall win.

### Reasons and limitations

The saved JSON report contains 349 nonempty reasons: 24 for relaxed-generated
descriptions, 64 for official-generated descriptions, and 261 for Help. They are
organized by description source, tactic, record setting, and record ID. The
current Markdown report contains aggregate tables only. Full-score reasons are
normally empty because the prompt requests an explanation only for partial or
none scores.

These results measure retrospective coverage of sampled records, not formal
correctness or performance on held-out proofs. We have not established that the
evaluation records are independent of the description-generation evidence.
The Help requirement also reduces the cohort to 69 tactics. A lower Help score
does not by itself mean the manual is wrong: this rubric asks how well its text
predicts particular trace outcomes. Scores are close to the upper limit for the
generated descriptions, and the single-order design does not measure position
bias. Manual checks of the reasons are still needed.

### Example: AP_TERM_TAC on one official record

This example comes from `help-separated-pilot-run1`, task
`a0b3a5ebdfafcad2-off-b1`, record `r1`. It was selected
to show a disagreement, not as a randomly selected or representative example.
The original call contained eight records; only r1 is shown below. The scores
are for this record, not the mean scores for the whole tactic.

The source names below are shown for the reader. The judge saw anonymous labels:
A = official-generated, B = Help, C = relaxed-generated. The descriptions below
are the exact saved, anonymized candidate text.

#### Relaxed-generated description (candidate C)

```text
<TACTIC> strips a common outermost function application off both sides of an equation (or iff), reducing `f a = f b` to `a = b`. Every record shows exactly one goal out, assumptions untouched — it never discharges or adds hypotheses, it only peels the goal's conclusion. The 'function' can be any head term: a constructor-like operator (`2 EXP _`, `2 * _`, `bit _`, `word _`, `nsum _`, `CARD _`, `word_popcount _`, `f _`), giving e.g. `2 EXP SUC (k-1) = 2 EXP k` |-> `SUC (k-1) = k`, or `CARD {m | ...} = CARD {m | ...}` |-> set equality. It also works on partially applied binary operators, which is how repeated use walks into the left argument: `(+) (2 * f m n) = (+) (2 * n)` becomes `2 * f m n = 2 * n`, and likewise for `(DIV)`, `(MOD)`, `(*)`, `(EXP)`, `(<=>)`, `(/\)`, `COND`, `(pow)`. When the stripped head is a binder like `minimal`, `@`, `?`, or `!`, the residual goal is an equation between the two lambda bodies, e.g. `(!m. 2 <= index m n ==> m = 1) <=> (!m. index m n <= 1)` |-> `(\m. 2 <= index m n ==> m = 1) = (\m. index m n <= 1)`. It fails (not shown here, since the records succeed) unless the two sides really share the same top-level operator.
```

#### Official-generated description (candidate A)

```text
`<TACTIC>` is pure congruence peeling: given a goal of the form `f a = f b` (or `f a <=> f b`, since `<=>` is equality on bool) where both sides apply the *same* function to different arguments, it discards the common head `f` and leaves the single subgoal `a = b`. In these records the head is anything from `2 EXP _` (a record: `2 EXP SUC (k - 1) = 2 EXP k` becomes `SUC (k - 1) = k`), `p EXP _`, `CARD _` (a record/20/21, reducing set-cardinality goals to set equality `{m | 0 < m /\ m <= n /\ coprime (m,n)} = {m | coprime (m,n) /\ m < n}`), `c * _`, a partially applied `(*) (p EXP b)` or `(EXP) (a * b)`, up to binders: `exists`/`select` goals turn into equality of the lambda bodies, e.g. a record leaves `(\y'. y' < n /\ (x * y' == gcd (n,y)) (mod n)) = (\y'. ...)` and a record peels one `exists` layer to `(\q1. exists q2. ...) = (\q1. exists q2. ...)`. It can also strip a conjunct that both sides share when it is the function part of the application, as in a record where `y' < n /\ P <=> y' < n /\ Q` becomes `P <=> Q`. It always yields exactly one subgoal and never touches the assumption list — every record here keeps assumptions like `prime p`, `~(n = 0)`, `x <= y` verbatim. Note it only removes the head; further argument structure must be handled by subsequent tactics (arithmetic, `EXTENSION`, `ABS_TAC`, etc.).
```

#### Help description (candidate B)

```text
SYNOPSIS
Strips a function application from both sides of an equational goal.

DESCRIBE
{<TACTIC>} reduces a goal of the form {A ?- f x = f y} by stripping away
the function applications, giving the new goal {A ?- x = y}.
{
    A ?- f x = f y
   ================  <TACTIC>
     A ?- x = y
}

FAILURE
Fails unless the goal is equational, with both sides being applications
of the same function.
```

#### Record shown to the judge

This is the complete saved judge-visible r1 object. JSON escapes such as
`\n` represent line breaks; `\\` represents a backslash.

```json
{
  "argument_names": [],
  "argument_types": [],
  "arguments": [],
  "goal_before": "\n  0 [`~(x <= y)`]\n\n`(exists q2. x + n * q1 = y + n * q2) <=>\n (exists q2. x - y + n * q1 = 0 + n * q2)`\n",
  "goals_after": [
    {
      "added_assumptions": [],
      "goal": "\n  0 [`~(x <= y)`]\n\n`(\\q2. x + n * q1 = y + n * q2) = (\\q2. x - y + n * q1 = 0 + n * q2)`\n",
      "removed_assumptions": []
    }
  ],
  "id": "r1",
  "subgoals_after": 1,
  "truncated": false
}
```

In plain words, the input has one assumption, `~(x <= y)`. Its conclusion
compares two existential statements. After the tactic, there is still one goal
with the same assumption, but the conclusion is now an equality between the two
lambda expressions. No assumptions were added or removed.

#### Saved scores and reasons

| Description | Judge label | Verdict | Score | Exact saved reason |
|---|---|---|---:|---|
| Relaxed-generated | C | full | 1 | `""` (empty; the prompt asks for no reason on full scores) |
| Official-generated | A | full | 1 | `""` (empty; the prompt asks for no reason on full scores) |
| Help | B | partial | 0.5 | Does not predict that an existential binder yields an equation between lambda bodies. |

The nonempty reason is the model's judgment, not a verified mathematical finding.
Both generated descriptions explicitly mention binders and the resulting lambda
equality. The Help text gives the more general rule `f x = f y -> x = y`.
That general rule can also describe the binder case when the expression is
viewed as a function application, so this deduction deserves manual review:
the lower Help score may reflect the judge's preference for explicit examples,
rather than an incorrect Help description.

The saved evidence comes from `input_tasks.jsonl` and `judgments.jsonl`;
the source-decoded verdicts and reasons were checked against
`summary.json → reasons → source → AP_TERM_TAC → official → r1`.
No new model call was made to produce this example.


## 2. Record-length metrics and charts

Added an offline analysis tool that measures record length in Unicode characters
and relates it to saved judge scores. It produces CSV tables and SVG charts for:

- Original corpus record-length distributions.
- Judge-visible record-length distributions.
- Coverage scores grouped by record length, with truncation tracked separately.

The existing `record-lengths-pilot-20260922-v2` analysis covers 727 original corpus
records and 80 judged record instances from the earlier two-description pilot.
These are different populations and should not be treated as paired raw and
rendered records.

This analysis is descriptive: it does not show that record length causes a
change in description quality. The current tool supports the older two-description
format and explicitly rejects the new three-description formats. Extending it
to the new run remains a next step.

## 3. Reproducible execution and review

Added `scripts/pipelines/llm_judge_tactic_desc.sh` with `--prepare`, `--judge`,
`--status`, and `--summary` stages. A judge preview does not call the model;
paid calls require `--execute`. Dry-run prints commands only. Saved plans keep
the records and candidate order fixed, and successful calls are skipped when
resuming. Failed calls require an explicit retry option.

Added plain-English comments, command examples, configurable environment
settings, and offline tests. The final related verification passed 139 tests,
including pipeline checks. Existing experimental outputs were kept out of the
commits, and original traces were not changed.

The work was split into five commits and three dependent PRs:

| PR | Scope |
|---|---|
| [#24](https://github.com/EngineeringSoftware/s2n-bignum-hol-light-llm/pull/24) | Help loading and the blinded three-description rubric |
| [#25](https://github.com/EngineeringSoftware/s2n-bignum-hol-light-llm/pull/25) | Separate-setting evaluation, batching, summaries, and earlier-format compatibility |
| [#26](https://github.com/EngineeringSoftware/s2n-bignum-hol-light-llm/pull/26) | Pipeline script, environment defaults, and documentation |

The remote PR head refs match the three prepared branches. They are not included
in the checked remote `main` snapshot. The intended review and merge order is
#24, then #25, then #26. Live review and CI status were not verified for this report.

The earlier record-grounded evaluator, record-length analysis, and judge rename
are already in remote main through PRs #17, #18, and #20.

## 4. TacticTrace lazy-argument work

The upstream change delays printing tactic arguments until trace output, so
arguments for discarded records do not need to be printed. The work is split
into two open draft PRs, verified from the upstream API:

- [TacticTrace #1](https://github.com/hol-light/TacticTrace/pull/1): lazy tactic-argument rendering.
- [TacticTrace #2](https://github.com/hol-light/TacticTrace/pull/2): regression coverage and documentation.

This week's work packaged the change for review and added test/documentation
support. The local test branch includes the bounded regression fixture and
plain-English test comments through commit `f1af563`.

The previously reported `mldsa_caddq` result was 1,549 s before and 639 s after,
with 414 trace files identical byte for byte. That is earlier benchmark evidence,
not a new full-campaign measurement this week. Broader validation is still needed.

## Next steps

1. Review and merge the three evaluation PRs in dependency order.
2. Add per-tactic, per-setting record verdicts and existing reasons to the Markdown
   report. This can use saved judgments without another paid model run.
3. Manually inspect low-scoring and ambiguous cases, including Help descriptions.
4. Extend record-length analysis to the three-description format and check whether
   longer records are associated with different coverage scores.
5. Plan held-out evaluation and a small order-sensitivity check before making
   broader claims about description quality.
6. Continue upstream TacticTrace review and wider validation when compute resources
   are available. New trace collection is separate from this completed evaluation.

## Local evidence

- Three-description experiment:
  `/home/tong-nong/s2n-bignum-hol-light-llm-help-judge/python/eval/out/llm-judge/help-separated-pilot-run1/`
- Earlier length analysis:
  `/home/tong-nong/s2n-bignum-hol-light-llm/python/eval/out/record-lengths-pilot-20260922-v2/`
- Earlier tracing benchmark: [September 17 report](sep17-report.md).

The experiment artifacts above are local outputs, not files supplied by cloning
the repository. This report does not include a new paid evaluation or trace run.
