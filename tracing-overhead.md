# Why the proofs take so long

*Measured 2026-09-12/13 on the lab server (32 cores, 124 GB). Every run was a single
container pinned to 4 CPUs; HOL Light proofs are single-threaded, so the runs are
comparable.*

## The question

Some s2n-bignum proofs were taking absurdly long — `mldsa_pointwise_acc_l7` ran for
56 hours, `mldsa_intt` for 54 — while others finished in minutes. The obvious suspicion
was that TacticTrace's logging was the cause rather than the proofs themselves.

**It is.** For the proof measured in detail, only 13% of the wall clock is the proof.
The other 87% is instrumentation. More than half of the total goes on printing tactic
arguments into text for records that are then thrown away. It took three guesses to get
there: first the `maxcnt` limit, then the pretty-printing of goals, and only then the
arguments. Keeping the arguments unprinted until the traces are written, so that only
the records finally kept get printed, makes the proof 2.4× faster (1,549 s to 639 s), and
the traces come out byte-for-byte identical.

## Ruling out the easy explanations first

**It is not the volume of trace output.** Across the 33 completed proofs, wall clock
and trace size are essentially uncorrelated (r = +0.10). The extremes go the wrong way:

| proof | wall clock | trace written |
|---|---:|---:|
| `mldsa_pointwise_acc_l7` | 56 h 23 m | 675 MB |
| `mldsa_rej_uniform_VARIABLE_TIME` | 0 h 45 m | 4.6 GB |

Seven times the output, seventy-five times faster. Traces are also written once at
process exit, not during the run.

**It is not the size of the code being verified.** Correlation with the `.text` size of
the object file is only r = +0.50, and two functions of almost identical size differ by
a factor of 324:

| proof | machine code | wall clock |
|---|---:|---:|
| `mldsa_pointwise_acc_l7` | 737 bytes | 56 h 23 m |
| `mlkem_unpack` | 759 bytes | 0 h 10 m |

**It is not simply the number of symbolic execution steps either.** Steps correlate
better (r = +0.71 on a log-log scale) but the cost *per step* varies about a
hundredfold:

| proof | steps | wall clock | per step |
|---|---:|---:|---:|
| `edwards25519_decode` | 3,357 | 0 h 43 m | 0.8 s |
| `mldsa_ntt` | 2,352 | 51 h 07 m | 78.2 s |
| `bignum_inv_p25519` | 2,293 | 1 h 03 m | 1.7 s |
| `mldsa_intt` | 2,280 | 53 h 55 m | 85.2 s |

`edwards25519_decode` does *more* steps than `mldsa_ntt` and finishes seventy times
sooner. The split is by family: ML-DSA and SHA-3 work on AVX2 vector state and cost
15–90 s per step; curve25519 and the generic bignums are scalar and cost 1–2 s.

That pattern — cost growing with the size of the proof state rather than the amount of
work — is what pointed at the instrumentation.

## Method

The same proof was compiled several times into differently-named binaries, so nothing
already built or recorded was disturbed, and each binary was timed on an otherwise idle
machine. Two proofs were used: `bignum_mux` (small, scalar) and `mldsa_caddq` (small
function but large vector state).

Every configuration that edited `exportTrace.ml` restored it and rebuilt the tracer on
the way out, so the environment ended exactly as it started.

| | what it changes |
|---|---|
| **A** | no tracing at all (`TRACE_DUMP_DIR` unset, so the proof is compiled uninstrumented) |
| **B** | tracing on, `maxcnt` back to the upstream 1,000 |
| **C** | tracing on with our settings: `maxcnt` 1,000,000, `max_num_records` 100, `max_assumptions` 100,000 |
| **D** | our settings but `max_assumptions` back to the upstream 150 |
| **E** | our settings but `max_num_records` back to the upstream 20 |
| **F** | our settings, but the tactic "interestingness" no longer calls `string_of_term`. Every length becomes 0, so every record looks interesting and the replacement branch stops running once the quota is full |
| **G** | the tactic record path returns immediately — tactics still wrapped, nothing recorded (conversions still recorded) |
| **H** | both the tactic and conversion record paths return immediately — everything wrapped, nothing recorded |
| **I** | our settings, but the tactic length is *estimated* from the term's structure instead of printed. Records are still compared and replaced |
| **J** | our settings, but records are built with empty argument lists instead of printing the tactic's arguments. Arguments play no part in the ordering, so exactly the same records are kept |
| **K** | the fix: our settings, but in the replacement branch the new record is sorted in with empty argument lists and gets its arguments printed only if it is kept. Output should be identical to C |
| **L** | our settings, but arguments are stored unprinted (`lazy`) and printed only when the traces are written, for the records finally kept. Same records kept; argument text could differ if a printing setting changed during the run |

Each configuration is **one change from C**, not a cumulative sequence: every run
restored `exportTrace.ml` to our settings before applying its single edit. H is the
exception — it disables both record paths, so it is two changes from C.

B, D, E, I, J, K and L are one-off probes. The other four happen to nest,
which is what makes the breakdown below meaningful:

```
H   tactics off,  convs off
G   tactics off,  convs on
F   tactics on, replacement branch off,  convs on
C   tactics on (full),  convs on
```

## Results

