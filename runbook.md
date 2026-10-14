# s2n-bignum + HOL Light — Operational Runbook

Commands only. Verified on Ubuntu 22.04.5 / x86_64.

Replace `x86` with `arm` throughout if you are on aarch64.

---

## 0. Prerequisites

```bash
uname -m                # x86_64 or aarch64
gcc --version
as --version            # GNU binutils
make --version
```

```bash
sudo apt update
sudo apt install libpcre2-dev ocaml libstring-shellquote-perl libgmp-dev xdot rlwrap
```

---

## 1. Build s2n-bignum

```bash
git clone https://github.com/awslabs/s2n-bignum.git ~/s2n-bignum
cd ~/s2n-bignum
(cd x86 && make -j$(nproc))
```

Produces `x86/libs2nbignum.a` plus one `.o` per function.

---

## 2. Unit tests

```bash
cd ~/s2n-bignum
(cd tests && make go)
```

Expected final line: `All 374 tests run, all passed`

Other forms:

```bash
cd ~/s2n-bignum/tests
make test                        # build ./test only
./test bignum_montmul_p256       # single function
./test +500                      # 500 cases per function (default 100)
make complete                    # 500 cases, unfiltered, with return code
```

---

## 3. Call from C

```c
// demo.c
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "s2n-bignum.h"

int main(void) {
  uint64_t a[4] = {~0ULL, ~0ULL, ~0ULL, ~0ULL};
  uint64_t b[4] = {3, 0, 0, 0};
  uint64_t r[8] = {0};
  bignum_mul(8, r, 4, a, 4, b);
  for (int i = 7; i >= 0; i--) printf("%016lx", r[i]);
  printf("\n");
  return 0;
}
```

```bash
cd ~/s2n-bignum
gcc -O2 -I include demo.c x86/libs2nbignum.a -o demo
./demo
```

---

## 4. Benchmark

```bash
cd ~/s2n-bignum
(cd benchmarks && make go)
```

Runs ~2 hours. To keep a log:

```bash
cd ~/s2n-bignum/benchmarks
make benchmark
nohup ./benchmark > bench.log 2>&1 &
tail -f bench.log
```

Single function:

```bash
./benchmark bignum_montmul_p256
```

---

## 5. Build HOL Light

```bash
git clone https://github.com/jrh13/hol-light.git ~/hol-light
cd ~/hol-light
eval $(opam env)
HOLLIGHT_USE_MODULE=1 make
```

`HOLLIGHT_USE_MODULE=1` is required — it produces `hol_lib.cmxa`, which `tools/build-proof.sh` checks for.

Verify:

```bash
ls -la ~/hol-light/hol_lib.cmxa
```

Smoke test:

```bash
cd ~/hol-light
LINE_EDITOR=rlwrap ./hol.sh
```

```ocaml
g `!a b:num. a + b = b + a`;;
e (ARITH_TAC);;
top_thm();;
#quit;;
```


---

## 6. Point s2n-bignum at HOL Light

`x86/Makefile` defaults to `HOLDIR?=$(HOME)/hol-light`. Override with an environment variable if needed:

```bash
export HOLDIR=$HOME/hol-light
```

---

## 7. Run the tutorial proofs (batch)

```bash
cd ~/s2n-bignum/x86
ulimit -s unlimited
make tutorial -j2 2>&1 | tee ~/tutorial.log
```

Verify:

```bash
ls ~/s2n-bignum/x86/tutorial/*.correct | wc -l     # expect 11
grep -inE 'error|exception' ~/tutorial.log
```

To force a re-run:

```bash
cd ~/s2n-bignum/x86
rm -f tutorial/*.native tutorial/*.correct
```

Tutorial files, in recommended reading order:

| Order | File | Topic |
|---|---|---|
| 1 | `simple.ml` | linear program, arithmetic property |
| 2 | `sequence.ml` | splitting a program into chunks |
| 3 | `branch.ml` | conditional branch |
| 4 | `memory.ml` | memory manipulation |
| 5 | `loop.ml` | simple loop |
| 6 | `bignum.ml` | writing a bignum specification |
| 7 | `safety.ml` | constant-time and memory safety |
| 8 | `rel_simp.ml` | equivalence of two simple programs |
| 9 | `rel_equivtac.ml` | equivalence with small differences |
| 10 | `rel_reordertac.ml` | equivalence under instruction reordering |

