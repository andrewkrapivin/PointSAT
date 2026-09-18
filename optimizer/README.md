# Exact integer-coordinate compaction

This bounded C++17 engine makes existing valid point sets smaller. It does not
claim globally minimal coordinates and does not need a SAT solver or Localizer.
The default may change the labeled order type while preserving the requested
geometric property. Use an explicit preservation mode for classification studies.

`optimizer/compact` is the **standard frozen v1** engine. The additional v2
transformations are available as `optimizer/compact_v2`, an experimental option.
The same-mode comparison below favored v1 by area on five of six inputs, so
the paper-specific v2 result is not used to justify making v2 the default.
This default-selection decision follows that comparison; it is not an
independent future evaluation of the selection policy.

```sh
make -C optimizer
optimizer/compact --input direct/seeds/paper23.pts --output /tmp/compact.pts \
  --seconds 60 --seed 1 --family mixed23 --preserve-layers
make -C optimizer test
```

Inputs and outputs are `n` followed by `n` integer `x y` rows, with 3–40 points.
Input coordinates must have absolute value at most 10^12. General position and
the requested geometric property are required; invalid input is rejected before
the output is touched. The CLI wrapper may normalize larger exact coordinates
first, but must validate that normalization independently.

## Modes and output contract

| Option | Meaning |
|---|---|
| `--family mixed23` | No convex 7-gon and no empty convex 6-gon; default |
| `--family holes29` | No empty convex 6-gon |
| `--family gons32` | No convex 7-gon |
| `--family caps26` | No convex 7-gon and no 5-cap in actual coordinate x-order |
| `--preserve-order-type` | Preserve every original labeled orientation sign |
| `--preserve-layers` | Preserve the sequence of hull-layer sizes, not layer membership |
| `--seconds N` | Native wall-clock budget; default 60 |
| `--iterations N` | Additional proposal limit |
| `--seed S` | Explicit pseudorandom seed; default 1 |
| `--check` | Read-only exact count/layer report; output path not required |
| `--geometry-repair` | Experimental v2 only: bounded annealing of actual forbidden-polygon counts |
| `--target-width W --target-height H` | Experimental v2 only: aspirational grid proposals, not a hard constraint |

Family names select constraints; they do not enforce the number encoded in the
name. Geometry repair is incompatible with strict order-type preservation.
The 64×78 target is never enabled by default. Target dimensions may be omitted
to use the general compaction portfolio.

The objective is bounding-box area, with smaller maximum side as a tie-breaker.
Every stored incumbent is valid and no worse than the normalized input. JSONL
stdout includes wall/CPU seconds, proposal counters, bounds, original/final
layer-size sequences, and the number of changed original orientation signs.
The single output file is replaced atomically at most once a second when
improved and again at termination. There are no per-iteration point files.
SIGINT/SIGTERM request a checked final save. Exit 0 means successful execution;
it does not mean a requested target grid or a global optimum was reached.

The wrapper should still run an independent exact output audit. In default
and layer-preserving modes, a compact output need not realize its source SAT
orientation assignment or satisfy the original labeling's symmetry-breaking
clauses. Strict order-type mode fixes orientation signs, not x ordering or
Euclidean distances; cap constraints are checked separately in every mode.

## Algorithm

The standard portfolio combines exact feasible-line coordinate moves, positive
affine/projective proposals followed by integer rounding, and exact orientation
repair. Experimental v2 adds minimum-triangle-area centering and, for triangular
hulls, barycentric projective normalization to spread tightly clustered interior
points. These additions are not paper-coordinate special cases, but their
extra cost and changed search trajectory can worsen bounded results.

Orientation repair examines the integer neighbors of all exact rational
thresholds on a coordinate line. Optional geometry repair can temporarily
violate the target while searching, but a candidate is never stored unless
general position and the full requested property pass exact checks. Default
valid single-point moves can cross order-type boundaries; preservation flags
filter these transitions. No learned or floating-point score can bypass the
exact acceptance gate.

