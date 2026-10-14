# September 17 Q&A

## Tracing optimization: lazy arguments and conclusion-length ranking

### Q1. Are there data comparing the time before and after using `lazy` and adding a JSON field for the size of the `goal_before` conclusion?

There are before-and-after measurements for the `lazy` argument optimization, but the experiment did **not** add a conclusion-size field to the JSON. Therefore, the measured result is for lazy argument formatting alone, not for a combined "lazy plus new JSON field" change.

| Proof | Before: Config C | After: Config L (`lazy`) | Difference | Output check |
|---|---:|---:|---:|---|
| `mldsa_caddq` | 1,549 s | 639 s | 910 s faster; 58.7% reduction; 2.42x speedup | 414/414 trace files byte-for-byte identical |
| `bignum_mux` | 160 s | 162 s | No measurable improvement on this small proof | 352/352 trace files byte-for-byte identical |

Config C eagerly prints tactic arguments when each candidate record is built. Config L stores the argument computation as `Lazy.t` and prints arguments only for records that remain in the final list.

The experiment also tested whether calculating the conclusion length was the bottleneck. Config I estimated the length instead of running `string_of_term`; it took 1,573 s, compared with Config C's 1,549 s. This showed that conclusion-length calculation was not the main source of the slowdown. The expensive operation was formatting tactic arguments for candidate records that were later discarded.

The existing internal value is:

```ocaml
input_concl_str_len =
  String.length (string_of_term (snd tr.goal_before))
```

It is not currently serialized into JSON. Adding the already-computed integer to JSON would probably add little time, but this has not been benchmarked and should not be reported as a measured result.

### Q2. Where is `input_concl_str_len` stored, and is it used for ranking when the list is full?

The type declaration is:

```ocaml
type tac_record_interestingness = {
  input_concl_str_len: int
}
```

Each tactic record is stored in memory as a triple:

```ocaml
(tac_record, record_args, tac_record_interestingness)
```

The triples are stored in the `ExportTrace.tac_logs` hash table. The tactic name is the key, and the value is that tactic's list of records:

```ocaml
tactic_name
  -> (tac_record * record_args * tac_record_interestingness) list
```

When the list contains fewer than `max_num_records` records, the new record is added directly. When the list is full, there are two cases:

1. If every retained record has `input_concl_str_len < 100`, the new record is ignored. Its rank is not calculated because `mk_full_rec()` is not called.
2. Otherwise, the new record is added temporarily. The `N + 1` records are sorted by `input_concl_str_len`, smallest first, and the record with the largest value is removed.

For example, with a limit of three records:

```text
existing lengths: [40, 120, 200]
new length:        80
sorted:            [40, 80, 120, 200]
retained:          [40, 80, 120]
```

However, if the existing lengths are `[40, 70, 90]`, all are already below the threshold of 100. The code stops updating that tactic's list, even if a later record would have a still shorter conclusion. The policy therefore tries to collect enough short records; it does not guarantee that the final list contains the globally shortest records from the whole proof.

The same rank is also used to order the retained records immediately before writing the JSON, although the rank itself is not written to the file.

### Q3. How long does `input_concl_str_len` exist, and where is it kept?

The type declaration exists for the lifetime of the loaded `ExportTrace` module. Each actual integer value is created when `mk_tac_record_interestingness` is called while building a candidate record.

- If the record is retained, the integer remains reachable through `tac_logs` until the entry is replaced or the HOL Light process ends.
- If the record is discarded during selection, it is no longer reachable from `tac_logs` and can later be reclaimed by OCaml's garbage collector.
- `exptrace_dump` does not clear `tac_logs`. In the normal workflow it runs at the end of the proof, writes the JSON files, and then the proof process ends.
- Because `input_concl_str_len` is not serialized, it does not persist after the process ends.

### Q4. After the final list is selected, how are the tactic arguments turned into text?

In Config L, building a candidate record stores a suspended computation:

```ocaml
let mk_full_rec() =
  (re, lazy (re_arg_gen()), mk_i())
```

Here, `mk_i()` calculates the rank immediately because selection needs it. In contrast, `lazy (re_arg_gen())` does not run `re_arg_gen()` yet.

Ranking examines only the third element of the triple. If a candidate is later discarded, its lazy argument computation is never forced, so its arguments are never formatted as text.

At the end of the proof, `exptrace_dump` iterates over the records that survived and runs:

```ocaml
let r_args = Lazy.force r_args_lazy
```

The first `Lazy.force` executes `re_arg_gen()` and produces:

```ocaml
{
  names: string list;
  types: string list;
  values: string list;
  exprs: string list;
}
```

For example, a wrapper may convert a term argument with `string_of_term tm`. The resulting strings are then escaped and written as `arg_names`, `arg_types`, `arg_values`, and `arg_exprs` in the JSON. `Lazy.force` memoizes the result, so forcing the same value again does not rerun `re_arg_gen()`.

The sequence is:

```text
run tactic
-> calculate input_concl_str_len
-> store lazy re_arg_gen computation
-> select retained records by input_concl_str_len
-> discard unselected lazy computations without formatting them
-> finish the proof
-> call exptrace_dump
-> Lazy.force arguments of retained records
-> write JSON files
```