```
                                        bignum_mux    mldsa_caddq
A   no tracing                                85 s          203 s
H   wrapped, nothing recorded                 96 s          388 s
G   tactics silent, convs recorded               -          560 s
E   max_num_records = 20 (upstream)              -          565 s
D   max_assumptions = 150 (upstream)             -          583 s
L   arguments printed only at the end            -          639 s
J   C, but argument text not printed             -          644 s
F   lengths forced to 0: no replacement          -          653 s
K   the fix: arguments printed if kept           -          673 s
B   maxcnt = 1000 (upstream)                 116 s         1492 s
C   our settings, everything on              156 s         1549 s
I   C, length estimated instead of printed       -         1573 s
```

`bignum_mux` is 1.8× slower with tracing. `mldsa_caddq` is **7.6×** slower. The
overhead is not a fixed percentage: it grows with the size of the proof state, which is
why the ML-DSA and SHA-3 proofs suffer and the scalar ones barely notice.

### Where the 1,549 seconds go

Because H, G, F and C nest, the differences between them attribute the runtime to one
component each. (They sum to the total by construction — that is arithmetic, not
evidence. What makes the attribution valid is the nesting.)

| | seconds | share |
|---|---:|---:|
| the proof itself | 203 | 13% |
| wrapper indirection (A → H) | 185 | 12% |
| conversion recording (H → G) | 172 | 11% |
| tactic size checks and retention (G → F) | 93 | 6% |
| **tactic record replacement (F → C)** | **896** | **58%** |
| total | 1,549 | 100% |

Config J later showed that nearly all of that last row is argument printing (see below).

## How TacticTrace chooses which records to keep

Everything below leans on this, so it is worth being exact. The rule is TacticTrace's own
design, in `exportTrace.ml`; nothing in this investigation changed it. The campaign only
raised three numeric limits: `max_num_records` 20 → 100, `max_assumptions` 150 → 100,000,
and `maxcnt` 1,000 → 1,000,000. Each tactic application goes through two separate steps,
and it is easy to blur them.

**1. Is it recorded at all?** `is_goal_too_large` looks at the goal before the tactic and
at every goal after it. A goal is too large if it has more than `max_assumptions`
assumptions, or its conclusion has more than `maxcnt` term nodes. If any is too large,
the application is not recorded. This step does look at assumptions and at the output
goals, but only to filter, never to rank. For conversions the filter looks only at the
input term's size.

**2. Which records are kept?** Each tactic keeps at most `max_num_records` records, ranked
by one number:

```ocaml
type tac_record_interestingness = {
  (* The length of string_of concl of goal_before. Shorter is better *)
  input_concl_str_len: int
}
let mk_tac_record_interestingness (tr:tac_record) =
  { input_concl_str_len = String.length (string_of_term (snd tr.goal_before)) }
```

A goal is a pair (assumption list, conclusion), and `snd` takes the conclusion. The rank is
the printed length of **the conclusion of the goal before the tactic**, and nothing else.
I first quoted only "Shorter is better" from that comment, which made it easy to read the
rank as the length of the whole triple. It is not.

A real record from `bignum_mux` makes it concrete:

```
  0 [`forall x y. R x y ==> P x y`]             <- assumption: not counted
  1 [`forall x y. P x y ==> P y x`]             <- assumption: not counted
  2 [`forall x y z. P x y /\ P y z ==> P x z`]  <- assumption: not counted

`forall x y. STC R x y ==> P x y`               <- conclusion: counted, 31 characters
```

The tactic was `REWRITE_TAC`, with the argument `[(|- forall R. STC R = TC (SC R))]`,
which does not count either. During the run none of this is text: goals, conclusions and
arguments are HOL Light term trees. The text above is what gets written to the JSON.

| part of the triple | counts towards the rank |
|---|---|
| conclusion of the goal before | **yes** |
| assumptions of the goal before | no |
| the goals after | no |
| the tactic and its arguments | no |

Once a tactic has its quota, each new record is added and the longest of the 101 dropped,
unless every kept record is already under 100 characters; from then on nothing changes.
Conversions follow the same scheme, ranked by the printed length of their input term, with
50 characters as the threshold.

Consequences:

- **"Shortest" means shortest conclusion, not smallest proof state.** June's email puts it
  as the smallest items "in terms of the input proof state", which is looser than the
  code. Assumptions are ignored, so a goal with hundreds of them can still rank as short.
  The records C kept on `mldsa_caddq` include one with 525 assumptions. Symbolic execution
  piles up assumptions, so what this rule selects is not necessarily a small proof state.
  Its effect on which examples end up in the dataset has not been measured.