Floating point is used only to propose coordinates. Predicates use signed
128-bit integers, with input magnitudes bounded as above and temporary proposal
coordinates bounded conservatively below 10^13. Cross products therefore remain
below 8×10^26, well inside the signed-128-bit range. Translation and positive
axiswise integer-gcd reduction preserve signs. Output coordinates can span up
to twice the input magnitude bound. Bounding areas are also accumulated in
128-bit integers.

The fan/cap kernel is reused from `../direct/search.cpp`; the independent
validator is `../direct/verify.cpp`, which enumerates subsets and computes their
convex hulls instead. Tests include 120 complete-count comparisons on unrelated
random configurations across all four families, strict preservation checks,
malformed-input handling, bounded runs, and direct SIGINT/SIGTERM serialization.
Standard v1 passed 133 tests and experimental v2 passed 138, including additional
experimental-option checks. `make test` exercises both executables.

## Initial equal-budget comparison

Six fixtures, seed 1, 120 native wall seconds per method, at most three
single-core workers. This compares the frozen initial optimizer v1 against
`direct/compact`, using exactly the same input coordinates. Both outputs were
independently audited. All 12 runs were valid. Measured aggregate process CPU
time was 1,435.73 seconds for 1,440 requested worker-wall seconds.

| Input | Old final box | v1 final box |
|---|---:|---:|
| Paper23 | 671×565 | 253×253 |
| Archive23 sample7 | 27,234×36,540 | 686×1,908 |
| Archive23 sample2 | 108,059×94,525 | 238×315 |
| SAT-guided23 case33 | 256,366×125,237 | 4,080×1,485 |
| Feedback23 sample3 | 252,429×484,870 | 147×95 |
| Control-margin23 sample6 | 41,454×26,999 | 1,089×2,135 |

The new method reduced area more on all six fixtures in this single-seed test.
This is not a pure speed ablation: the old method fixes the full order type,
whereas v1 used its more permissive default. These are six related research
examples, not a statistically representative success-rate sample. The five
fresh inputs occupy two layer-size classes, not five different layer classes.

Archive sample7 changed from layers `[3,4,4,6,5,1]` to `[3,3,4,6,4,3]`; this is a
valid additional layer-class witness, not a preservation success. The other
five outputs retained their layer-size sequence. Detailed commands, input/output
hashes, CPU measurements, exact counts, and coordinates are in
[`results/paired120s-20260906/`](results/paired120s-20260906/).

## Provenance and frozen versions

The local `Happy_ending.pdf` is the PointSAT paper. Its Figure 1 and Section 5.2
give the 672×566 witness in `direct/seeds/paper23.pts`; they do not provide a
64×78 witness. That smaller dimension was only an aspirational target supplied
in conversation. No missing witness was fabricated or substituted.

- PDF SHA256: `7a1ea829fb5a83c7e6e8396f74c5098084a2ef0489ce31fcc2cfb2bb76bba5d6`.
- Paper fixture SHA256: `835db1678c6cad38b7595bb1eb68ed569c4638f605e3d1c58cf75f9e29f37623`.
- Standard v1/current binary: `80faa99d357cb6f21e55d6da442b8cde8362b8e150f0211142cf9dbcf9de3205`.
- Experimental v2 binary: `b64a9a166d0761bdc1e15df79f9cb6fe741d22a5bd3d49c0af99224ae7221482`.

`compact_v1.cpp` contains the complete standard source; `compact.cpp` contains
the experimental source. `make all` builds both executables. A fresh-directory
rebuild of v1 reproduced its frozen executable hash exactly; the Makefile keeps
the original translation-unit basename to preserve that reproducibility.

v2 adds barycentric projective normalization, triangle-margin steps, and the
opt-in actual-geometry repair. It was frozen before the held-out cross-family
tests. The initial six-case table above is v1 evidence, not a claim that its
numbers were measured with v2. `refinement_jobs.json` records the subsequent
bounded exploratory runs; no source or binary is changed while these run.

`benchmark.py` reproduces the matched-input protocol and refuses an existing
output directory, protecting historical results. Coordinate artifacts are
new outputs; original witnesses and prior experiment files are never replaced.

## Frozen-v2 refinement results

All seven runs in `results/refinement600s-20260906/` finished within their
native budgets and passed the independent exhaustive output audit. Five fresh
23-point inputs were run for 120 seconds each with `--preserve-layers`:

