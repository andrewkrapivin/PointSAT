# 23-point direct-search experiments

Target: 23 integer-coordinate points in general position with **no convex
7-gon and no empty convex 6-gon**. The main implementation is C++17,
compiled with GCC 13.3, `-O3 -march=native`. Python schedules processes and
records results. The environment exposes eight AMD Ryzen AI 9 365 vCPUs
under KVM and about 8.7 GiB RAM; measurements describe this environment,
not an isolated bare-metal processor.

The session began at 03:42:47 UTC on 2026-09-05. After the user's 04:05
refocus, all sustained computation targeted this 23-point problem. Related
experiments from the initial broader request remain archived separately.
Searches and final checks concluded around 04:43 UTC: approximately one
hour of machine time, including implementation, validation, and tuning.

## Findings

The direct searches from random coordinates reached valid **22-point**
sets. Fixed-size searches reached **23 points with zero 7-gons and one
6-hole**. No unseeded valid 23-point set was found during this hour.
Those near misses are not solutions. A particularly useful
finding is that the best one-hole configuration cannot be repaired by
relocating any single point while fixing the other 22; exact arrangement
enumeration checked all 23 choices, including deletions that expose holes.
This is a statement about those specific coordinates, not an impossibility
result for the 23-point problem.

Direct geometric refinement did produce an attractive valid **349 × 346**
23-point configuration, starting from the paper's Figure 1. The paper's
example occupies 672 × 566, so bounding-box area fell from 380,352 to
120,754 (about 68%). Its order type also changed: 39 labeled orientation
signs differ, and its number of convex six-point subsets differs from the
published example. This is a seeded refinement, not a discovery from
random coordinates.

- [Refined valid 23-point coordinates](results/2026-09-05/polished/repair23-grid400-s12-compact.pts)
- [Valid 22-point set grown by direct search](results/2026-09-05/pool-hull3-snapshot22.pts)
- [One-hole local trap, **not a solution**](results/2026-09-05/one-hole-local-trap23.pts)
- [All 23 exact relocation scans](results/2026-09-05/arrangement-all-relocations/summary.json)

## Methods and observed performance

| Method | Outcome or measurement |
|---|---|
| Overmars insertion / Brownian motion / backtracking | Valid 22 points from scratch; normalization raised throughput substantially |
| Quadratic insertion oracle, fixed valid 22 seed | 325,995 proposals in 3.000 wall seconds / 1.498 CPU seconds: about 217,617 proposals per CPU-second |
| Plain annealing, 600 s | Best 23-point incumbent: 0 gons, 2 holes; 6,180,624 scored evaluations |
| Late acceptance, 600 s | Best incumbent: 0 gons, 2 holes; 6,082,517 scored evaluations |
| Conflict-guided coordinate / triangle search | Reached 0 gons, 1 hole from entirely geometric seeds |
| Candidate pools, 600 s | 32,356 pools, 194,136 new candidate points, 4,373 valid replacements of 22-point sets; best size 22 |
| Exact arrangement relocation | 520,191 cells across all 23 deletions checked in 4.892 s; no single-point repair of the saved local trap |
| Exact insertion plus Overmars motion, 600 s | 1,856 exhaustive scans of evolving 22-point sets; best size 22; 504.718 CPU s |
| Hole-directed / guided breakout repair | 15.8 million scored candidates across ten trials, 2,291 CPU s; best 0 gons, 1 hole |
| Coupled two-point repair, 240 s | 1,067 exhaustive insertion scans after perturbing another point; no solution (one final scan timed out) |
| Small-grid seeded repair | Valid 392 × 394 in 0.040 s; subsequent exact compaction yielded 349 × 346 |

Insertion proposals and complete scored evaluations are different units
of work. Both wall and CPU rates are provided where measured. Machine
load varied because searches and development checks ran concurrently.
The one paired cutoff benchmark reduced CPU time from 5.56 to 4.24 s
(1.31×) for exactly 100,000 proposals with identical outputs; this is not
a claim that every workload receives that speedup.

The final triangle solver updates only triples involving the moved point,
uses bit masks for geometry, rejects moves as soon as their partial count
exceeds a pre-sampled acceptance threshold, and retains a bank of equally
good incumbents. The Overmars solver includes O(n²) angular-sweep insertion,
exact integer normalization, orientation-preserving move shortcuts,
line-intersection proposals, boundary-crossing moves, and optional complete
arrangement scans. Pool preprocessing was accelerated by enumerating convex
fans directly instead of checking every arbitrary subset.

## Is SAT the best tool?

This experiment supports direct geometry as a useful search and refinement
component. It does not establish that direct search replaces SAT for
finding 23-point configurations from scratch. SAT also supports exclusion
proofs; these time-bounded stochastic searches do not prove nonexistence.

Before the refocus, a local PointSAT baseline generated 40 abstract models
and tested their realizations: zero full solutions in 457.3 wall seconds /
898.2 aggregate CPU seconds. A 20-trial ablation also found none. Direct
repair then solved two of four selected SAT near misses in 23.535 and
0.031 seconds of repair, respectively. These are **SAT-seeded hybrid
successes** and include selection and preceding SAT/realization costs;
the repair times are not unbiased end-to-end discovery times.

Those samples are too small and selected to rank universal success rates.
For this session, geometric repair and exact insertion checks are useful
additions to the existing SAT workflow. The paper's broader measurements
also distinguish SAT's generality from the speed of dedicated geometric
algorithms. [PointSAT paper](https://arxiv.org/abs/2607.02958)

## Correctness and reproducibility

`verify.cpp` independently enumerates every 7- and 6-subset, computes its
convex hull, and checks emptiness with signed 128-bit determinants. A
23-point certificate therefore checks 245,157 heptagon subsets and 100,947
hexagon subsets, plus general position. `verify_big.cpp` is a separate
arbitrary-precision implementation for large coordinate certificates.

Validation includes thousands of differential polygon-count / insertion
tests, 20,000 incremental-orientation comparisons, malformed and degenerate
input tests, and arbitrary-precision affine tests beyond the 128-bit range.
The final rebuilt binaries passed `make -C direct test`, another 1,089
oracle comparisons including caps, the 20,000 incremental tests, and 20
arbitrary-precision affine comparisons. All search processes were stopped
before handoff; no unattended computation remains.
Exact arrangement enumeration was calibrated both by reconstructing a
removed point of a known valid 23-point set and by filling an existing hole.
Calibration examples are not counted as new discoveries.

The single-point trap result also covers moving a point into an existing
hole: `--allow-base-holes` requires the new point to fill **every** hole of
the deletion baseline and independently avoids new forbidden polygons
through the inserted point. Merely checking hole-free deletions would not
justify the complete relocation statement.

Run commands are in [README.md](README.md). The focused one-hour portfolio
is [portfolio23.json](portfolio23.json). Logs and per-job metadata preserve
seeds, parameters, executable hashes, timings, incumbents, and certificates.
Initial development runs that lack CPU timing are labeled accordingly.
Some superseded runs were interrupted deliberately; their partial results
must not be treated as completed time limits.

The comparison figure is available as [PNG](results/2026-09-05/configurations23.png),
[SVG](results/2026-09-05/configurations23.svg), and
[PDF](results/2026-09-05/configurations23.pdf).

Additional method details: [Overmars](overmars_notes.md),
[exact insertion and coupled repair](arrangement_notes.md), and
[hole-directed breakout](baseline/DIRECT_REPAIR.md).