- **The rank needs the conclusion printed, not the arguments.** The conclusion is printed
  to measure it as each record is built, in C and in every fix, K and L included. Config I
  tried estimating the length without printing, and that changed which records were kept
  (23 of 70 all-short against C's 46). The arguments play no part in the rank at all, which
  is why L can leave them unprinted until the end and still produce identical output.

### The rule step by step

Notation: a goal is a pair `(asl, w)`, where `asl` is the list of assumptions and `w` is
the conclusion, the statement still to be proved. The **goal before** is `(asl, w)`; the
**goals after** are `[(asl₁, w₁), …, (aslₖ, wₖ)]`, where k can be 0. A record's
**rank** is `String.length (string_of_term w)`: the number of characters in the conclusion
of *that record's own* goal before, printed as text.

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

[0] happens in the wrapper and [5] in `exptrace_dump`; [1] to [4] are `exptrace_add_tac`.
[1] is step 1 above, "Is it recorded at all?", and [2] to [4] are step 2, "Which records
are kept?". They are also the four cases used in "What a fix would look like" below. The size of a conclusion
counts every variable, constant and numeral as 1, and each lambda abstraction adds 1.

**Which record [4] drops.** The one with the largest rank: the record whose goal-before
conclusion `w`, printed as text, is longest. How many assumptions it has, how long they
are, its goals after and its arguments play no part. Each record's rank is computed once,
when that record is built in [2] or [4], and stored as an integer; later replacements
compare the stored integers. The new record itself is dropped if its rank is larger than
every kept record's.

**Ties.** Two records of the same tactic come from different calls, each with its own goal
before. They tie when their conclusions `w_A` and `w_B`, different terms, happen to print
to the same number of characters. OCaml's `List.sort` is stable (`let sort = stable_sort`,
`list.ml:436` in the 5.4 standard library), and new records always go in at the front of
the list (`mk_full_rec()::records`), both while the list fills and in [4]. So among records
tied for the largest rank the newer ones come first, and the one dropped is the oldest of
them. A new record that ties with the longest stays. How often a tie decides which record
is dropped has not been measured.

## What is actually slow

In terms of the flowchart in "The rule step by step", almost all of the time goes on
**step [4]**, and within it on **printing the new record's arguments before the sort and
the drop**. On `mldsa_caddq` under C (1,549 s), the nested configs split the time roughly
by step:

| part | step | seconds | share |
|---|---|---:|---:|
| the proof itself | none | 203 | 13% |
| wrapper indirection (A → H) | [0] | 185 | 12% |
| conversion recording (H → G) | the conversion rule | 172 | 11% |
| tactic size checks and retention (G → F) | mostly [1] to [3] | 93 | 6% |
| **tactic record replacement (F → C)** | **mostly [4]** | **896** | **58%** |

The step column is approximate. F never reaches [4], but it also stops measuring the rank
in [2], and C and F write different records in [5].

What [4] does, every time it runs:

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

- **[4] does no filtering of its own.** The conditions that decide whether a call is
  handled at all come earlier: [1] rejects goals that are too large, and [3] skips once
  every kept record is short. A call that reaches [4] always goes through print, sort,
  and drop one.
- **Printing the arguments and computing the rank are a single step.** Both happen in
  `mk_full_rec()`, before the sort. OCaml leaves the evaluation order of a tuple's parts
  unspecified, and here it does not matter which comes first.
- **The time is argument printing, not goal printing.** Config J removes only the
  argument printing and keeps exactly C's records, so [5] prints the same goals in both.
  J took 644 s against C's 1,549 s. The goals are printed only in [5], for the records
  finally kept.
- **Argument size never affects which records are kept.** It decides only how long the
  printing takes and what text goes into `arg_values`; [1] to [4] never look at it.

"Printing every argument" costs very different amounts depending on the argument's type.
The ~900 s is spent on theorems and terms; how it splits between the two has not been
measured.

| argument type | how it is printed | cost |
|---|---|---|
| theorem (`thm`, `thm list`) | `string_of_thm` in full; only afterwards is text over 1,000 characters replaced by `(omitted thm)` | part of the ~900 s; the printing is paid even when the text is replaced |
| term | `string_of_term` in full, with no length limit | part of the ~900 s |
| function (`conv`, `thm -> tactic`, ...) | cannot be printed; the fixed string `(don't know how to express)` is written instead | almost none |

Why that costs so much:

1. **Theorem and term arguments are printed in full,** a theorem even when its text is
   then replaced by `(omitted thm)`. How large the arguments of the dropped records are
   is not known; see "Chasing the `(omitted thm)` idea" below.
2. **The text is often thrown away at once.** If the new record's conclusion is longer
   than every kept one, the new record is the one dropped, right after its arguments were
   printed. A record that stays can still be replaced later, and then its printing was
   wasted too.
3. **[4] runs on almost every call once a list is full.** It stops only when every kept
   record is short, and that state is permanent. On `mldsa_caddq`, 24 of the 70 tactics
   that filled their list never reached it, so every later call of those tactics went
   through [4].

The evidence in brief: J, which prints no arguments and otherwise matches C, took 644 s.
I, which estimates the rank instead of printing `w`, took 1,573 s, no faster than C. L,
which prints arguments only for the records finally kept, took 639 s. Upstream's settings
hide most of this, because `max_assumptions = 150` stops most ML-DSA goals at [1], before
they can reach [4] (config D, 583 s); see "Upstream code, exposed by our settings" below.

The rest of this section shows how each part was established.

Every tactic application that survives the size check goes through this (from
`exportTrace.ml`, simplified):

```ocaml
let mk_full_rec () = (re, re_arg_gen (), mk_i ())      (* prints arguments and goal *)
if List.length records < max_num_records then add (mk_full_rec ())
else if all_tac_records_interesting records then ()    (* all kept records < 100 chars *)
else keep the shortest 100 of (mk_full_rec () :: records)   (* sort 101, drop one *)
```

Once a tactic has 100 records, every further application takes the last branch until
all 100 kept records are short. After that nothing can change them, so the tactic never
takes the branch again. On `mldsa_caddq`, 24 of the 70 tactics that filled their quota
never got there (their final records are not all short, and that state can only be
reached, never left), so every later use of those tactics went through the branch. The
other 46 got there at some point, which the final records cannot date. The branch builds
a full record, printing the tactic's arguments and the goal's conclusion, then sorts 101
records and throws the longest away. That is either the new record, wasting all the
work, or an old one, which the new record replaces.