---

## 8. Interactive proving in VSCode

### 8.1 One-time setup

Launcher script (fixes the working directory and avoids `ledit`):

```bash
cat > ~/hol-light/hol-s2n.sh <<'EOF'
#!/bin/bash
export LINE_EDITOR=rlwrap
cd "$HOME/s2n-bignum" || exit 1
exec "$HOME/hol-light/hol.sh" "$@"
EOF
chmod +x ~/hol-light/hol-s2n.sh
```

Install the extension:

```bash
code --install-extension monadius.hol-light-simple
```

Add to VSCode `settings.json` (`Ctrl+Shift+P` → `Preferences: Open User Settings (JSON)`):

```json
"hol-light.exePaths": ["/home/<user>/hol-light/hol-s2n.sh"],
"hol-light.path": "/home/<user>/hol-light",
"hol-light.rootPaths": [".", "{hol}", "{workspace}"],
"hol-light.autoIndex": true,
"files.associations": { "*.ml": "hol-light-ocaml" }
```

Open the repository root as a folder:

```bash
code ~/s2n-bignum
```

Confirm the language mode in the status bar reads **HOL Light**.

### 8.2 Per-session flow

| # | Action | Wait |
|---|---|---|
| 1 | `Ctrl+Shift+P` → `HOL Light: New HOL Light REPL Session` → pick `hol-s2n.sh` | ~1 min |
| 2 | `Ctrl+Shift+P` → `HOL Light: Start Server` | seconds |
| 3 | `Ctrl+Shift+P` → `HOL Light: Show HOL Light Goals` | — |
| 4 | Line 13 `needs "x86/proofs/base.ml";;` → `Alt+E` | ~6 min |
| 5 | Line 22 `let simple_mc = ...` → `Alt+E` | seconds |
| 6 | Line 41 `let EXEC = ...` → `Alt+E` | seconds |
| 7 | Lines 65–82, the backquoted term → `Alt+G` | seconds |
| 8 | Line 85 onward, one tactic per line → `Alt+L` repeatedly | seconds each |

Line numbers refer to `x86/tutorial/simple.ml`.

Step 2 must come before step 4: the goal view is fed by a JSON server running inside the REPL, not by parsing terminal output. The server does not carry over to a new REPL session.

Verify the server:

```bash
ss -ltnp | grep 2012
```

Cleaner goal display:

```ocaml
print_types_of_subterms := 0;;
```

Extract the finished theorem:

```ocaml
let SIMPLE_SPEC = top_thm();;
```

### 8.3 Keybindings

| Key | Command |
|---|---|
| `Alt+E` | Send Current Statement |
| `Alt+A` | Send All Statements before Cursor |
| `Alt+G` | Set Current Term as a Goal |
| `Alt+L` | Execute Current Tactic |
| `Alt+M` | Execute Current Tactic (Multiple Lines) |
| `Alt+R` | Select Tactic at Cursor Position |
| `Alt+O` | Rotate Subgoals |
| `Alt+B` | Revert One Proof Step |
| `Alt+P` | Print Current Goal |
| `Alt+S` | Search Theorems |
| `Alt+C` | Send ^C to REPL |

### 8.4 Editor-independent REPL commands

| Command | Effect |
|---|---|
| ``g `...`;;`` | set the goal |
| `e (TACTIC);;` | run one tactic |
| `b();;` | undo one step |
| `p();;` | reprint the current goalstack |
| `r n;;` | rotate subgoals |
| `top_thm();;` | extract the proved theorem |
| `#quit;;` | leave the REPL (or Ctrl+D) |

### 8.5 Formal proofs vs. tutorials

Tactics in `x86/proofs/*.ml` span multiple lines and use `THENL` branching. Use `Alt+M` instead of `Alt+L`, and `Alt+O` to move between subgoals. A single file contains many theorems, each needing its own `Alt+G`.

---

## 9. Prove a single function

