# PointSAT improvement results — 5 September 2026

The supplied **19-point problem is solved**, with exact Euclidean threefold
rotational symmetry. The improved SAT/Localizer workflow also produced at least
**15 pairwise nonisomorphic 23-point order types** across the active and
unattended experiments. These are verified configurations, not a claim of
literature-wide novelty or new bounds for all four paper problems.

The additional active improvement hour ran from 05:26:41 to 06:26:49 UTC.
After that, frozen queues ran with occasional monitoring and an automatic
deadline of **10 AM EDT, or 14:00 UTC**. Maximum experiment concurrency was
eight single-core workers. All four supervisors finished before the cutoff;
the host process check at 14:00:20 UTC confirmed no experiment workers remained.
No solver jobs were launched after the deadline.

## The 19-point witness

Take the origin, these six points, and their 120° and 240° rotations:

```text
(-667, -1605)   (3333, 1586)   (-2656, 1313)
(-948,  1232)   (2362, 1537)   (33666, 3722)
```

All 969 triples are noncollinear. Exhaustive exact arithmetic over all 27,132
six-subsets finds 28 convex hexagons: 15 contain one point, 12 contain two,
and one contains four. None contain zero or three points. Independent Python
and C++ algebraic checks agree; a fresh SAT extension also passes every one of
the original CNF's 2,311,196 clauses.

[Exact coordinates, diagram, independent certificates and reproduction](success19/README.md).

The successful SAT-guided job took 552.032 seconds including failed earlier
samples. Its final warm Localizer attempt took 11 seconds after feedback
changed three primary orientations. The 11-second figure is **not** total
discovery time. This witness was not seeded from known solution coordinates.

The supplied formula actually compresses the 969 orientations into 327 signed
C3 orbits; treating its first 969 variables as ordinary triple orientations
would be incorrect. The explicit adapter and original-CNF check are essential.
The first extracted abstract assignment, and a particular relaxed target,
were independently proved nonrealizable. Those proofs concern those targets,
not the problem itself; the successful witness has a different orientation type.

## What improved

- PointSAT: persistent SAT/flippability checks, less repeated preprocessing,
  bounded workers, deterministic retries, warm starts, archived candidates,
  exact geometry/CNF acceptance, and optional UNSAT-core-guided retargeting.
- Bernardo's native Localizer: cached incident constraints, early rejection,
  correct coupled symmetry moves, archive fixes, native budgets, checkpointing
  on interruption, and round-trip coordinate output. Portable upstream patches
  and reproducible builds are included.
- Additional experiments: Overmars-style insertion/motion/backtracking,
  annealing, conflict-guided repair, exact arrangement relocation, symmetry-free
  lazy SAT, native analytic-gradient realization, and independently verified
  nonrealizability cuts.

Search hot paths are C/C++; Python handles orchestration and exact certification.
The public entry point remains `PointSAT.py SETTINGS.json`. See
[pipeline options](pipeline/README.md) and [Localizer build instructions](localizer/README.md).
The original user CNF and baseline sources were preserved; no commit was made.

## Measured performance and all four paper problems

On five paired 100,000-iteration repetitions per family, cached native
evaluation reproduced byte-identical coordinates and trajectories. Median CPU
times were:

| Paper problem | Reference CPU seconds | Cached CPU seconds | Speed ratio |
| --- | ---: | ---: | ---: |
| 23: no convex 7 / no empty 6 | 0.890849 | 0.474014 | 1.879× |
| 29: no empty 6 | 1.521926 | 0.718095 | 2.119× |
| 32: no convex 7 | 1.950335 | 0.938699 | 2.078× |
| 26: no convex 7 / no 5-cap | 1.174678 | 0.555158 | 2.116× |

This isolates evaluation speed, not end-to-end solving time. A separate matched
eight-input pipeline test using the same upstream native binary reduced wall
time from 91.945 to 79.791 seconds (13.2%); both versions solved 0/8.

The completed 120-job SAT-feedback portfolio produced ten additional certified
23-point outputs and the 19-point witness. It did not find new 26-, 29-, or
32-point solutions. All ten overnight 23-point convex-six counts differ from
one another and from the five earlier witnesses, proving at least 15 distinct
order types. Coordinates and full certificates are linked in the
[completed portfolio report](pipeline/unattended_20260905/RESULTS.md).

A separate prospective cold-search benchmark completed 80 registered SAT draws
(79 unique models, one timeout) and 831 native 45-second runs across all four
families. It found no valid geometries. Optional line and paired moves worsened
mean orientation error in every family; they remain off by default. Ordered-x
also incurred a substantial search cost, although cap acceptance must respect
the encoding's coordinate-order semantics. These negative results are preserved
in the [prospective benchmark report](benchmarks/overnight/RESULTS.md).

## Is direct geometry better than SAT here?

The evidence favors retaining a hybrid workflow, not replacing SAT. In the
earlier direct-geometric hour, Overmars-style search grew valid 22-point sets
from scratch; the best unseeded 23-point search retained one empty hexagon.
Direct refinement of the paper's witness did produce a valid 349 × 346 integer
configuration. These are different achievements: seeded compaction is not
cold discovery. [Direct methods, rates and certificates](../direct/RESULTS23.md).

For the 19-point problem, both free and C3 direct-objective searches were tried,
alongside an uncompressed symmetry-free SAT/proof-filter arm. The successful
realization came from the C3 SAT-feedback workflow. Failure of another bounded
search is not evidence of nonexistence or a universal solver ranking.
Final arm-specific counts are in the
[geometric search report](localizer/unattended14/RESULTS.md) and
[symmetry-free proof-search report](lazy19/overnight/RESULTS.md).

The direct 19-point queue completed 60 full 900-second runs plus two
deadline-censored runs, evaluating 3.35 billion proposals; 66 other registered
jobs were never started. Its 1,041 exact candidate audits found no solution.
The symmetry-free producer saved 639 new independently verified impossibility
proofs, in addition to 18 reused cuts. Its two unresolved exported targets and
457 geometric fallback runs yielded no witness. Interrupted proofs and skipped
jobs are not counted as mathematical or experimental successes.

## Reproducibility and next targets

Frozen manifests retain input/binary hashes, seeds, wall/CPU measurements where
available, interrupted runs and exact certificates. Core validation included
115,975 helper checks, 25 pipeline regression tests, exact geometry differential
tests, native cache/reference agreement, and independent impossibility-proof
verification. Failed numerical realization alone never authorizes a permanent
SAT exclusion.

The most promising follow-up here is to retain the fast default native kernel,
archive exact geometric candidates, and use bounded SAT feedback plus verified
impossibility cuts. Optional search moves need problem-specific evaluation.
[Additional research targets](RESEARCH_TARGETS.md) records garment-number and
colored empty-triangle experiments with source references; those are proposed
future problems, not claimed solved results.
