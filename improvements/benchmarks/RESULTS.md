# Independent measurements and certificates

Snapshot: 2026-09-05, active experiments before the unattended 14:00 UTC deadline.
All searches ran locally. The search kernels are native C/C++; Python schedules
runs, checks certificates, and summarizes results. This file distinguishes
measured speed, empirical search quality, and mathematical certificates.

## Native evaluator speed: a reproducible 1.88–2.12× improvement

Five paired repetitions per problem, identical native v1 binary and seed42,
100,000 actual iterations in every run. The only treatment is full reference
evaluation versus incremental evaluation; all 20 coordinate-file pairs are
bit-for-bit identical. These fresh SAT inputs do not solve early.

| Problem | Reference median CPU | Incremental median CPU | Median paired speedup |
| --- | ---: | ---: | ---: |
| 23: no convex7 / no empty6 | 0.891s | 0.474s | 1.88× |
| 29: no empty6 | 1.522s | 0.718s | 2.12× |
| 32: no convex7 | 1.950s | 0.939s | 2.08× |
| 26: no convex7 / no5cap | 1.175s | 0.555s | 2.12× |

Source: [fixed-work results](results/kernel_fresh_v1/summary.json), including
binary hash, proposal counts, and exact constraint-evaluation counts. This is
an evaluator ablation, **not** a claim that the entire new PointSAT pipeline is
twice as fast. Earlier known-realizable controls solved too early for clean
fixed-work comparisons on26/32 and are not used for this headline.

## Matched 15-second search quality on all four problems

The first fresh corpus froze two tuning and three heldout SAT seeds per family
before seeing outcomes. Fifteen23/26/32 SAT models were generated; all five29
draws reached their90-second SAT cap. A separate default-Kissat29 draw succeeded
in208.10s wall /207.13s CPU and is explicitly a one-model late-heldout sample.
Every Localizer pair uses the same full orientation file and random seed;
three native seeds per fresh model. No known coordinate seed is supplied.

| Heldout problem | Unique SAT models | Upstream mean violations | v1 mean violations | Optional v3 line10 |
| --- | ---: | ---: | ---: | ---: |
| 23 | 3 | 25.22 | 24.22 | 29.78 |
| 29, late sample | 1 | 53.33 | 49.33 | 47.33 |
| 32 | 3 | 168.56 | 161.33 | 175.67 |
| 26 | 3 | 41.22 | 38.67 | 37.44 |

All three treatments had zero exact realizations and zero valid geometries on
these48 fresh runs. The v1 evaluator is a useful speed improvement; these small
samples do not establish a general success-rate improvement. The line-search
feature is mixed and worse on23/32 here, so it remains opt-in. Full paired
wins/ties/losses, CPU/wall totals, and exploratory unique-model-cluster intervals
are in [v1 comparison](fresh_v1_comparison.json) and
[v3 comparison](fresh_v3_comparison.json).

On60 legacy development23 inputs, v1 lowered mean violations14.97→14.28,
with24 wins,21 ties,15 regressions. More importantly, its saved geometry gave
one genuine23 solution versus none for upstream, although two target
orientations remained violated. This is development evidence, not heldout
success-rate evidence. See [legacy comparison](legacy23_comparison.json).

A second prospective corpus froze v5 and its default/line10/pair+line10
treatments before generating new SAT inputs. Both new29 draws timed out600s.
Six generated cases contain only four unique models: the two32 models match
each other, as do the two26 models. Analyses therefore cluster by orientation
SHA256, not SAT seed. See [registration](round2_corpus/registered.json),
[all SAT outcomes](round2_corpus/manifest.json),
[line comparison](round2_line10_comparison.json), and
[pair+line comparison](round2_pair_line10_comparison.json). All54 native runs
finished, with zero geometrically valid outputs. Mean errors for
default/line/pair+line were23:19.33/19.00/23.50;
32:116.33/119.67/131.50;26:37.83/40.50/45.17. This small prospective sample
does not support enabling the paired proposal by default.

## Five independently certified, distinct23-point solutions

All have no convex7, no empty6, and general position. Each original decimal
output was converted to exact integers and exhaustively checked with an
independent arbitrary-precision verifier. A compact integer normalization
preserves all1,771 labeled orientation signs and is separately checked using
the independent `__int128` subset validator. Each verification enumerates
245,157 seven-subsets and100,947 six-subsets. Full original-CNF extensions are
also saved; some geometries require only radial relabeling to meet its labeling
symmetry-breaking convention.