How often each happens was not measured directly. K and J give a rough idea: K prints
arguments only for records that survive and costs 29 s more than J, which prints none,
while C prints them for every record and costs about 900 s more. So survivors are a small
share, assuming kept and dropped records carry similar arguments, which is unverified.

This explains a puzzle in the results table. Every one-factor config from D to H is
roughly 900 s faster than C even though they change completely different things. They
are not removing separate costs. Each one switches off, or shrinks, this same branch by a
different route:

- **D** rejects the big-assumption goals at the size check, before they reach the branch.
  The largest goal it kept had 70 assumptions, against 525 in C.
- **E** keeps only 20 records, so every sort and scan is five times smaller. Twenty short
  records are also easier to collect than a hundred, so more tactics stop replacing
  early: 65 of 92 full tactics ended with all records short, against 46 of 70 in C.
- **F** makes every length 0, so every record is "interesting" and the branch never runs
  again. It ended with 1 of 70 all-short, because it simply kept the first 100.
- **G** and **H** return before any of it.
- **B** only changes a check that ML-DSA goals pass anyway, so it looks just like C.

The 896 s between F and C is therefore the cost of **the branch as a whole**, not of one
function in it.

The first suspect inside the branch was the goal printing:

```ocaml
input_concl_str_len = String.length (string_of_term (snd tr.goal_before))
```

That is HOL Light's full pretty-printer (precedence, bracketing, infix, type annotations),
run only to read one integer off the resulting string. It looked like an obvious waste.
Config I tested it by keeping everything as in C but estimating the length from the
term's structure instead of printing it. **I took 1,573 s against C's 1,549 s**, so there
was no saving at all. The goal printing is not the cost.

That left two candidates inside the branch: printing the tactic's arguments
(`re_arg_gen`, which also calls `string_of_term`) and sorting 101 records on every call.
Config J separated them by building every record with empty argument lists and changing
nothing else. It kept exactly the records C kept (46 of 70 full tactics ended all-short
in both), so this comparison is clean. **J took 644 s against C's 1,549 s**, about the
same as F, where the branch does not run at all. So nearly all of the branch's cost is
argument printing. The sort and the goal printing are too cheap to measure.

Which tactics carry the expensive arguments is still unknown. I looked at the arguments
of the records C kept: the largest is about 2,400 characters (a theorem list passed to
`METIS_TAC`), and most are a few hundred. But the kept records are the survivors, chosen
for their short goals. The records built and dropped in the replacement branch are not
saved anywhere, so their arguments cannot be inspected from the traces.

### What "printing the arguments" actually means

A tactic's arguments are HOL Light values, not text. A term like `word_add a (word 736)`,
or a theorem, is a tree in memory. JSON only holds strings, so the generated wrapper in
`kernel_wrapper.ml` turns every argument into text with HOL Light's printer the moment
the record is built:

```ocaml
(* ABBREV_TAC: its argument is a term *)
values = [ "`" ^ (string_of_term tm) ^ "`" ]

(* REWRITE_TAC: its argument is a list of theorems *)
values = [ ... string_of_thm x ... if String.length s > 1000 then "(omitted thm)" else s ... ]
```

The printer walks the whole tree and works out brackets, operator placement and type
annotations. For REWRITE_TAC the theorems are the arguments themselves; there is nothing
extra besides them. The order matters: each theorem is printed in full, and only then is
a string over 1,000 characters swapped for `(omitted thm)`. The printing is paid for
even when its result is thrown away.

### Two lengths that are easy to confuse

| | measures | used for | cost |
|---|---|---|---|
| conclusion length | the goal's conclusion | choosing which 100 records to keep | cheap (config I) |
| 1,000-character check | each theorem argument | keeping over-long text out of the JSON | the printing done before it |

Which records are kept depends only on the conclusion length. The arguments play no part
in it, which is exactly why K can skip them for records that will be dropped.

The purpose of each step, for the record: the quota keeps the 100 records with the
shortest conclusions because TacticTrace's authors chose "shorter is better" (it says so
in a comment in `exportTrace.ml`; June's email describes it more loosely, as the smallest
input proof state). Arguments are turned
into text only because they have to be written into the JSON's `arg_values` field.

### Root cause, stated precisely

**Arguments are printed the moment a record is built. Once a tactic's quota is full,
every new record gets its arguments printed before it is compared with the 100 already
kept, and most new records are then dropped, so that printing is wasted.** J and K
establish this: J (no argument text, identical retention) took 644 s, and K (arguments
printed only for records that survive) took 673 s with byte-identical traces.

It is *not* established that the waste comes mainly from huge theorems.

### Chasing the `(omitted thm)` idea

The order in the REWRITE_TAC wrapper suggested an explanation for the puzzle above: huge
theorems get printed in full and then replaced by `(omitted thm)`, so their cost would
never show up in the arguments of kept records. I counted `(omitted thm)` to test that.

In `mldsa_caddq`'s config C traces (kept records only):

| | tactic | conversion |
|---|---:|---:|
| records | 8,555 | 14,370 |
| records with a theorem argument | 3,577 | 1,763 |
| records containing `(omitted thm)` | 90 | 222 |
| `(omitted thm)` occurrences | 99 | 2,896 |