```bash
cd ~/s2n-bignum/x86
ulimit -s unlimited
make p256/bignum_montmul_p256.correct
```

The target path must include the subdirectory: `%.native` depends on `%.o` at the same path.

Re-run:

```bash
rm p256/bignum_montmul_p256.correct
make p256/bignum_montmul_p256.correct
```

A passing `.correct` ends with:

```
Running time: <n> sec, Start unixtime: ..., End unixtime: ...
```

---

## 10. Prove everything

```bash
mkdir -p ~/tmp
cd ~/s2n-bignum/x86
ulimit -s unlimited
TMPDIR=$HOME/tmp nohup make -j1 proofs > proofs.log 2>&1 &
tail -f proofs.log
```

`TMPDIR` is required here: the full run needs more than 5 GB of scratch space (~16 MB per proof).

Progress:

```bash
cd ~/s2n-bignum/x86
find . -name '*.native' ! -path './tutorial/*' | wc -l    # compiled
find . -name '*.correct' ! -path './tutorial/*' | wc -l   # executed
```

Total target count:

```bash
make -f Makefile -f <(printf 'print-%%:\n\t@echo $($*)\n') print-PROOF_BINS \
  | tr ' ' '\n' | grep -c native
```

All `.native` binaries are built before any `.correct` runs.

Instruction semantics test (optional):

```bash
cd ~/s2n-bignum/x86
make sematest
```

---

## 11. Generate tactic traces (TacticTrace)

Produces `(proof state, tactic, next proof state)` triples from s2n-bignum proofs.

`TacticTrace` ships with upstream HOL Light (`jrh13/hol-light`, added 2025-08-22). The
s2n-bignum side needs `s2n-bignum.patch` from this repository.

### 11.1 Prerequisite: OCaml 5.4.0 in a local switch

TacticTrace requires HOL Light built with OCaml 5.4.0 and a **local** opam switch at
`$HOLLIGHT_DIR/_opam`. Both `TacticTrace/Makefile` and `build-hol-kernel.sh` assume it.

```bash
cd ~/hol-light
make switch-5                       # creates ~/hol-light/_opam with ocaml-base-compiler.5.4.0
eval $(opam env)
ocamlc -version                     # expect 5.4.0
HOLLIGHT_USE_MODULE=1 make
```

Regression check before continuing:

```bash
cd ~/s2n-bignum/x86
ulimit -s unlimited
make tutorial -j2                   # expect 11/11
```

After `make switch-5`, HOL Light is built with the local switch (OCaml 5.4.0) while your
shell `PATH` still points at the global switch. `tools/build-proof.sh` detects
`$HOLDIR/_opam` and activates it before compiling:

```bash
# tools/build-proof.sh:46-49
if [ -d "${HOLLIGHT_DIR}/_opam" ]; then
  eval $(opam env --switch "${HOLLIGHT_DIR}/" --set-switch)
fi
```

So you do not need to run `eval $(opam env --switch ~/hol-light)` yourself before `make`.
Linking a 5.4.0-built `hol_lib.cmxa` with a 4.14.2 `ocamlopt` would fail.

### 11.2 Build TacticTrace

```bash
export HOLLIGHT_DIR=$HOME/hol-light
eval $(opam env --set-switch --switch=${HOLLIGHT_DIR})

cd ${HOLLIGHT_DIR}/TacticTrace
make                                # builds: tracer, types_test
./build-hol-kernel.sh               # builds: kernel_wrapper.ml
```

Verify both exist:

```bash
ls -la ${HOLLIGHT_DIR}/TacticTrace/tracer ${HOLLIGHT_DIR}/TacticTrace/kernel_wrapper.ml
```

### 11.3 Apply the patch

```bash
cd ~/s2n-bignum
git apply ~/s2n-bignum-hol-light-llm/s2n-bignum.patch
git diff --stat
```

The patch touches three things:

| File | Change |
|---|---|
| `x86/Makefile`, `arm/Makefile` | sets `HOLDIR?=/mnt/disk/hol-light` — override with the env var below |
| `arm/proofs/arm.ml` | `ARM_SIM_TAC`: `?(preprocess_tac=ALL_TAC)` → `?(preprocess_tac:tactic option)` with an explicit match |
| `tools/build-proof.sh` | inserts the trace-generation pipeline |