| Source experiment | Convex6 count | Normalized box | Certificate |
| --- | ---: | ---: | --- |
| Cold native v1, legacy SAT case33 | 772 | 1,000,000 ×740,898 | [case33](successes/sat-guided23-case33/certificate.json) |
| UNSAT-core feedback, fresh sample3 | 591 | 590,237 ×1,000,000 | [feedback](successes/feedback23-sample3/certificate.json) |
| Archive/core feedback, fresh sample2 | 642 | 717,390 ×1,000,000 | [archive2](successes/archive23-sample2/certificate.json) |
| Archive/core feedback, fresh sample7 | 606 | 100,000 ×85,769 | [archive7](successes/archive23-sample7/certificate.json) |
| Target-margin core feedback, sample6 | 573 | 100,000 ×88,656 | [margin6](successes/control-margin23-sample6/certificate.json) |

The published fixture has753 convex6s. These differing invariant counts prove
the five experimental order types are pairwise different and different from
that fixture, even after relabeling/reflection. This is not a claim of a
literature-wide novelty search. The first four have hull layers3,4,4,6,5,1;
the fifth has3,5,5,5,4,1. Their SAT-guided searches were not initialized with
the paper's known coordinates.

The paired Python orchestration isolation (same upstream native binary, eight
SAT seeds, identical models/flippability sets) reduced total wall91.945→79.791s
and aggregate CPU179.932→156.726s. All16 saved outputs were independently
invalid geometrically. This pipeline test is separate from the native kernel
test and from exploratory successful feedback portfolios.

## Correctness findings that matter to acceptance

1. A Localizer target mismatch need not make its geometry invalid. Exact
   geometry fallback plus label-only radial canonicalization recovered genuine
   solutions that a target-error-only gate would discard.
2. For the26 cap problem, realizing orientation signs is **not enough**: caps
   depend on the x direction, which the SAT encoding implicitly orders.
   A known-control output with zero target errors still has forbidden5caps.
   Exhaustively scanning all650 nondegenerate projection intervals found a
   best count27, so no nondegenerate affine x projection/relabel can repair that fixed
   geometry. [Projection certificate](cap_projection_control26.json).
   The pipeline now checks actual5caps before acceptance; optional ordered-x
   native proposals are a separate prospective treatment, not retroactive
   evidence of success.
3. The supplied19-point abstract orientation model is rigorously
   **nonrealizable**, even without requiring Euclidean threefold symmetry.
   An independently verified certificate combines882 strict signed
   Grassmann–Pluecker product inequalities with positive integer weights;
   all902 bracket exponents cancel exactly, giving the contradiction0>0.
   The matching blocking clause contains967 orientation literals.
   [Independent proof check](supplied19_bfp_independent.json),
   [producer's exact certificate](../realizability/results/supplied19-rational.json).
   This rules out only that model (and assignments keeping those premises),
   **not** the19-point geometric problem.
   A second certificate independently proves the942-orientation relaxed
   target `model002-relaxed.or` itself nonrealizable:846 inequalities,
   exact cancellation on865 bracket variables, and939 blocking premises,
   all explicitly present in the partial input. No omitted sign is assumed.
   [Partial-target proof check](relaxed002_bfp_independent.json).

## Independent oracle and proof testing

- Native19 geometry oracle:200 random/adversarial GP fixtures versus exhaustive
  arbitrary-integer hull/interior enumeration, all passed.
- Lazy19 SAT cut oracle:40 random GP fixtures,2,126 independently falsified
  obstruction clauses, all cuts satisfied by the supplied abstract valid
  target model;3,450,300 real-geometry/base-clause checks passed.
- Exact Q(sqrt3) C3 checker:160,801 algebraic-sign self-tests; existing physical
  candidates,10 high-precision random Euclidean C3 fixtures, and20 exact
  integer-lattice C3 fixtures agree with independent polygon enumeration.
- BFP proof checker: no imports from its producer;85,800 exact GP product
  identity/inequality checks on40 random realizable GP sets, plus deliberate
  certificate-weight corruption rejection.
- Matched-run shutdown and unattended five-treatment smoke tests passed.

See [protocol and commands](README.md), [native19 differential report](geometry19_independent_tests.json),
and [lazy19 independent report](lazy19_independent_tests.json).

## Unattended continuation

[Frozen queue](overnight/jobs.json) and [registration](overnight/registration.json)
contain80 prospective SAT draws across all four problems. The root supervisor
limits aggregate workers and stops at14:00UTC. Each native treatment is
single-core,45 seconds, with three matched seeds and prospectively randomized
treatment order. SAT failures stay in the denominator. Every saved geometry
is checked; successes also receive independent original-CNF certificates.
No result from this queue is claimed before its actual audit completes.