For tactics it is rare, about 2.5% of the records with a theorem argument, so the idea
found no support there. Conversions are another matter: `X86_CONV` has it in 94 of its 100
kept records, about 16 per record, with `ALIGNED_WORD_CONV` and
`X86_FORCE_CONDITIONAL_CONV` next at 684 each. But all conversion recording together cost
only 172 s on this proof, so that is not the main cost either.

Across the campaign's traces (27 s to grep, 44 proof directories), the count per proof
runs from 72 (`bignum_mux`) to 12,630 (`mlkem_ntt`); the `mldsa_caddq` total of 2,995
matches the experiment's own traces exactly. The 11 tutorial proofs were left out of the
comparison, because they were traced with the old `max_num_records = 10000` and keep far
more records. For the 33 campaign proofs, the count correlates only moderately with
runtime: Pearson +0.37, log-log +0.61, rank +0.53. The exceptions are stark:

| proof | `(omitted thm)` | runtime |
|---|---:|---:|
| `mldsa_pointwise_acc_l7` | 1,977 | 56 h 23 m (4 h 9 m of it paused) |
| `mlkem_basemul_k2` | 8,597 | 1 h 31 m |
| `mldsa_rej_uniform_VARIABLE_TIME` | 5,381 | 45 m |

So the count does not predict runtime. The moderate correlation is probably both growing
with proof size, like the earlier moderate correlations with code size and step count.

None of this rules the idea out for tactics, because the records dropped in the
replacement branch are exactly the ones the traces do not contain. Settling it needs
counting at the moment records are built, dropped ones included: characters printed per
tactic's arguments, and theorems omitted. The fix does not depend on the answer: K and L
both skip the printing for every dropped record, whatever size its arguments are.

## The tunable constants do not fix this

The four compile-time constants in `exportTrace.ml` are all *post-hoc filters*: the
record is built first, then they decide whether to keep it.

| constant | what it gates | effect on `mldsa_caddq` |
|---|---|---|
| `max_assumptions` | drops a goal carrying more assumptions than this | 1,549 → 583 s |
| `max_num_records` | how many records to keep per tactic | 1,549 → 565 s |
| `maxcnt` | term nodes in the *conclusion* before it counts as too large | 1,549 → 1,492 s |
| `interesting_concl_strlen` | which records survive once the quota is full | selection only |

`maxcnt` barely moves the needle because it only measures the **conclusion**, and what
is large in s2n-bignum is the **assumption list** — median 178 assumptions, 242 at the
90th percentile. ML-DSA goals sail through that check whatever `maxcnt` is set to.

The two constants that do help only help by **recording less**. `max_assumptions = 150`
is exactly the upstream default that discarded essentially all of s2n-bignum in the
first place. So they buy speed by giving up the data, which is not a trade worth making.

And the floor is 2.8× no matter how they are set: wrapping every tactic and building the
record happens before any constant is consulted.

## Upstream code, exposed by our settings

The expensive branch is TacticTrace's own code. But it only runs for goals that get past
the size check, and our raised limits are what let the ML-DSA goals through. With
upstream's `max_assumptions = 150` (config D) the run takes 583 s, because most of those
goals are discarded before they are recorded, along with the data this project needs.
`maxcnt` on its own (config B) makes only a 4% difference.

An earlier version of this note said config B had every constant at its upstream default,
and concluded that upstream settings were just as slow. That was wrong: B resets only
`maxcnt`, and the other two limits stay at our values.

## What a fix would look like

There are two candidates, both measured, and L is the better one.

**K: print a record's arguments only if it survives the cut.** The new record is sorted in
with an empty argument list, and its arguments are printed only if it is still there
afterwards. It prints when the tactic runs, as C does.

```ocaml
      let new_records = List.sort
          (fun (_,_,i1) (_,_,i2) -> ExportTrace.compare_tac_interestingness i1 i2)
          ((re, {ExportTrace.names = []; ExportTrace.types = []; ExportTrace.values = []; ExportTrace.exprs = []}, mk_i())::records) in
      let new_records = rev (tl (rev new_records)) in
      let new_records = List.map
          (fun ((r,_,i) as x) -> if r == re then (r, re_arg_gen(), i) else x) new_records in
      Hashtbl.replace logs tactic_name new_records
```

The `List.map` finds the new record by physical identity (`r == re`). Each tactic
application passes in a freshly built record, so it cannot match an older one. The flaw:
a record can survive the cut now and be replaced later, and then its printing was wasted.

**L: keep the arguments unprinted until the traces are written.** This was the user's
idea: store the arguments, and only print them once it is known which records are final.
Deciding which records to keep never looks at the arguments, only at the conclusion
length, so nothing about retention changes.

Reading the code for it turned up a comment showing that TacticTrace's authors already
delay the printing part of the way:

```ocaml
(* Separate record_args to lazily evaluate this (otherwise it takes too long) *)
```

`re_arg_gen` is a function so that printing can wait. The arguments are printed wherever
`exptrace_add_tac` calls `mk_full_rec()`, because that is what calls `re_arg_gen()`. Laid
over the retention rule, every tactic application ends in one of four cases:

```
1. a goal fails the size check        -> return, no mk_full_rec()   -> arguments not printed (saved)
2. the tactic's list is not yet full  -> mk_full_rec(), add it      -> arguments printed
3. list full, every kept record's     -> skip                       -> arguments not printed (saved)
   conclusion under 100 characters
4. list full, some conclusion of 100  -> mk_full_rec(), sort,       -> arguments printed, for nothing
   characters or more                    drop the longest              if the new record is dropped
```

