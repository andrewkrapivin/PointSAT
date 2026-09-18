# PointSAT baseline

This directory benchmarks the repository's unmodified `PointSAT.py` with its
existing CNF, Kissat, scranfilize, and Localizer. The problem is **23 points with
no convex 7-gon and no empty convex 6-gon**. Root source and settings are untouched.

`settings.json` uses 40 scrambled SAT instances with omission of flippable
orientations. `no_flippable.json` uses the same first 20 scrambling seeds without
omission. Both use two workers, one Localizer thread per worker, 15-second
Localizer limits, and 60-second SAT limits. Both test partial realizations against
the complete CNF. The smaller ablation is paired only on seeds 0 through 19.

Dependencies and exact revisions are recorded in `versions.json`. They were
downloaded from their public upstream repositories into `direct/vendor/` and
built with optimization. Python packages live in `direct/vendor/venv/`.

From the repository root, after building those dependencies:

```bash
direct/vendor/venv/bin/python direct/baseline/run_baseline.py direct/baseline/settings.json --wall-seconds 540
direct/vendor/venv/bin/python direct/baseline/run_baseline.py direct/baseline/no_flippable.json --wall-seconds 360
direct/vendor/venv/bin/python direct/baseline/verify_baseline.py direct/baseline/with_flippable
direct/vendor/venv/bin/python direct/baseline/verify_baseline.py direct/baseline/without_flippable
direct/vendor/venv/bin/python direct/baseline/summarize_runs.py direct/baseline/with_flippable direct/baseline/without_flippable
```

The runner refuses to overwrite an existing run containing `raw_results.jsonl`;
copy a settings file and choose a fresh output folder for another run. PointSAT's
`multiprocessing.Manager` requires local IPC sockets. The first sandboxed launch
was denied that operation; the benchmark ran after a scoped sandbox escalation.

Each output directory contains full console logs, raw per-job records, settings,
and `summary.json` with wall time and aggregate child-process CPU time. Worker
time includes orchestration and validation overhead; CPU time is the better
measure when comparing concurrent runs. Compilation and dependency installation
are excluded from reported benchmark time. Timings share the machine with the
other experiments and are not isolated hardware measurements.

`verify_baseline.py` interprets the decimals printed by Localizer exactly,
translates and scales them into integers without rounding, then calls the
independent exhaustive C++ checker `direct/verify`. Its `exact_points/` files
include unsuccessful partial realizations: consult `exact_verification.jsonl`
before treating any as solutions. Counts of violated orientation constraints are
not counts of forbidden polygons. `normalize_points.py` can reduce large integer
coordinates while preserving every triple orientation; its grid search does not
claim a globally minimum grid.

The two small runs measure local throughput and candidate quality, but cannot
establish a reliable success rate for this rare-event search. For context, the
paper's larger current-method 23-point experiment found 423 valid configurations
from 200,000 abstract solutions in 1811 core-hours. The earlier ablation used a
different generation setup. Source: [PointSAT paper, section 6](https://arxiv.org/pdf/2607.02958).

## Measured baseline results

| Configuration | Samples | Wall seconds | CPU seconds | Valid 23-point witnesses |
|---|---:|---:|---:|---:|
| Omit flippables | 40 | 457.316 | 898.212 | 0 |
| Keep flippables | 20 | 211.690 | 405.937 | 0 |

All 60 printed coordinate sets were independently checked. Exact decimal and
exact binary64 interpretations agreed on every triple orientation. On paired
scrambling seeds 0–19, mean orientation violations were 11.4 with omission and
22.4 without. Those numbers count different sets of constraints; the independent
polygon counts in `comparison.json` provide a common geometric measure.

## Hybrid SAT plus direct repair

The four partial realizations with the fewest actual forbidden polygons were
selected across both baseline runs, normalized onto integer grids without
changing their orientations, then passed to the C++ direct repair solver. Each
trial has a 600-second limit and stops early on a solution; two run concurrently.
This is a hybrid search seeded by fresh SAT sampling. It does not use the known
paper coordinates and is also not a cold direct coordinate search.

```bash
direct/vendor/venv/bin/python direct/baseline/prepare_hybrid.py direct/baseline/with_flippable direct/baseline/without_flippable
direct/vendor/venv/bin/python direct/run_experiments.py direct/baseline/hybrid_jobs.json --output direct/baseline/hybrid --workers 2
```

Trial 2, seeded by scrambling seed 23's failed Localizer realization, found a
valid 23-point witness in **23.54 seconds** of repair (21.81 CPU seconds). It
started with three 7-gons and three 6-holes. The witness is
`hybrid/hybrid_sat_partial_2_seed4102.pts`; the corresponding `.meta.json` contains
an independent exhaustive certificate and executable hash. Its hull layers are
`(3, 4, 4, 4, 6, 2)`.

The winning seed's SAT/flippability stage cost 9.124 worker-seconds and its
Localizer/validation stage cost 15.740 worker-seconds. Adding those to repair
gives a **post-selection** chain of approximately 48.4 stage-seconds. That number
excludes the other sampled seeds and trials and must not be presented as a cold
time to discovery. Full baseline and portfolio resource use is preserved in the
result files so the complete cost can be included in comparisons.

The completed four-trial portfolio produced two valid witnesses. Trial 4 solved
its seven-gon/zero-hole input in 0.031 seconds of C++ repair (380 evaluated
states), yielding `hybrid/hybrid_sat_partial_4_seed4104.pts`. Trials 1 and 3 each
used their full 600 seconds and retained one forbidden hole. All four trials
cost 1196.17 CPU seconds; including the main 40-sample SAT/Localizer stage gives
2094.382 CPU seconds for this selected portfolio. Including the separate
20-sample ablation gives 2500.319 CPU seconds. Full provenance and both exact
certificate paths are in `hybrid_summary.json`.

After the user redirected effort to direct 23-point geometry, no further SAT
computations or polishing runs were launched. See `DIRECT_REPAIR.md` for the
subsequent completely geometric experiments.
