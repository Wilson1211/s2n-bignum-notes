# Tactic Description Pipeline

Turns HOL Light tactic traces from s2n-bignum proofs into English descriptions of
what each tactic does, using Claude on Amazon Bedrock.

```
traces/<proof>.ml/<TACTIC>.json        (read-only input, produced by TacticTrace)
      │  prepare.py     deduplicate; one file per tactic; classify by size
      ▼
dedup/<TACTIC>.jsonl + _index.json     (gitignored — ~8 GB)
      │  describe.py    one Bedrock call per tactic, smallest first
      ▼
descriptions.jsonl
      │  report.py
      ▼
TACTICS.md  (deliverable)  +  REPORT.md
```

## Scripts

| Script | Purpose | Calls AWS |
|---|---|---|
| `prepare.py` | Dedup traces, write one file per tactic, classify into phases | no |
| `describe.py` | Generate a description per tactic via Bedrock | **yes** |
| `report.py` | Render `TACTICS.md` and `REPORT.md` | no |
| `status.py` | Show pipeline progress, cost, what's next | no |
| `dedup_stats.py` | One-off analysis of duplication rates | no |

`describe.py` is the only script that touches AWS, and it opens a
**`bedrock-runtime`** client and nothing else.

## Usage

```bash
export AWS_PROFILE=lab          # credentials scoped to Bedrock only

python3 status.py               # where are we?
python3 prepare.py              # dedup + classify (local, free, ~3 min)
python3 describe.py --phase 1 --limit 5 --dry-run   # inspect prompts, no API call
python3 describe.py --phase 1   # generate descriptions
python3 report.py               # render TACTICS.md
```

Useful flags: `--model opus|sonnet|haiku`, `--tactic NAME`, `--limit N`,
`--effort low|medium|high`, `--max-tokens N`, `--threshold N` (prepare).

`descriptions.jsonl` is keyed by tactic name and appended to, so an interrupted
run resumes without repeating work or cost.

## Phases

Each call carries one tactic's records, bounded by `--threshold` (default 400K
tokens, against a 1M context window).

| Phase | Situation | Handling |
|---|---|---|
| 1 | all distinct records fit in one call | sent complete — no sampling, no truncation |
| 2 | too many records | stratified sample (see below) |
| 3 | a single record exceeds the budget | per-record truncation |

Phase 1 carries no methodological caveats, which is why it runs first. The phase
2 and 3 strategies are not yet settled.

### Sampling (phase 2)

Two passes. First, one record from every (proof, structural bucket) pair, rarest
bucket first — this guarantees uncommon behaviours (a tactic that closes the goal
in 1 of 121 records, say) survive. Second, round-robin across proofs and buckets
until the token budget is spent. A bucket is
`(subgoal count, assumptions added?, assumptions removed?, arguments passed?)`.

Without the first pass, sampling 71% of the records still missed 2 of 6 distinct
behaviours, because the largest bucket absorbed the whole budget.

## Cost

Measured on 25 proofs, phase 1: **167 tactics, $58.63, 29 minutes** (Opus 5,
`effort=low`). `describe.py` prints a running dollar total — the IAM user has no
Cost Explorer access, so that counter is the only meter.

Estimating tokens as `bytes / 3.5` **underestimates by ~24%** on this data;
multiply by 1.245.

## Notes for whoever picks this up

- `maxTokens` covers thinking *and* output on Opus 5. Setting it to 1200 left
  ~10 tokens for the answer after thinking consumed the rest. 8000 is the default
  here.
- Do not ask the model for JSON. HOL Light terms are full of backslashes
  (`\s.`, `/\`, `\/`) and escaping breaks — 7 of 167 responses were malformed
  before switching to plain prose.
- `max_num_records = 100` in `TacticTrace/exportTrace.ml` is the binding limit
  for roughly half the tactics, and its retention rule keeps the records with the
  *shortest* conclusions rather than the first N. Both bias what ends up here.
- 71% of raw records are exact duplicates, but removing them cuts only 5% of the
  bytes: the duplicates are small, the unique records are the huge
  symbolic-execution goals.
