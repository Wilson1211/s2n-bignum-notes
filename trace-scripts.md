# Operational scripts

Everything needed to stand up the trace-generation environment and watch it run.
Copy this directory to the machine that will do the work; `run.sh` expects to sit at
the root of the run tree:

```
tactic-trace/              <- the run tree (ROOT)
├── run.sh  runloop.sh  batches.sh  status.sh  diskguard.sh  dedupe.py
├── trace-status.sh
├── docker/Dockerfile  build.sh  entrypoint.sh
├── hol-light/          bind-mounted to /opt/hol-light
├── opamroot/           bind-mounted to /opt/opamroot
├── s2n-bignum/         bind-mounted to /work/s2n-bignum
├── out/{traces,thms}/  bind-mounted to /out
└── scratch/            bind-mounted to /scratch  (TMPDIR)
```

None of the bulk directories are in git — see the main [README](trace-overview.md) §6.5.

## Setup and execution

| Script | What it does |
|---|---|
| `docker/build.sh` | Builds the `tp-hol:latest` toolchain image (~600 MB: OS packages + opam only). |
| `docker/Dockerfile` | ubuntu:22.04 + build deps + opam 2.3.0. Deliberately thin — hol-light, s2n-bignum and all outputs are bind-mounted, so results survive the container. |
| `docker/entrypoint.sh` | Activates the local opam switch, then prints a banner with the hol-light commit, OCaml version, the three sampling constants and the stack limit. Read that banner before trusting a run. |
| **`run.sh`** | **The entry point.** `--setup-hol` · `--setup-s2n` · `--rebuild-trace` · `--clean-native` · `-d` (detached) · `--logs` · `--shell` · `--stop`. Anything else is run verbatim inside the container. |
| `runloop.sh` | Run → filter → run, until everything is done or disk runs out. Detects a changed `exportTrace.ml` and forces `--clean-native`. |
| `batches.sh` | Runs directories in sequence, packing after each. **Superseded** by a single continuous queue — batching by directory leaves job slots idle while a directory's last few proofs finish. |

## Monitoring

| Script | What it does |
|---|---|
| **`trace-status.sh`** | **The one to reach for.** Progress against the 342 targets, per-directory coverage, and with `-l` every completed proof with its wall clock and every running proof with its elapsed time. `-c` adds container and host state. |
| `status.sh` | One-liner: is `runloop.sh` still alive. |
| `diskguard.sh` | Polls every 60 s and stops the container if free space falls below `FLOOR_GB` (default 30). Not running by default. |

```bash
./trace-status.sh          # summary + coverage
./trace-status.sh -l       # + per-proof timings
./trace-status.sh -lc      # + containers and disk
ROOT=/elsewhere ./trace-status.sh
```

## Housekeeping

| Script | What it does |
|---|---|
| `dedupe.py` | Hardlinks byte-identical trace JSONs together. Only touches proofs whose `.correct` is complete, so a running proof is never disturbed. Measured 12 GB → 5.9 GB in 19 s. |

## Two things that will bite you

**`%.native` does not depend on `kernel_wrapper.ml`.** After editing
`hol-light/TacticTrace/exportTrace.ml` you must run `--rebuild-trace` *and*
`--clean-native`, or make silently reuses binaries compiled with the old sampling
constants. This has already cost one four-hour run.

**A `.correct` file is created when the proof STARTS.** `tools/run-proof.sh` does
`"$native" 2>&1 > "$out"`, so the log exists from the first second. Completion means
the file contains `Dumped to` or `Running time:` — nothing else. If a proof is killed,
its half-written `.correct` will make the next `make` skip it. Clear those first, and
only those:

```bash
cd s2n-bignum/x86
for f in */*.correct; do grep -qE 'Dumped to|Running time:' "$f" || echo "$f"; done   # look
for f in */*.correct; do grep -qE 'Dumped to|Running time:' "$f" || rm -f "$f"; done  # then delete
```

Never delete `.native` to recover from this — those are the compiled proofs and
represent most of the CPU already spent.
