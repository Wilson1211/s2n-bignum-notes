
| Parameter in exportTrace.ml  |  Official repo  |  Our setting  |  Purpose |
| --- | --- | --- | --- | 
| maxcnt | 1,000 | 1,000,000 | Maximum number of term nodes allowed in a recorded proof state |
| max_num_records | 20 | 100 | Maximum records retained per tactic in each proof |
| max_assumptions | 150 | 100,000 | Maximum assumptions allowed in the input and output goals |
| interesting_concl_strlen | 100 | 100 | Conclusion-length threshold used by the record-retention policy |

comparison of LLM generated result of official repo and our setting

file: 

s2n-bignum-hol-light-llm/result/TACTICS-official.md

s2n-bignum-hol-light-llm/result/TACTICS.md

## Time Spent
**A full run with upstream's sampling limits finished in a day.** The same 33 proofs took 22 hours under upstream's while we spent several days. But they record a quarter of the data, and four loop tactics disappear from the corpus entirely.


## Profiling

**The long proof times are the tracer, not the proofs.** On `mldsa_caddq`, 58% of the total is printing tactic arguments for records that are then thrown away. A small change makes that proof 2.4× faster.



### The rule step by step

Notation: a goal is a pair `(asl, w)`, where `asl` is the list of assumptions and `w` is
the conclusion, the statement still to be proved. 
The **goal before** is `(asl, w)`; 

The **goals after** are `[(asl₁, w₁), …, (aslₖ, wₖ)]`, where k can be 0. 

A record's
**rank** is `String.length (string_of_term w)`: the number of characters in the `conclusion
of *that record's own* goal before`, printed as text.

```
 goal before = (asl, w)
        │
        ▼
 [0] run the tactic
        │ fails (raises an exception) ────────────────────► not recorded
        ▼ succeeds
 goals after = [(asl₁, w₁), …, (aslₖ, wₖ)]
        │
        ▼
 [1] size check: on (asl, w) and on every (aslᵢ, wᵢ)
        │ if any of those goals has
        │   length(asl) > max_assumptions, or
        │   size of w > maxcnt ───────────────────────────► not recorded
        ▼ all pass
 [2] this tactic's list holds fewer than max_num_records records?
        │ yes (including the first record) ───────────────► build the record, add it
        ▼ no (the list is full)
 [3] every record in the list has rank < 100?
        │ yes ────────────────────────────────────────────► not recorded (the list never changes again)
        ▼ no (at least one ≥ 100)
 [4] build the record; with the list that makes N+1; sort by rank, smallest
     first; drop the last one (the longest)

        …… the last line of the proof file finishes ……

 [5] exptrace_dump: sort each tactic's list by rank and write <tactic>.json
```

```
 [4] only when the list is full (N records) and at least one rank is 100 or more
      │
      ├─ ① build the full record, mk_full_rec()
      │     ├─ print every argument, re_arg_gen()                  ◄── nearly all the time
      │     └─ compute the rank, mk_i(): print the goal before's
      │        conclusion w, measure it, throw the text away
      │        (the goal before (asl, w) and the goals after go into
      │         the record as they are, as HOL Light data, not printed)
      │
      ├─ ② add it to the list, N+1 records, and sort by rank       ◄── integer comparisons, cheap
      │
      └─ ③ drop the last record, the one with the largest rank     ◄── may be the new record itself
```

## Result

| Proof | Before | After: lazy | Output check |
|---|---:|---:|---|
| `mldsa_caddq` | 1,549 s | 639 s | 414/414 trace files byte-for-byte identical |


---

## Time spent


`mldsa_caddq`, our settings, 1,549 s total:

| | seconds | share |
|---|---:|---:|
| the proof itself | 203 | 13% |
| wrapper indirection | 185 | 12% |
| conversion recording | 172 | 11% |
| tactic size checks and retention | 93 | 6% |
| **tactic record replacement** | **896** | **58%** |

Once a tactic has collected its quota of records, every further application builds a full
record — which prints all of the tactic's arguments — then sorts and discards the longest.
The discarded record is often the one just built. Two configurations isolate the cost:
printing no arguments at all takes 644 s, and estimating the record's rank instead of
printing the goal takes 1,573 s, i.e. no saving. So the cost is argument printing, not
goal printing.

**Fix.** Keep the arguments unprinted until the traces are written, then print only the
records that survived (`lazy (re_arg_gen())`, forced in the dump). `mldsa_caddq` goes from
1,549 s to 639 s.

`max_assumptions = 150` discards most of these goals before a record is built.




## What the limits cost in data

Same 33 proofs:

| | our limits | upstream limits | kept |
|---|---:|---:|---:|
| tactic records | 291,204 | 76,426 | 26% |
| conversion records | 501,635 | 121,759 | 24% |
| distinct tactic names | 248 | 240 | 97% |
| distinct conversion names | 319 | 318 | 99.7% |
| trace size | 14 GB | 631 MB | 4.4% |

Upstream's limits keep a quarter of the records but almost the same *variety*: what is
lost is examples per tactic, not tactics. The exception matters, though — four tactics
have no records at all under upstream's limits:

```
ENSURES_WHILE_PAUP_TAC   ENSURES_WHILE_PDOWN_TAC
ENSURES_WHILE_PUP_TAC    ENSURES_WHILE_UP_TAC
```

These are the loop tactics, whose goals carry the most assumptions, so
`max_assumptions = 150` rejects every one of them. Raising that limit is what brings them
into the corpus.



##  Next step

- Send the PR to TacticTrace repo
- Collect cases when tactic is failing
- Use the HOL Light's HELP/ documents that records the descripion of the tactic of s2n-bignum as baseline
- Possible approach to deal with large size of triples: 
  - 1. summary the parameters in the theorem (currently there's only omit)
  - 2. some sampling and truncation strategy for the tactics that do not fit in one request.
- store the output in HuggingFace private repo