Because `HOLDIR` uses `?=`, an environment variable wins:

```bash
export HOLDIR=$HOME/hol-light
```

### 11.4 What the patched `build-proof.sh` does

```
template.ml
    │  hol.sh inline-load
    ↓
inlined_raw.ml
    │
    ├─► THM_DUMP_DIR branch:
    │     TacticTrace/remove-linenum-dirs.py   → strips # line directives
    │     TacticTrace/get-ast.sh               → <name>.marshalled.bin
    │     TacticTrace/tracer collect-toplevel-thms → <name>.json
    │
    └─► TRACE_DUMP_DIR branch:
          TacticTrace/modify-proof.sh inlined_raw.ml inlined.ml <dump dir>
              ↓
          inlined.ml → ocamlopt → .native → emits trace JSON at run time
```

Each branch is skipped (with a warning) if its environment variable is unset.

### 11.5 Run

```bash
export HOLDIR=$HOME/hol-light
export THM_DUMP_DIR=$HOME/s2n-bignum-hol-light-llm/thms
export TRACE_DUMP_DIR=$HOME/s2n-bignum-hol-light-llm/traces

cd ~/s2n-bignum/x86
ulimit -s unlimited
```

Start with one proof to inspect the output format:

```bash
rm -f tutorial/simple.native tutorial/simple.correct
make tutorial/simple.correct
```

Then the tutorial set:

```bash
rm -f tutorial/*.native tutorial/*.correct
make tutorial -j2 2>&1 | tee ~/trace-tutorial.log
```

Then the full proof set:

```bash
mkdir -p ~/tmp
TMPDIR=$HOME/tmp nohup make -j1 proofs > proofs.log 2>&1 &
```

Traces are emitted during the **execution** phase, not the compile phase. Since
`run_proofs: build_proofs $(PROOF_LOGS)`, all `.native` binaries are built before any
trace appears.

### 11.6 Outputs

| Directory | Contents |
|---|---|
| `$TRACE_DUMP_DIR/<proof>.ml/` | tactic input/output goals and conversion input term / output theorem, in JSON |
| `$THM_DUMP_DIR/<proof>.ml.json` | top-level theorem names with line/column positions |

Both are needed together: the trace says what a tactic did, the theorem dump maps it back
to a named theorem and a source location.

### 11.7 Known limitations

From `TacticTrace/README.md`:

- **Multi-line goal terms.** HOL Light's preprocessor replaces line breaks inside a term
  with spaces, so `goal_linenum_end` and `goal_colnum_end` need adjusting before slicing
  the goal text out of the source file.
- **Tactics defined inside modules are not captured.**

---

## 12. Cleanup

```bash
cd ~/s2n-bignum/x86 && make clean
cd ~/s2n-bignum/tests && make clean
cd ~/s2n-bignum/benchmarks && make clean

rm -rf ~/tmp/*                   # build-proof.sh scratch leftovers
```

---

## Verified environment

| Component | Version |
|---|---|
| OS | Ubuntu 22.04.5, x86_64 |
| CPU | AMD Ryzen 7 7735U (8C/16T), BMI2/ADX/AVX2/SHA-NI, no AVX-512 |
| RAM | 14 GB |
| gcc | 11.4.0 |
| GNU as | 2.38 |
| OCaml | 4.14.2 (opam) |
| camlp5 | 8.00.04 |
| HOL Light | `2a1cea8` (2026-09-06) |
| VSCode extension | `monadius.hol-light-simple` 2.7.0 |

### Measured timings

| Operation | Time |
|---|---|
| `make -j$(nproc)` (s2n-bignum) | < 1 min |
| `make go` (tests) | ~2 min |
| `make go` (benchmarks) | ~1 h 50 min |
| `HOLLIGHT_USE_MODULE=1 make` (HOL Light, after `make clean`) | 1 min 23 s |
| `make tutorial -j2` | ~11 min |
| REPL cold start | 58 s |
| `needs "x86/proofs/base.ml"` in REPL | 5 min 44 s |
| Single proof execution (`bignum_montmul_p256`) | 161 s |