Case 1 is step 1 of the rule, "Is it recorded at all?"; cases 2 to 4 are step 2. A tactic's
first record also goes through `mk_full_rec()` and counts as case 2.

So the upstream delay saves the printing only in cases 1 and 3. In case 4 the order is the
problem: print first, then sort and drop.

```ocaml
let mk_full_rec() = (re, re_arg_gen(), mk_i()) in            (* build a record: print its arguments *)
...
let new_records = List.sort ... (mk_full_rec()::records) in  (* print, then sort ... *)
let new_records = rev (tl (rev new_records)) in              (* ... then drop the longest *)
```

Printing in case 2 can be wasted as well, since a record added while the list fills may be
replaced later in case 4.

The rank, `mk_i()`, is computed at the same points, in cases 2 and 4 only. L leaves it
there, because case 4 needs it to sort.

L takes the printing out of cases 2 and 4 and does it at the very end, with small changes
to the tactic path: the record type holds `record_args Lazy.t`, a record is built with
`lazy (re_arg_gen())`, and the dump code does `Lazy.force` before printing (plus the
matching type annotation on `all_tac_records_interesting`).

An earlier version of this note said the authors "meant this all along" and that
`exptrace_add_tac` "calls it immediately", as if the delay never happened. That overstated
it: the delay is real, it just stops too early.

### What L does in each case

With L, the same four cases:

```
1. a goal fails the size check        -> return, nothing built                    (as upstream)
2. the tactic's list is not yet full  -> build the record with its arguments
                                         unprinted, add it
3. list full, every kept record's     -> skip                                     (as upstream)
   conclusion under 100 characters
4. list full, some conclusion of 100  -> build the record with its arguments
   characters or more                    unprinted, sort, drop the longest
```

No case prints the arguments, but cases 2 and 4 still do everything else: they build the
record, compute its rank, sort and drop. Computing the rank is unchanged from upstream and
still happens when the tactic runs:

```ocaml
input_concl_str_len = String.length (string_of_term (snd tr.goal_before))
```

`snd tr.goal_before` is the conclusion of the goal before the tactic, `string_of_term`
prints it to text, `String.length` counts the characters, and the text is thrown away. The
arguments' length is never measured, in upstream or in L, which is why their printing can
wait. Only the arguments are held differently: instead of text, `lazy (re_arg_gen())`, a
call that has not run yet and still holds the original terms and theorems.

The lists are final only when the proof has finished. TacticTrace's `modify-proof.sh` adds
one line to the end of every instrumented proof file:

```ocaml
exptrace_dump "<dir>";;
```

So the dump runs after the last line of the proof. For each record still in a list it
calls `Lazy.force`, which prints the arguments, and writes them to the JSON together with
the goals, which are printed at the same point. A record dropped along the way never has
its arguments printed.

Two limits:

- Only the tactic path is changed. Conversions still print their arguments as soon as a
  record is built. All conversion recording together cost 172 s on `mldsa_caddq` (H → G).
- L is an experiment configuration, not what the campaign runs. The campaign's tracer on
  Tokyo is still upstream, and `trace-overhead.sh` restored `exportTrace.ml` when it
  finished. Using L for real means deciding to adopt it, rebuilding the tracer and
  recompiling the proofs. And because the arguments are printed at the end, a printing
  setting changed during the proof could change their text; see the risk paragraph under
  Results below.

### Three ways to time the printing

| | When the arguments are printed | Printed for nothing | `mldsa_caddq` | Where it is |
|---|---|---|---|---|
| Eager | every time a wrapped tactic runs, in all four cases | every record not finally kept, even those rejected in case 1 | not measured | not in git |
| Upstream | when a record is built, in cases 2 and 4 (in case 4, before the drop) | records dropped straight away in case 4, and records kept for a while and replaced later | 1,549 s (C) | commit `9b56951`; what the campaign runs |
| L | when the traces are written, for the records finally kept | nothing | 639 s | this experiment only |

Eager is only a reference point. No version in git works that way; the comment's
"otherwise it takes too long" hints that the authors tried something like it before
committing, but that is a guess.

It is easy to read "the authors already delay it" as a fix the campaign failed to pull. It
is not. `9b56951` (2025-08-22) is the commit that added TacticTrace, and the delay and the
replacement branch both came with it. The only later commit to touch `exportTrace.ml`,
`b8ca210` (2025-11-20), deletes four unrelated lines: an unused helper and one line of the
conversion output. GitHub has nothing newer (checked 2026-09-15). The campaign's checkout
on Tokyo (`2a1cea8`) contains both commits, and its only local changes to the file are the
three constants. So the upstream row is exactly what produced the 1,549 seconds, and no
pull would have avoided them.

K, above, sits between upstream and L. It prints a new record's arguments only if the
record survives the cut, so records dropped straight away cost nothing, but a record
replaced later was still printed for nothing: 673 s against L's 639 s.

### Step by step: upstream and L

The steps are those of "The rule step by step" above.

