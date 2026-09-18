# Total-wall anytime study

Frozen registration: [anytime_20260907/registration.json](anytime_20260907/registration.json),
SHA256 `bc9b176c5c291e62660c29a78155b06943a0a5f9d92cd754158a429cc9812f58`.
Registration does not itself launch a search.

The main queue was launched on **2026-09-07 at 01:55:14 UTC** in the detached
`PointSAT:anytime-bench` tmux window, using
[`run_anytime_20260907.sh`](run_anytime_20260907.sh). It is restricted to CPU
affinity `[0, 1]`. The append-only progress log is
[`anytime_20260907/run.log`](anytime_20260907/run.log).

The separate six-trajectory smoke test finished with three exact online
successes on the known positive control, three timeouts on the fresh target,
one exercised SAT-repair/warm-restart cycle, no online checker errors, and
145 preserved artifacts passing integrity checks. The smoke's two targets,
60-second horizon, timings and generated report are **excluded from the main
study**. See [`anytime_smoke_20260907/SMOKE_ONLY.md`](anytime_smoke_20260907/SMOKE_ONLY.md).

## What is compared

There are **100 fixed SAT targets and 560 trajectories**, with one registered
seed per target and at most two single-core workers. Each family has 20 distinct
canonical target types; this is a reused, deliberately diverse corpus, not an
IID or unseen test population. The 19-point corpus contains 9 fresh and 11
historical initial-SAT targets. Known coordinate solutions are not search seeds.

| Family | Actual geometric goal | Strategies | Trajectories |
| --- | --- | ---: | ---: |
| 19 points | No convex hexagon with 0 or 3 other points inside | 4 | 80 |
| 23 points | No convex 7-gon and no empty 6-gon | 6 | 120 |
| 29 points | No empty 6-gon | 6 | 120 |
| 32 points | No convex 7-gon | 6 | 120 |
| 26 points | No convex 7-gon and no 5-cap | 6 | 120 |

The 19-point strategies are upstream, v4 fixed-target, v4 warm-retry, and v4
feedback. The paper-family strategies are upstream, v6 plain, v6 line, v6
line+pair, v6 warm-retry, and v6 feedback. Retry and feedback share 15-second
native bursts and online checks; feedback additionally spends time on SAT
retargeting. Continuous strategies check naturally returned outputs and the
final stopped output; an unreturned internal incumbent is not a solved result.

**30/60/120 seconds are milestones on one 120-second trajectory**, not three
independent runs or checkpoints retrospectively searched for a good result.
The clock starts immediately before launching the worker and includes imports,
initial flippability, native work, retries, SAT feedback, and online exact
verification. All strategies reserve 3 seconds for final verification. A result
counts only when its exact geometric certificate and witness have been saved
and checked before the deadline. CNF consistency and exact C3 reconstruction
are secondary; they do not create or remove a primary online success.

The upstream arm uses the original git-blob `check_flippable` and original
Localizer. Updated arms use the current flippability checker. The logical
initial targets must agree, but their actual preparation costs are charged.
Thus upstream-versus-updated is a **package comparison**, not a cache-only
ablation. All arms share the orientation adapter, logging, deadline wrapper,
and exact acceptance rule; this is not a literal execution of the entire old
PointSAT driver. SAT target generation is excluded. The 19-point arms share the
same rotation cycles and fixed center; caps use the prior strict-x definition
without a new rejection of repeated x coordinates or an `--ordered-x` treatment.

## Runtime and accounting

The primary allowance is 560 × 120 = **67,200 worker-seconds (18h40m)**, or
nominally **9h20m on two cores** if every trajectory exhausts its allowance.
Successful early returns reduce that. Each trajectory can additionally spend
up to 20 seconds on post-hoc auditing: at most 11,200 worker-seconds, nominally
another 1h33m20s on two cores. Allow roughly 11 hours including audits, bounded
cleanup, scheduling and final reporting; this is not a guaranteed host-runtime
deadline. The final report process is separately capped at 300 seconds.

All persisted attempts, including interrupted attempts, remain in SQLite and
contribute to recorded cost totals. A deadline termination is a completed,
censored trajectory, not automatically an operational error. External STOP
leaves an incomplete attempt, which is retained and rerun fresh on resume.
Forced termination can make process CPU accounting a lower bound; that flag is
recorded. Post-hoc audit costs remain separate and cannot backdate a success.

## Launch, pause, resume, status

Run from `/home/andrew/PointSAT`, after the separate real smoke checks pass.
For disconnect tolerance, use a persistent terminal such as a tmux session.
Only one coordinator may run; the registration's lock prevents duplicates.

```sh
python3 benchmarks/anytime_20260907/frozen/anytime_compare.py run \
  --registration benchmarks/anytime_20260907/registration.json --workers 2
```

To pause gracefully, including across PID namespaces:

```sh
touch benchmarks/anytime_20260907/STOP
```

Wait for the coordinator to exit and its owned workers to finish cleanup.
To resume, remove only the STOP marker and repeat the launch command above:

```sh
rm -- benchmarks/anytime_20260907/STOP
```

Completed case/strategy rows are skipped. Interrupted native trajectories are
not resumed from their internal state, and previous attempt artifacts are not
overwritten. Do not modify frozen files or the registration to change a protocol.

Once `results.sqlite` exists, this status query is read-only; it prints counts
keyed by `complete` (`0` = incomplete attempts, `1` = completed trajectories):

```sh
python3 -c 'import sqlite3; d=sqlite3.connect("file:benchmarks/anytime_20260907/results.sqlite?mode=ro",uri=True); print(dict(d.execute("SELECT complete,COUNT(*) FROM trials GROUP BY complete")))'
```

After the coordinator has stopped, independently check stored integrity:

```sh
python3 benchmarks/anytime_20260907/frozen/anytime_compare.py verify \
  --registration benchmarks/anytime_20260907/registration.json
```

On full completion, the coordinator automatically writes `summary.json`, checks
all stored artifact hashes and online certificates into `integrity.json`, and
builds the final PDF/README/JSON in
[`../reports/anytime_20260907/`](../reports/anytime_20260907/).
`report.log` and `report-process.json` record report execution. An existing
report directory is never overwritten; inspect any partial output before
arranging a separate new report destination.

## Earlier diagnostic results stay separate

The stopped native-budget study has 110/180 completed 19-point conditions and
15/1,200 completed paper-family conditions. Its 10/30/60-second allowances
excluded preparation, feedback and auditing, so it is **not the main
equal-total-cost comparison**. Its partial results and two interrupted 19-point
attempts are retained unchanged for diagnostics and historical cost accounting.
Do not pool those denominators, timing curves, or outcomes into this study.
