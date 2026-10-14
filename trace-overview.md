# s2n-bignum × HOL Light — Tactic Trace Corpus

Extract `(proof state, tactic, next proof state)` triples from the machine-checked
HOL Light proofs that ship with [s2n-bignum](https://github.com/awslabs/s2n-bignum),
so that each tactic can later be given a natural-language description grounded in
what it actually does to a goal.

Detailed step-by-step operations live in [`RUNBOOK.md`](runbook.md). This file is the
overview: **how to build it, how to run it, and where the data stands right now.**

## Repository layout

| Path | What |
|---|---|
| [`RUNBOOK.md`](runbook.md) | Step-by-step operations: build HOL Light, build s2n-bignum, run proofs, interactive proving in VSCode, generate traces. |
| [`scripts/`](~/s2n-bignum-hol-light-llm/scripts/) | Everything that runs the campaign — Docker image, `run.sh` entry point, the run loop, and `trace-status.sh` for progress. See [`scripts/README.md`](trace-scripts.md). |
| [`llm/`](~/s2n-bignum-hol-light-llm/llm/) | Stage 3: turning traces into natural-language tactic descriptions with Claude on Amazon Bedrock. See [`llm/README.md`](llm-pipeline.md). |
| `s2n-bignum.patch` | The patch that wires the trace pipeline into `tools/build-proof.sh`. |
| `TODO.txt` | Working notes. |

Generated data — `traces/`, `thms/`, `llm/dedup/` — is gitignored; it runs to tens of
gigabytes. §6.5 says where it actually lives. No credentials are stored in this repo:
`llm/describe.py` reads an AWS profile (default `lab`) from `~/.aws/credentials` and
calls `bedrock-runtime` only.

---

### 

Wall-clock is a single core per proof; several proofs ran concurrently, so the column
does not sum to elapsed time.

| Folder | Theorem / proof | Started | Finished | Wall clock | Tactic files | Triples | Size |
|---|---|---|---|---:|---:|---:|---:|
| `curve25519` | `bignum_inv_p25519` | 09-10 10:35 | 09-10 11:38 | **1h03m** | 430 | 10706 | 87 MB |
| `curve25519` | `curve25519_ladderstep_alt` | 09-10 11:20 | 09-10 13:02 | **1h42m** | 425 | 10493 | 71 MB |
| `curve25519` | `curve25519_ladderstep` | 09-10 11:20 | 09-10 12:58 | **1h38m** | 425 | 10453 | 68 MB |
| `curve25519` | `curve25519_pxscalarmul_alt` | 09-10 11:20 | 09-10 13:05 | **1h45m** | 429 | 10577 | 72 MB |
| `curve25519` | `curve25519_pxscalarmul` | 09-10 11:20 | 09-10 13:05 | **1h45m** | 430 | 10542 | 69 MB |
| `curve25519` | `edwards25519_decode` | 09-10 11:22 | 09-10 12:06 | **0h43m** | 457 | 10809 | 145 MB |
| `curve25519` | `edwards25519_encode` | 09-10 11:22 | 09-10 11:26 | **0h04m** | 374 | 7362 | 34 MB |
| `generic` | `bignum_mux` | 09-10 11:02 | 09-10 11:06 | **0h03m** | 352 | 6779 | 32 MB |
| `mldsa` | `mldsa_caddq` | 09-10 02:36 | 09-10 03:09 | **0h32m** | 414 | 8555 | 94 MB |
| `mldsa` | `mldsa_nttunpack` | 09-10 02:36 | 09-10 02:50 | **0h13m** | 422 | 8786 | 65 MB |
| `mldsa` | `mldsa_pointwise` | 09-10 02:36 | 09-10 04:04 | **1h27m** | 426 | 9082 | 393 MB |
| `mldsa` | `mldsa_reduce` | 09-10 02:36 | 09-10 02:49 | **0h13m** | 398 | 8255 | 111 MB |
| `mldsa` | `mldsa_rej_uniform_VARIABLE_TIME` | 09-10 02:36 | 09-10 03:22 | **0h45m** | 391 | 8634 | 4.6 GB |
| `mlkem` | `mlkem_basemul_k2` | 09-09 19:32 | 09-09 21:03 | **1h31m** | 404 | 8336 | 504 MB |
| `mlkem` | `mlkem_basemul_k3` | 09-09 19:32 | 09-09 22:43 | **3h11m** | 404 | 8340 | 557 MB |
| `mlkem` | `mlkem_basemul_k4` | 09-09 19:32 | 09-10 01:59 | **6h26m** | 404 | 8340 | 608 MB |
| `mlkem` | `mlkem_frombytes` | 09-09 21:03 | 09-09 21:26 | **0h23m** | 395 | 8234 | 206 MB |
| `mlkem` | `mlkem_intt` | 09-09 21:26 | 09-10 15:03 | **17h36m** | 405 | 8412 | 430 MB |
| `mlkem` | `mlkem_mulcache_compute` | 09-09 22:43 | 09-09 22:57 | **0h13m** | 404 | 7971 | 178 MB |
| `mlkem` | `mlkem_reduce` | 09-10 00:55 | 09-10 02:13 | **1h17m** | 425 | 8667 | 86 MB |
| `mlkem` | `mlkem_rej_uniform_VARIABLE_TIME` | 09-10 00:55 | 09-10 01:12 | **0h17m** | 417 | 8686 | 74 MB |
| `mlkem` | `mlkem_tobytes` | 09-10 00:55 | 09-10 01:30 | **0h34m** | 404 | 8196 | 346 MB |
| `mlkem` | `mlkem_tomont` | 09-10 00:55 | 09-10 01:08 | **0h12m** | 403 | 8274 | 163 MB |
| `mlkem` | `mlkem_unpack` | 09-10 00:55 | 09-10 01:06 | **0h10m** | 398 | 8246 | 68 MB |
| `sha3` | `sha3_keccak_f1600` | 09-09 19:30 | 09-10 03:44 | **8h14m** | 360 | 8128 | 853 MB |

Total CPU time for the 25: **52.2 h**. Median ~46 min; the tail is
`mlkem_intt` (17 h 36 m), `sha3_keccak_f1600` (8 h 14 m) and `mlkem_basemul_k4` (6 h 26 m).
`mldsa_rej_uniform_VARIABLE_TIME` is the size outlier at 4.6 GB — a single file,
`POP_ASSUM_LIST.json`, accounts for 869 MB of it.

---

## 1. What a triple looks like

`TacticTrace` instruments the HOL Light kernel. Every tactic application inside a
proof script is logged to `$TRACE_DUMP_DIR/<proof>.ml/<TACTIC_NAME>.json` as a list
of records:

```json
{
  "tactic": "ARITH_TAC",
  "goal_before":  "...term with its assumption list...",
  "goals_after":  ["...", "..."],
  "num_subgoals": 2,
  "arg_names": [...], "arg_types": [...], "arg_values": [...], "arg_exprs": [...],
  "definition_line_number": {"file_path": "...", "line": 1234},
  "user_line_number":       {"file_path": "...", "line": 5678}
}
```

`goal_before` → `tactic` → `goals_after` is the triple. Conversions (`*_CONV`) are
logged in the same directory with `conv` / `output` fields instead — those are
rewrites, not tactics, and carry no goal state.

Theorem statements proved by each file are dumped separately to
`$THM_DUMP_DIR/<proof>.ml.json`.

---

## 2. Components and pinned versions

| Component | Version in use | Notes |
|---|---|---|
| [`jrh13/hol-light`](https://github.com/jrh13/hol-light) | `2a1cea8` (2026-09-06) | must be recent — `TacticTrace/` only exists upstream since 2025-08-22 |
| [`awslabs/s2n-bignum`](https://github.com/awslabs/s2n-bignum) | `7948ca13` (2026-09-02) | x86 side only so far |
| `s2n-bignum.patch` | in this repo | advisor's patch; wires the trace pipeline into `tools/build-proof.sh` |
| OCaml | **5.4.0** | required by `TacticTrace`; installed as a *local opam switch* at `$HOLLIGHT_DIR/_opam` |

The patch touches `x86/Makefile`, `arm/Makefile`, `tools/build-proof.sh`, and
`arm/proofs/arm.ml`. The last hunk is **already upstream**, so it must be excluded:

```bash
git apply --exclude='arm/proofs/arm.ml' s2n-bignum.patch
```

---

## 3. Build

### 3.1 Docker (what the production runs use)

Everything lives on the lab server under `~/tactic-trace/`. The image is deliberately
thin (~600 MB): OS packages + opam only. `hol-light`, `s2n-bignum`, the opam root and
all outputs are **bind-mounted from the host**, so results survive the container and
stay editable from outside.

```
~/tactic-trace/
├── docker/Dockerfile          ubuntu:22.04 + build deps + opam 2.3.0
├── docker/entrypoint.sh       activates the opam switch, prints version/limits banner
├── run.sh                     the only entry point (see below)
├── hol-light/     →  /opt/hol-light
├── opamroot/      →  /opt/opamroot
├── s2n-bignum/    →  /work/s2n-bignum
├── out/           →  /out          traces/ and thms/
└── scratch/       →  /scratch      TMPDIR; intermediate .ml files accumulate here
```

One-time build:

```bash
cd ~/tactic-trace
docker build -t tp-hol:latest docker/          # ~3 min

./run.sh --setup-hol      # clone hol-light, opam switch-5, make, build TacticTrace  (~15 min)
./run.sh --setup-s2n      # clone s2n-bignum, apply the patch
```

`--setup-hol` performs, inside the container:

```bash
git clone https://github.com/jrh13/hol-light.git /opt/hol-light
opam init --disable-sandboxing --bare -y
opam update && make switch-5                   # OCaml 5.4.0 local switch
eval $(opam env --switch /opt/hol-light --set-switch)
HOLLIGHT_USE_MODULE=1 make                     # produces hol_lib.cmxa
cd TacticTrace && make && HOLLIGHT_DIR=/opt/hol-light ./build-hol-kernel.sh
```

Key `docker run` flags, all of which matter:

| Flag | Why |
|---|---|
| `--user $(id -u):$(id -g)` | otherwise every output file is root-owned and undeletable from the host |
| `--ulimit stack=-1` | `.native` binaries use the **system** stack; `curve25519_ladderstep` overflows 8 MB. `OCAMLRUNPARAM=l=` only affects bytecode and does nothing here |
| `-e HOME=/scratch/home` | opam needs a writable HOME |
| `--cpus` / `--memory` | one proof = one core = one process; memory is the real constraint |

### 3.2 Bare metal

Same steps without Docker; set `HOLDIR` / `HOLLIGHT_DIR` to your checkout and make sure
`ulimit -s unlimited` is in effect. `tools/build-proof.sh:46-49` auto-detects and
activates `$HOLLIGHT_DIR/_opam` if present, so the local switch is picked up
automatically. See `RUNBOOK.md` §11.

---

## 4. Sampling parameters — the one thing that decides how much data you get

Four compile-time constants in `hol-light/TacticTrace/exportTrace.ml` govern what is
kept. **The upstream defaults throw away most of s2n-bignum**, because s2n-bignum goals
are enormous: median 178 assumptions, 90th percentile 242, max 353; median goal text
124 KB.

| Constant | Line | Upstream | **Ours** | Effect |
|---|---|---|---|---|
| `maxcnt` | 33 | 1 000 | 1 000 000 | term-node budget when measuring goal size |
| `max_num_records` | 49 | 20 | **100** | records kept per tactic per proof |
| `max_assumptions` | 53 | 150 | 100 000 | **the real gate** — at 150 it drops ~54 % of all records |
| `interesting_concl_strlen` | 69 | 100 | 100 | unchanged |

After editing that file you must run **both**:

```bash
./run.sh --rebuild-trace                 # rebuild tracer + kernel_wrapper.ml
./run.sh --clean-native <command...>     # delete stale .native/.correct, then run
```

`%.native` depends only on the proof `.ml` and the `.o`, **not** on `kernel_wrapper.ml`,
so skipping `--clean-native` silently reuses binaries compiled with the old constants.
(This cost one 4-hour run already.)

`max_num_records = 100` is binding for roughly half the tactics: the informative ones
naturally produce 21–45 records, while a handful of workhorse tactics would otherwise
emit tens of thousands of near-identical entries. Raising it mostly buys noise and disk.

---

## 5. Run

The build/run split for one proof `dir/name`:

```
proofs/name.ml  +  dir/name.o
        │
        ├─ build-proof.sh → inline-load → inlined_raw.ml
        │       ├─ THM_DUMP_DIR branch: get-ast.sh → tracer collect-toplevel-thms
        │       └─ TRACE_DUMP_DIR branch: modify-proof.sh → inlined.ml → ocamlopt
        │                                                        ↓
        │                                              dir/name.native
        └─ run-proof.sh  → ./dir/name.native  → dir/name.correct   (stdout log)
                                              → /out/traces/name.ml/*.json
```

```bash
# one proof
./run.sh make p256/bignum_montmul_p256.correct

# a directory
./run.sh -d make -j12 $(cd s2n-bignum/x86 && ls mlkem/*.o | sed 's/\.o$/.correct/')

# everything (342 targets)
./run.sh -d make -j12 proofs

./run.sh --logs      # follow
./run.sh --shell     # exec into the running container
./run.sh --stop
```

Notes that bite:

* **Targets must carry their directory prefix.** The Makefile uses
  `%.native: proofs/$(*F).ml … %.o` with `.SECONDEXPANSION`; `$(*F)` is filename-only,
  so proof scripts live flat in `proofs/` while `.o` files live in per-function
  directories. `make bignum_mux.correct` will not work; `make generic/bignum_mux.correct` will.
* **`.correct` existing does not mean the proof finished.** `run-proof.sh` does
  `"$native_path" 2>&1 > "$output_path"`, which creates the file at process *start*.
  Completion is signalled by the string `Dumped to` (patched) or `Running time:` (original).
* HOL Light proofs are single-threaded. One proof pins exactly one core; all parallelism
  comes from `-j`.
* Traces are written **at process exit**, not incrementally. A proof killed at 19 h yields nothing.

---

## 6. Current results

*Snapshot: **2026-09-11 11:04 CDT**. Host: lab server, 32 cores / 124 GB RAM.
All numbers are x86; `arm/` has not been started.*

### 6.1 Where things stand

The denominator is **342**, not the 352 proof scripts in `x86/proofs/`. `PROOF_BINS`
is `$(OBJ:.o=.native)` — derived from the object files — and the 342 non-tutorial `.o`
map 1:1 onto proof scripts. The 10 leftover scripts are shared infrastructure, not
per-function proofs: `aes`, `base`, `consttime`, `decode`, `equiv`, `instruction`,
`mldsa_rej_uniform_table`, `simulator`, `subroutine_signatures`, `x86`. (A further 15
`.o` live under `tutorial/`, which is a separate target set — see §6.4.)

| | Proofs | Tactic-trace files | Triples | On-disk (logical) |
|---|---:|---:|---:|---:|
| **Completed** | **30 / 342** | 12 219 | **264 687** | 13.1 GB |
| Running | 3 | — | — | — |
| Not started | 309 | — | — | — |
| *Tutorial set (separate)* | *11 / 11* | *3 674* | *582 123* | *11.5 GB* |

Coverage by directory:

| Directory | Targets | Done | Running | Not started | `.native` already compiled |
|---|---:|---:|---:|---:|---:|
| `generic`    | 71 | 1  | 0 | 70 | 61 |
| `curve25519` | 46 | 7  | 0 | 39 | 33 |
| `p256`       | 44 | 0  | 0 | 44 | 32 |
| `p384`       | 40 | 0  | 0 | 40 | 32 |
| `p521`       | 35 | 0  | 0 | 35 | 27 |
| `sm2`        | 32 | 0  | 0 | 32 | 24 |
| `secp256k1`  | 32 | 0  | 0 | 32 | 26 |
| `fastmul`    | 17 | 0  | 0 | 17 | 17 |
| `mlkem`      | 12 | **12** | 0 | **0** | 12 |
| `mldsa`      | 10 | 7  | 3 | **0** | 10 |
| `sha3`       | 3  | **3**  | 0 | **0** | 3  |
| **Total**    | **342** | **30** | **3** | **309** | **277** |

`mlkem` and `sha3` are complete; `mldsa` has three left running. 277 of 342 `.native`
binaries are already compiled, so ~81 % of the (expensive) compilation is banked and a
restart goes straight to execution.

**The theorem-statement half of the pipeline is already finished.** `build-proof.sh`
has two independent branches (§5); the `THM_DUMP_DIR` branch only needs the inline
load, not the `ocamlopt` build and the proof replay, so it has completed for all
**353 / 353** files (342 + 11 tutorial). Only the trace branch is still in progress.

Regenerate all of this with [`scripts/trace-status.sh -lc`](trace-scripts.md).

### 6.2 Completed

Wall clock is a single core per proof; several proofs ran concurrently, so the column
does not sum to elapsed time. Five proofs were frozen with `docker pause` for 4 h 09 m
on 2026-09-10 (21:52 → 02:01); that idle time is included in the figures for
`mldsa_pointwise_acc_l5`, `sha3_keccak4_f1600_alt` and the three still running.

| Folder | Theorem / proof | Started | Finished | Wall clock | Tactic files | Triples | Size |
|---|---|---|---|---:|---:|---:|---:|
| `curve25519` | `bignum_inv_p25519` | 09-10 10:35 | 09-10 11:38 | **1h03m** | 430 | 10706 | 87 MB |
| `curve25519` | `curve25519_ladderstep` | 09-10 11:20 | 09-10 12:58 | **1h38m** | 425 | 10453 | 68 MB |
| `curve25519` | `curve25519_ladderstep_alt` | 09-10 11:20 | 09-10 13:02 | **1h42m** | 425 | 10493 | 71 MB |
| `curve25519` | `curve25519_pxscalarmul` | 09-10 11:20 | 09-10 13:05 | **1h45m** | 430 | 10542 | 69 MB |
| `curve25519` | `curve25519_pxscalarmul_alt` | 09-10 11:20 | 09-10 13:05 | **1h45m** | 429 | 10577 | 72 MB |
| `curve25519` | `edwards25519_decode` | 09-10 11:22 | 09-10 12:06 | **0h43m** | 457 | 10809 | 145 MB |
| `curve25519` | `edwards25519_encode` | 09-10 11:22 | 09-10 11:26 | **0h04m** | 374 | 7362 | 34 MB |
| `generic` | `bignum_mux` | 09-10 11:02 | 09-10 11:06 | **0h03m** | 352 | 6779 | 32 MB |
| `mldsa` | `mldsa_caddq` | 09-10 02:36 | 09-10 03:09 | **0h32m** | 414 | 8555 | 94 MB |
| `mldsa` | `mldsa_nttunpack` | 09-10 02:36 | 09-10 02:50 | **0h13m** | 422 | 8786 | 65 MB |
| `mldsa` | `mldsa_pointwise` | 09-10 02:36 | 09-10 04:04 | **1h27m** | 426 | 9082 | 393 MB |
| `mldsa` | `mldsa_pointwise_acc_l4` | 09-10 02:36 | 09-10 18:00 | **15h24m** | 426 | 9372 | 444 MB |
| `mldsa` | `mldsa_pointwise_acc_l5` | 09-10 02:36 | 09-11 07:27 | **28h50m** | 426 | 9445 | 521 MB |
| `mldsa` | `mldsa_reduce` | 09-10 02:36 | 09-10 02:49 | **0h13m** | 398 | 8255 | 111 MB |
| `mldsa` | `mldsa_rej_uniform_VARIABLE_TIME` | 09-10 02:36 | 09-10 03:22 | **0h45m** | 391 | 8634 | 4.6 GB |
| `mlkem` | `mlkem_basemul_k2` | 09-09 19:32 | 09-09 21:03 | **1h31m** | 404 | 8336 | 504 MB |
| `mlkem` | `mlkem_basemul_k3` | 09-09 19:32 | 09-09 22:43 | **3h11m** | 404 | 8340 | 557 MB |
| `mlkem` | `mlkem_basemul_k4` | 09-09 19:32 | 09-10 01:59 | **6h26m** | 404 | 8340 | 608 MB |
| `mlkem` | `mlkem_frombytes` | 09-09 21:03 | 09-09 21:26 | **0h23m** | 395 | 8234 | 206 MB |
| `mlkem` | `mlkem_intt` | 09-09 21:26 | 09-10 15:03 | **17h36m** | 405 | 8412 | 430 MB |
| `mlkem` | `mlkem_mulcache_compute` | 09-09 22:43 | 09-09 22:57 | **0h13m** | 404 | 7971 | 178 MB |
| `mlkem` | `mlkem_ntt` | 09-09 22:57 | 09-10 17:17 | **18h19m** | 405 | 8411 | 477 MB |
| `mlkem` | `mlkem_reduce` | 09-10 00:55 | 09-10 02:13 | **1h17m** | 425 | 8667 | 86 MB |
| `mlkem` | `mlkem_rej_uniform_VARIABLE_TIME` | 09-10 00:55 | 09-10 01:12 | **0h17m** | 417 | 8686 | 74 MB |
| `mlkem` | `mlkem_tobytes` | 09-10 00:55 | 09-10 01:30 | **0h34m** | 404 | 8196 | 346 MB |
| `mlkem` | `mlkem_tomont` | 09-10 00:55 | 09-10 01:08 | **0h12m** | 403 | 8274 | 163 MB |
| `mlkem` | `mlkem_unpack` | 09-10 00:55 | 09-10 01:06 | **0h10m** | 398 | 8246 | 68 MB |
| `sha3` | `sha3_keccak4_f1600` | 09-09 19:30 | 09-10 20:04 | **24h34m** | 383 | 8308 | 997 MB |
| `sha3` | `sha3_keccak4_f1600_alt` | 09-09 19:30 | 09-11 03:34 | **32h04m** | 383 | 8288 | 947 MB |
| `sha3` | `sha3_keccak_f1600` | 09-09 19:30 | 09-10 03:44 | **8h14m** | 360 | 8128 | 853 MB |

Total CPU time for the 30: **171 h**. Median **88 min**, but the mean is 5 h 42 m —
the sample is deliberately tail-heavy, because `mlkem` / `mldsa` / `sha3` were run
first and hold the slowest proofs in the tree. `sha3_keccak4_f1600` took 24 h 34 m.
`mldsa_rej_uniform_VARIABLE_TIME` is the size outlier at 4.6 GB — one file,
`POP_ASSUM_LIST.json`, is 869 MB of it.

### 6.3 Running

| Folder | Theorem / proof | Started | Elapsed (as of 11:04) |
|---|---|---|---:|
| `mldsa` | `mldsa_intt` | 09-10 02:36 | **32h28m** |
| `mldsa` | `mldsa_ntt` | 09-10 02:36 | **32h28m** |
| `mldsa` | `mldsa_pointwise_acc_l7` | 09-10 02:36 | **32h28m** |

The last three of the long tail — ML-DSA NTT/INTT butterflies and a pointwise
accumulator. Each has been going over 32 h (4 h 09 m of that paused). They sit in
`tl-batch-mldsa` at 16 cores / 64 GB.

### 6.4 Tutorial proofs (separate target set)

`x86/tutorial/` is **not** part of the 342 — it is `TUTORIAL_PROOF_BINS`, a separate
Makefile variable. These were traced on 2026-09-08 with the earlier
`max_num_records = 10000`, which is why they carry ~6× the triples per proof
(52 920 vs 8 852) despite being far smaller proofs — five minutes of wall clock each.
They are usable data, but **not sampled the same way as everything above**.

| Proof | Wall clock | Tactic files | Triples | Size |
|---|---:|---:|---:|---:|
| `bignum` | 0h05m | 326 | 48286 | 976 MB |
| `branch` | 0h05m | 320 | 40870 | 959 MB |
| `loop` | 0h05m | 326 | 41437 | 962 MB |
| `memory` | 0h05m | 320 | 38500 | 955 MB |
| `rel_equivtac` | 0h06m | 350 | 46217 | 1.2 GB |
| `rel_reordertac` | 0h05m | 342 | 46435 | 1.2 GB |
| `rel_simp` | 0h05m | 333 | 41962 | 1.2 GB |
| `rodata` | 0h05m | 340 | 53067 | 999 MB |
| `safety` | 0h12m | 382 | 145555 | 1.2 GB |
| `sequence` | 0h05m | 321 | 40862 | 958 MB |
| `simple` | 0h05m | 314 | 38932 | 955 MB |

### 6.5 Where the data lives

| What | Where |
|---|---|
| Live trace output | lab server, `~/tactic-trace/out/traces/<proof>.ml/*.json` |
| Theorem statements | lab server, `~/tactic-trace/out/thms/<proof>.ml.json` — **353 / 353, complete** (plus the `_inlined.ml` / `.mli` / `.marshalled.bin` for each) |
| Packed + md5-verified on the laptop, `~/s2n-bignum-traces/` | `mlkem-partial-9.tar.gz` 157 MB (9 `mlkem`) · `batch2-unpacked.tar.gz` 215 MB (5 `mldsa`, `mlkem_basemul_k4`, `sha3_keccak_f1600`) · `batch3-queue-9.tar.gz` 72 MB (7 `curve25519`, `bignum_mux`, `mlkem_intt`) — 25 proofs, 445 MB |
| Not yet packed (server only) | `mlkem_ntt`, `mldsa_pointwise_acc_l4`, `mldsa_pointwise_acc_l5`, `sha3_keccak4_f1600`, `sha3_keccak4_f1600_alt` — 5 proofs, ~2.8 GB |
| Sample committed here | `traces/simple.ml/`, `thms/` |

Originals on the server are kept after packing — nothing has been deleted.

**Compiled artifacts are never deleted.** `s2n-bignum/x86/*/*.native` (277 of them,
~10 GB) and the `.correct` logs represent the bulk of the CPU already spent. Only
`./run.sh --clean-native` removes them, and it must not be run — a restart is meant to
pick these up, not rebuild them. Changing `exportTrace.ml` would invalidate them, which
is exactly why the sampling parameters are frozen for the rest of this campaign.

Containers, as of the snapshot (all `tp-hol:latest`):

| Name | State | Holds |
|---|---|---|
| `tl-batch-mldsa` | **Up** | the last three `mldsa` long-tail proofs |
| `wonderful_ride` | **Up** (idle) | its `sha3` / `mlkem` proofs have all finished |
| `tl-queue` | Exited (2) | the aborted 317-target queue — see §7 |
| `tl-mlkem-rest` | Exited (0) | finished normally, kept for its logs |

`wonderful_ride` carries an auto-generated Docker name, so it is easy to miss when
filtering the container list by `tl-`. It is holding 20 hours of work; do not stop it.

### 6.6 Cost model

| Quantity | Measured (30 proofs) |
|---|---|
| Median wall clock per proof | **88 min** |
| Mean wall clock per proof | 5 h 42 m (171 CPU-hours / 30) |
| Mean trace size per proof | ~437 MB logical |
| Mean triples per proof | ~8 820 |
| gzip ratio on trace directories | 14–24× depending on directory |

Do not project from the mean. The 30 proofs run so far are `mlkem`, `mldsa`, `sha3`
and the heavy `curve25519` scalar multiplications — deliberately the slowest corner of
the tree, which is why the mean is four times the median. The 309 that remain are
`generic` / `p256` / `p384` / `p521` / `sm2` / `secp256k1` / `fastmul`: ordinary bignum
routines that should track the median. On that basis:

* **~450 CPU-hours**, or roughly **40 h of wall clock at `-j12`**
* **~130 GB** of trace output

The binding constraint is disk, not CPU: **112 GB free** against that ~130 GB.
Packing completed proofs as they finish removes the problem — and packing must target
`out/traces/`, never the `.native` binaries.

---

## 7. Known issues

**The main queue is currently stopped.** The `-j12` container that held the remaining
317 targets exited on 2026-09-10 shortly after its last in-flight proof finished at
13:05. Three `ocamlopt` invocations had been OOM-killed (`Error 137`) while compiling
the largest curve25519 proofs:

```
curve25519/curve25519_x25519_alt.native
curve25519/curve25519_x25519base.native
curve25519/curve25519_x25519base_alt.native
```

Because `make` was run without `-k`, the first failure stopped it from scheduling new
targets; it drained the four in-flight proofs and exited. Restarting needs either a
higher memory ceiling for that container (it was capped at 48 GB, while the other two
containers hold 64 GB each and the host has 124 GB total) or `make -k` so one OOM does
not take down the whole queue. The three failures are compile-time, not proof-time —
no trace data was lost.

**Other things that have actually gone wrong:**

| Symptom | Cause | Fix |
|---|---|---|
| Stack overflow in `curve25519_ladderstep` | `.native` uses the system stack; `OCAMLRUNPARAM=l=` is bytecode-only | `ulimit -s unlimited` / `--ulimit stack=-1` |
| `ledit` segfaults at HOL Light startup | `/usr/bin/ledit` is OCaml 4.13.1 bytecode; the opam runtime needs `caml_atfork_hook` | `export LINE_EDITOR=rlwrap` |
| Traces silently unchanged after editing `exportTrace.ml` | `%.native` does not depend on `kernel_wrapper.ml` | `--rebuild-trace` **and** `--clean-native` |
| Output files owned by root, undeletable from the host | container ran without `--user` | `--user $(id -u):$(id -g)`; clean up the old ones with a throwaway root container |
| `scratch/` grows without bound | the patch adds `inlined_raw="$(mktemp).ml"` but never adds it to the closing `rm` | expected; sweep files older than 30 min that no process holds open |
| Same proof traced twice | two containers were given overlapping target lists | partition targets explicitly before launching |
| `make <name>.correct` says no rule | targets need the directory prefix | `make <dir>/<name>.correct` |

Deeper writeups (in Traditional Chinese) live in the companion notes repo:
`README.md` (setup + interactive VSCode workflow) and `PITFALLS.md` (28 entries).

---

## 8. Status against the assignment

| Step | State |
|---|---|
| 1. Build HOL Light (latest upstream) and prove simple things | done — `2a1cea8`, tutorial proofs replayed, interactive VSCode workflow documented |
| 2. Build s2n-bignum | done — `7948ca13`, patch applied, x86 objects and unit tests pass |
| 3a. Generate `(proof state, tactic, next proof state)` triples | **in progress** — theorem statements 353/353 complete; traces 30/342 proofs = 264 687 triples, 3 running, 309 queued |
| 3b. Turn triples into English tactic descriptions | pipeline built and running — see [`llm/`](~/s2n-bignum-hol-light-llm/llm/): sample → Claude on Bedrock → `descriptions.jsonl` → `REPORT.md` |

Next action: relaunch the queue with `make -k` and a higher memory ceiling (§7), and
pack completed proofs as they finish so disk stops being the limit (§6.6).