| Step | Upstream repository | L, with the campaign's constants |
|---|---|---|
| [0] tactic fails | not recorded | same |
| [1] assumption limit, `max_assumptions` | not recorded if any checked goal has more than 150 assumptions | not recorded if any checked goal has more than 100,000 |
| [1] conclusion size limit, `maxcnt` | not recorded if any checked goal's conclusion is larger than 1,000 | not recorded if larger than 1,000,000 |
| [1] goals checked | the goal before `(asl, w)` and every goal after `(aslᵢ, wᵢ)` | same |
| [2] list limit, `max_num_records` | 20 | 100 |
| [2] goal before `(asl, w)` and goals after `[(aslᵢ, wᵢ)]` in the record | kept as HOL Light data, not printed | same |
| [2] rank | `w` printed, measured, text thrown away | same |
| [2] arguments | **printed to text now and stored in the record** | **not printed**; stored as an unevaluated `lazy` |
| [3] skip when the list is all short | every rank < 100: skip, nothing built | same |
| [4] rank of the new record | `w` printed, measured, text thrown away | same |
| [4] sort and drop | sort by rank, drop the largest (the oldest among ties) | same |
| [4] arguments | **printed before the sort**; wasted if the new record is the one dropped | **not printed**; stored as `lazy` |
| [5] goal before `(asl, w)` and goals after | printed with `pp_print_goal`, assumptions and conclusion | same |
| [5] added and removed assumptions | for each goal after: added = `aslᵢ` minus `asl`, removed = `asl` minus `aslᵢ` | same |
| [5] arguments | the text made in [2] or [4] copied in | **printed now with `Lazy.force`**, for the kept records only |

- **L changes no filter.** The different numbers in [1] and [2] are the campaign's
  constants, raised before this experiment, and have nothing to do with L. L changes only
  what happens to the arguments in [2], [4] and [5].
- **The campaign today runs the upstream code with the campaign's constants.** L has only
  been run in this experiment.
- **What decides retention:** in [1], the number of assumptions and the size of the
  conclusion of the goal before and of every goal after; in [3] and [4], the rank, which is
  the printed length of the goal before's conclusion `w` alone. What the assumptions say
  and the arguments never matter.
- **Conversions** follow a separate rule that L leaves alone: [1] checks only the size of
  the input term, results of the form `t = t` are skipped, the rank is the printed length
  of the input term, and the threshold in [3] is 50.

### How a record is stored, before and after L

A record is the triple: the goal before the tactic, the tactic with its arguments, and the
goals after. L changes only how the arguments are held while the proof runs; the JSON
written at the end is the same.

**Now (C).** When a tactic application passes the size check and a record is built:

| part | held as |
|---|---|
| goal before (`goal_before`) | HOL Light data: the assumption list and the conclusion as term trees, not text |
| goals after (`goals_after`) | the same, not text |
| tactic name | text, such as `"REWRITE_TAC"` |
| **arguments** | **printed to text straight away**; a theorem over 1,000 characters becomes `(omitted thm)` |
| rank | one integer: the conclusion is printed, measured, and the text thrown away |

When the proof finishes, only the kept records are written out: both goals are printed,
the added and removed assumptions worked out, the argument text made earlier copied in,
and the JSON written. The waste is in the arguments row. Every new record gets its
arguments printed, and most of those records are dropped soon after.

**With L.**

| part | held as |
|---|---|
| goal before, goals after | unchanged: HOL Light data |
| tactic name | unchanged: text |
| **arguments** | **not printed**: a lazy value still holding the original terms and theorems |
| rank | unchanged: the same integer, with the conclusion still printed to measure it |

At the end, `Lazy.force` prints the arguments of the kept records, and everything else is
produced as before. A dropped record never has its arguments printed.

```
now:    arguments printed when a record is built       -> dropped records printed for nothing
L:      arguments printed when the traces are written  -> only the records that are kept
goals:  printed when the traces are written, in both versions
```

L makes the arguments follow the rule the goals already followed. K sits in between: the
new record is sorted in with empty arguments and, if it survives, printed immediately. A
record that survives and is replaced later was then printed for nothing, which is the 34 s
between K and L.

### What ends up in the JSON

Neither K nor L changes it. A `REWRITE_TAC` record from `bignum_mux`:

```json
{
  "tactic": "REWRITE_TAC",
  "arg_values": ["[(|- forall R. STC R = TC (SC R))]"],
  "goal_before": "\n  0 [`forall x y. R x y ==> P x y`]\n  ...\n\n`forall x y. STC R x y ==> P x y`\n",
  "goals_after": [ {"goal": "...", "added_assumptions": [...], "removed_assumptions": [...]} ],
  ...
}
```

**The conclusion has no field of its own.** `goal_before` is a single string: the numbered
assumptions, a blank line, then the conclusion in backticks. Getting the conclusion out
means taking the last backtick-quoted piece of that string.

**The rank is not written out, and recomputing it from the JSON is only approximate.** The
number TacticTrace ranked by lived in memory and was never saved. The records in each file
are at least written in rank order, shortest conclusion first (the dump code sorts them
with `tac_rec_comp` before writing), so the order survives even though the numbers do not.
Measuring the conclusion from `goal_before` afterwards can give a different number, for two
reasons:

- *Layout.* The rank was the length of `string_of_term`'s output. `goal_before` is laid out
  by `pp_print_goal`, which breaks long terms over several lines and indents the
  continuation, as in this assumption from an `mldsa_caddq` record:

  ```
    1 [`forall s' n'.
            n' < n1 /\ steps step n' sb0 s' ==> (exists s''. step s' s'')`]
  ```

  The characters of the term are the same, but the newlines and indentation differ, and
  `String.length` counts them. A conclusion short enough for one line comes out the same
  either way; a long one does not. The "31 characters" quoted earlier was measured with the
  whitespace squeezed down to single spaces, so it is an approximation too.