### Q5. Is the JSON generated only after the list is decided?

Yes, in the normal workflow. Records are collected and replaced in the in-memory `tac_logs` table throughout the proof. `modify-proof.sh` appends an `exptrace_dump` call to the end of the generated proof file. After the last proof command finishes, `exptrace_dump` sorts each retained list, forces the lazy arguments, and writes one `<TACTIC>.json` file per tactic.

There is no separate operation that permanently locks the lists. `exptrace_dump` writes their current state. Calling it at the end of the proof makes that state the final one in the normal workflow. If the proof fails before reaching `exptrace_dump`, the final JSON files will normally not be generated.

### Q6. Why is the first tactic in `TACTICS-official.md` missing from `TACTICS.md`?

The first tactic is `ABBREV_TAC`. It is not missing from our trace data; it is missing only from our generated description report.

`TACTICS.md` is not a complete inventory of the tactics found in the traces. The LLM pipeline first deduplicates each tactic's records and classifies the tactic by input size:

```text
raw traces
-> deduplicated records
-> phase classification
-> completed LLM descriptions
-> TACTICS.md
```

Only tactics with completed descriptions are written to `TACTICS.md`.

| `ABBREV_TAC` | Our limits | Upstream limits |
|---|---:|---:|
| Recorded applications | 2,285 | 659 |
| Distinct records | 576 | 75 |
| Estimated input tokens | 84,502,597 | 106,139 |
| Largest record | 10,853,954 tokens | 8,332 tokens |
| Pipeline classification | Phase 3 | Phase 1 |
| Description completed | No | Yes |

Our relaxed limits retain much larger proof states. One of our `ABBREV_TAC` records is estimated to exceed 10 million tokens, which is larger than the 400,000-token budget. The tactic is therefore assigned to phase 3, where individual records require truncation. Phase 3 has not been processed yet.

The upstream limits discard the very large states. Its remaining `ABBREV_TAC` evidence fits in phase 1, so the official description was generated successfully. This produces the apparently reversed result:

```text
Our traces:
ABBREV_TAC exists -> phase 3 -> not processed -> absent from TACTICS.md

Official traces:
ABBREV_TAC exists -> phase 1 -> processed -> present in TACTICS-official.md
```

All 43 descriptions currently present only in `TACTICS-official.md` also have records in our prepared index. Of those, 17 are waiting in phase 2 and 26 are waiting in phase 3. They represent unfinished LLM-description work, not missing raw tactic coverage.

The two Markdown files also cover different proof sets: the current `TACTICS.md` says 25 proofs, while `TACTICS-official.md` says 33. They therefore should not be used directly as the same-33-proof tactic-name comparison.

The four `ENSURES_WHILE_*` tactics are the opposite case: they appear in our report and are absent from the official report. However, the available relaxed records have only 5--11 assumptions, below the upstream `max_assumptions = 150` limit. Their exclusion is more consistent with the `maxcnt = 1000` term-size filter, although a controlled filter test is required to establish the exact cause.

### Q7. Is `ExportTrace.tac_logs` a folder or a data structure in the code?

`ExportTrace.tac_logs` is an OCaml data structure in memory. It is not a filesystem folder.

Its declaration is:

```ocaml
let tac_logs
  : (string,
     (tac_record * record_args * tac_record_interestingness) list)
    Hashtbl.t =
  Hashtbl.create 128
```

It is a hash table with this logical structure:

```text
key:   tactic name, such as "REWRITE_TAC"
value: the retained record list for that tactic
       [(tac_record, record_args, tac_record_interestingness); ...]
```

For example:

```text
"REWRITE_TAC" -> [record1; record2; record3]
"ABBREV_TAC"  -> [record1; record2]
```

`ExportTrace` is the OCaml module name and `tac_logs` is a variable inside that module. `Hashtbl.create 128` gives the hash table an initial size hint; it does not limit the table to 128 tactic names.

The table exists in the HOL Light process's memory. At the end of the proof, `exptrace_dump` reads it and creates the filesystem output:

```text
ExportTrace.tac_logs     in-memory OCaml hash table
out/traces/...           directory containing generated JSON files
```

## Implementation-state note

The C/L timing experiment used `max_num_records = 100`. At the time of this note, the currently modified local `hol-light/TacticTrace/exportTrace.ml` has `max_num_records = 10000` and still calls `re_arg_gen()` eagerly. Config L is recorded as an experimental patch in `s2n-bignum-hol-light-llm/experiment/patches.py`; it is not currently applied to the local `exportTrace.ml`.

## Relevant files

- `s2n-bignum-hol-light-llm/experiment/README.md`: configurations, timing results, and output comparisons.
- `s2n-bignum-hol-light-llm/experiment/patches.py`: the Config L lazy changes.
- `hol-light/TacticTrace/exportTrace.ml`: record storage, ranking, replacement, and JSON output.
- `hol-light/TacticTrace/kernel_wrapper.ml`: argument generators such as `string_of_term tm`.
- `hol-light/TacticTrace/modify-proof.sh`: appends `exptrace_dump` to the end of a proof.