| Input | Final box | Preserved layer sizes |
|---|---:|---|
| Archive sample7 | 320×353 | 3,4,4,6,5,1 |
| Archive sample2 | 172×191 | 3,4,4,6,5,1 |
| SAT-guided case33 | 4,275×3,231 | 3,4,4,6,5,1 |
| Feedback sample3 | 101×121 | 3,4,4,6,5,1 |
| Control-margin sample6 | 597×728 | 3,5,5,5,4,1 |

This is not uniformly better than v1: case33 has a larger final box. Flags and
search trajectories differ, and one run per input is not a universal ranking.

Experimental v2's general mode, without target-grid or geometry-repair options, compacted
the paper fixture to **101×78** in a 600-second exploratory run, changing 145
labeled orientation signs while retaining its layer-size sequence. Another
600-second optional target-grid run, warm-started from the v1 feedback example,
went from 147×95 to 124×81; it did **not** attain 64×78. These follow-ups do not
claim order-type preservation or minimum possible grid dimensions.

## Frozen-v2 cross-family check

After freezing v2, two previously unused 23-point solutions (pipeline jobs090
and072), two newly certified 29-point solutions, and the 32-/26-point controls
were selected without tuning the engine on them. Each method received 30
seconds, seed1, with three workers maximum. Both used identical independently
validated, order-type-preserving normalization of each input. v2 used
`--preserve-layers`; the old compactor fixed the full order type (and x-order
for the cap case).

| Input | Old final box | v2 final box |
|---|---:|---:|
| Untouched23 job090 | 65,614×86,892 | 179×114 |
| Untouched23 job072 | 152,456×177,833 | 825×905 |
| New29 trial11 | 470,864×395,697 | 7,353×3,413 |
| New29 trial19 | 375,451×439,880 | 5,397×1,151 |
| 32-point control | 121×148 | 82×84 |
| 26-point no-5-cap control | 76×131 | 46×71 |

All twelve outputs passed the independent exhaustive property and layer audits.
Job090 adds the preserved layer class `[3,4,4,5,5,2]`; the 29-point examples
preserve `[3,4,7,7,7,1]`. The 32-/26-point controls are not newly discovered
witnesses. These results demonstrate applicability outside the paper fixture,
but still compare different preservation restrictions, not pure throughput.
Raw evidence is in `results/heldout30s-20260906/`. `heldout.py --ablation` runs
the additionally requested same-mode frozen-v1/v2 comparison on all six inputs,
with `--preserve-layers` enabled in both arms and no optional target/repair flags.

## Same-mode v1/v2 ablation

Both frozen engines were rerun on all six cross-family inputs with exactly the
same 30-second budget, seed1, family, and `--preserve-layers` mode. No algorithms
were changed, and no outcomes were omitted. Every output was independently
valid and retained the original layer-size sequence.

| Input | Standard v1 | Experimental v2 | Smaller area |
|---|---:|---:|---|
| Untouched23 job090 | 147×121 | 177×114 | v1 |
| Untouched23 job072 | 432×382 | 825×905 | v1 |
| New29 trial11 | 5,972×2,295 | 7,352×3,402 | v1 |
| New29 trial19 | 2,347×7,143 | 5,397×1,151 | v2 |
| 32-point control | 35×164 | 82×84 | v1 |
| 26-point control | 36×63 | 46×71 | v1 |

The v2 additions won one case and regressed on five by the stated area
objective. Its 32-point box is more square but has larger area. This is a fairer
test of the additional proposal mechanisms than comparing against the old
strict-order-type compactor; it still does not isolate a pure arithmetic-kernel
speedup or establish universal expected performance from six single-seed runs.
The standard engine therefore remains v1; v2 is available for optional
experimentation and produced the reported 101×78 paper-derived example.

The complete experiments comprise 43 runs, all independently valid, totaling
approximately 3,949.94 measured process CPU seconds. Condensed machine-readable
results are in [`results/summary.json`](results/summary.json); regenerate them
with `python3 optimizer/summarize.py`. Complete ablation commands, coordinate
files, hashes, CPU records and audits are in `results/ablation30s-20260906/`.