- *Printing settings.* The rank was measured when the tactic ran, but `goal_before` is
  printed at the end. If a printing setting changed in between (the same
  `override_interface` and `parse_as_infix` changes that make up L's risk), the text itself
  can differ. The original version of this explanation missed this.

This only matters for someone reconstructing, from the JSON, which records would have been
kept. Records with close lengths, or near the 100-character threshold, are the ones that
could come out differently. How large the differences are has not been measured.

### Results

Results on `mldsa_caddq`:

| | C | K | L |
|---|---:|---:|---:|
| wall clock | 1,549 s | 673 s | **639 s** |
| full tactics all-short | 46 of 70 | 46 of 70 | 46 of 70 |
| trace files identical to C | — | 414 of 414 | **414 of 414** |

L is as fast as J, which prints no arguments at all, because it prints only the records
that end up in the traces. The 34 s between K and L is what K spent on records kept at
first and replaced later.

I then ran C and L back to back on `bignum_mux`, a small scalar proof:

| | C | L |
|---|---:|---:|
| wall clock | 160 s | 162 s |
| tactics / at quota / all-short | 141 / 49 / 41 | 141 / 49 / 41 |
| trace files identical to C | — | **352 of 352** |

No speedup there, and none was expected: tracing only roughly doubles this proof's time
(85 s untraced), and 41 of its 49 full tactics settle on all-short records, so the
replacement branch rarely runs. The output was identical again. (The run's own summary
line said L wrote 128 MB of traces against C's 33 MB. That was only because `du` measured
the whole `traces-L` directory, which still held the 96 MB from L's earlier `mldsa_caddq`
run.)

L carries one risk K does not. HOL Light prints according to its settings at the moment
of printing, and s2n-bignum changes some while loading:
`override_interface("%", Register)` at `x86/proofs/instruction.ml:413` (after it,
`Register` prints as `%`), and five `parse_as_infix` declarations in
`common/for_hollight.ml`, `common/components.ml` and `common/relational.ml`. A tactic
recorded before one of these, whose arguments contain the affected constant, would print
the old way under C and the new way under L. `prioritize_num/int/real` are called about
200 times too, but `printer.ml` looks up a constant's symbol by matching the constant, so
reordering the interface should not change what is printed unless one constant has
several symbols, which I did not check exhaustively. On `mldsa_caddq` none of this made
any difference: all 414 files matched. On `bignum_mux` all 352 matched too. All seven of
the settings changes sit in shared files, not in any per-function proof, but which
records survive to be printed differs from proof to proof, so two matching proofs are
evidence, not a guarantee.

Before sending it to June:

- Repeat the byte-for-byte comparison on more proofs. Done so far on `mldsa_caddq` and
  `bignum_mux`; for L each one doubles as a check on the printing-settings risk.
- Decide whether to treat the conversion path the same way. It has the same shape and was
  left alone. All conversion recording together cost 172 s here (H → G).

June (TacticTrace's author) has invited contributions and is splitting TacticTrace into
its own repository under `github.com/hol-light`, so the patch has somewhere to go.

## Caveats

- Two proofs, two families. The 7.6× figure is `mldsa_caddq`; `bignum_mux` is 1.8×. The
  remaining 309 proofs are mostly the scalar kind, where the overhead is much smaller.
- `mldsa_caddq` is not one of the 50-hour proofs. The extrapolation to `mldsa_intt` and
  friends assumes the ratio holds within a family; it has not been measured there
  because a single run would take days.
- Configuration F changes which records are kept (with the length always zero, every
  record looks equally interesting, so it keeps the first 100), so its 191 MB of output
  is not comparable to C's 94 MB. It is a timing measurement only.
- Configuration I is not perfectly clean either. Its length estimate does not order
  records exactly the way the printed length does: 23 of 70 full tactics ended
  all-short, against 46 of 70 in C. So I probably runs the replacement branch somewhat
  more often than C. For goal printing to be the real cost, those extra runs would have
  to cost almost exactly what the printing saved, which is unlikely but not impossible.
- Configuration J has no such problem: arguments do not affect the ordering, and it ended
  with exactly C's retention. Its records carry no argument text, so it too is a timing
  measurement only.
- Every timing is a single run. A few seconds either way, such as L's 639 s against J's
  644 s, is too small to mean anything.
- G leaves the conversion path recording, so its 560 s is not a pure "wrapped but
  silent" figure. H is.

## Reproducing

Every configuration, I to L included, is now in the repository:
`experiment/trace-overhead.sh` builds, runs and times, and `experiment/patches.py` holds
the source edits for each config. `experiment/README.md` there explains how to run it. The
original one-off scripts are still on the lab server under `~/tactic-trace/scratch/`
(`exp.sh`, `expB.sh`, `expDE.sh`, `expFG.sh`, `expH.sh`). All of them build into
`*_exp<TAG>.native`, write traces under `/scratch/`, never touch the campaign's own
binaries or traces, and restore `exportTrace.ml` on exit.

`perf` and `gdb` are both unusable on that host — `perf_event_open` is blocked by an
LSM regardless of `perf_event_paranoid`, and `ptrace_scope = 1` prevents attaching to a
process inside a container. Hence the differencing approach rather than a profiler.
