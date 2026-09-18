# Native Localizer improvements

Based on Bernardo Subercaseaux's Localizer, commit
5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb.

The upstream binary was preserved before editing or rebuilding as
localizer_baseline (SHA256
f5c0819778eba20ac1d8c1f231e922ac0f309372e8d79db9476aca801200b98c).
localizer_v1 is the immutable first candidate (SHA256
ee6644d849da68e2f86e5c8873fdb41e19f47a132fd24a0832b9420326028492),
frozen 2026-09-05 05:00:39 UTC before revised held-out benchmarking.

## Reproduce

With a clean checkout of that upstream commit, run:
bash improvements/localizer/build.sh /path/to/localizer

The tracked upstream.patch contains the final source changes, including the new
src/solver_fast.c. Vendor files and native executables may be ignored by
PointSAT's Git rules; the patch is the portable deliverable. The original
src/solver.c remains unchanged for inspection, but the revised main uses
solver_fast.c.

Pass the absolute path of v1.patch as a second build.sh argument to reproduce
the immutable benchmark candidate. Its reproduction was tested in a clean local
clone: compiled binary SHA256 matched localizer_v1 exactly, and upstream tests
passed. The final patch adds optional experiments; no held-out feedback was used
to tune them.

## Changes

- Cached constraint-violation flags: accepted moves update only incident
  constraints and per-point scores; rejected moves stop as soon as their
  violation count exceeds the old incident total.
- Symmetry proposals move an orbit leader, then evaluate the deduplicated union
  of incident constraints. Previously follower proposals were overwritten by
  unchanged leaders; full rescoring was used for every move.
- Correct descending top-K archive shifts and nonnegative initialized-entry
  sampling. These change the search, independently of evaluation speed.
- Optional warm starts and native wall/iteration budgets.
- SIGINT/SIGTERM only set a lock-free atomic flag. Main joins workers, checks the
  stored objective, then writes the best incumbent. Output uses 17 significant
  digits so parsed doubles round-trip.
- Validate ranges, malformed inputs, finite coordinates and conflicting
  fixed/symmetry specifications. Optional file arguments are null-initialized.
- Positive minimum-distance penalties use full scoring for correctness.
  Collinearity constraints use abs(det) <= 1e-6 instead of being silently
  ignored; nonfinite determinants are always violations.
- Makefile tracks all included source dependencies and uses pthread flags.

## Added options

Existing flags retain their meanings.

| Flag | Meaning |
|---|---|
| -w FILE | Warm start: exactly N indexed rows i x y, indices 1..N |
| -T SECONDS | Native wall budget per worker, checked each outer iteration |
| -I ITERATIONS | Deterministic outer-iteration budget per worker |
| -q | Suppress progress messages; final status/JSON remain |
| --reference-evaluation | Same revised search, uncached old/new incident evaluation; no early rejection |
| --check-every K | Recompute cached flags/scores every K iterations, assertions enabled |

Long aliases are --warm-start, --seconds, and --max-iterations.
Final status is SOLVED/STOPPED plus Violations: N and one JSON statistics row
per thread. Budget expiration is a normal exit (0), not a claim of success.
Only zero violations realizes the input orientation system; exact external
geometric validation is required for mathematical claims. Fixed coordinates take
priority over warm starts; a fixed orbit member freezes the whole rotation orbit.

In v4 and later, --archive-prefix PREFIX additionally saves up to ten
initialized archive entries as PREFIX-00.real through PREFIX-09.real, in increasing
native objective order. Entries can be duplicates; callers should hash-deduplicate
and independently audit each candidate. Every archived native objective is
recomputed before serialization. This option is off by default and changes no
search decisions; a 100,000-iteration check reproduced identical v3 coordinates.

## Evidence and benchmark boundaries

A 5-second gprof profile of untouched upstream (-O3 -pg, seed 42,
23-point 7gon-6hole-test4-2.or) attributed 95.95% of sampled runtime to evaluate
(10,250,371 calls). This identifies the bottleneck, not a fair baseline speed
measurement: profiling itself adds overhead.

Initial revised reference-vs-cached check: 100,000 outer iterations, seed 42,
998,654 proposals, byte-identical final coordinate files, best 20 violations,
461,379,919 versus 138,035,881 determinant evaluations. A single loaded-machine
run took 0.968 versus 0.482 seconds; use the repeated benchmark for performance
claims, not that preliminary timing. Cache consistency passed 10,000 iterations
checked after every iteration; all upstream unit tests passed.

Reference mode isolates caching/early-rejection speed within the revised search.
Upstream-vs-revised wall-budget benchmarks additionally include archive/symmetry
search changes and cannot attribute objective gains solely to speed. Remaining
orientation violations are not a geometric solution certificate.

The independent five-repeat CPU-time ablation (100,000-iteration cap, stopping
early when solved) measured the following median ratios, with byte-identical
coordinates and search counters in every pair:

| Case | Reference CPU s | Cached CPU s | Ratio |
|---|---:|---:|---:|
| 23, no 7-gon/no 6-hole | 1.402382 | 0.651715 | 2.152x |
| 29, no 6-hole | 1.111773 | 0.534886 | 2.079x |
| 32, no 7-gon | 0.029766 | 0.015210 | 1.957x |
| 26, no 7-gon/no 5-cap | 0.007687 | 0.005178 | 1.485x |

These are same-revised-search kernel ablations, not total speedups over upstream.
The last two solve quickly and consequently include proportionally more startup
overhead. Raw records and manifests are in ../benchmarks/results/kernel_v1/.

On the 60-run legacy 23-point tuning set, the preserved upstream binary produced
zero geometrically valid outputs and v1 produced one. The independently audited
example is ../benchmarks/results/legacy23_v1/legacy23-with_flippable-33-s1/points.real
(with an exact integer .pts companion). It has no convex 7-gon, no empty convex
6-gon, and no collinear triples, despite two mismatches with the supplied partial
orientation target. Thus geometric fallback auditing can accept useful results
that a strict orientation-success check would discard. This isolated success is
not a reliable success-rate estimate. The paired native objective comparison had
24 wins, 21 ties, and 15 regressions, with mean violations 14.97 versus 14.28.

## Optional line-search extension (v3)

The native binary localizer_v3 adds --line-every K. Every Kth candidate replaces
the random displacement by a minimum-violation interval along the sampled line.
For one free point each determinant is affine along this line; for a coupled
rotation orbit it is quadratic. The implementation sorts real roots of the
determinant threshold equations, sweeps interval scores, and chooses an interior
midpoint. The ordinary cached evaluator then verifies the actual floating-point
candidate, so numerical root inaccuracies cannot bypass acceptance checks.

This adds computation per proposal; it is an experimental search improvement,
not part of the frozen v1 comparison. --min-radius R and --max-radius R expose
the proposal scales (defaults 0.1 and 15). A warm-repair experiment can use
-w previous.real -i 24 --min-radius 0.000001 --line-every 10. Lower-radius and
line options must be reported when comparing search outcomes.

The default no-symmetry cached path also reads the already maintained per-point
violation count instead of summing old incident flags again. Default v2/v1
coordinates matched after 100,000 fixed-seed iterations.

native_tests.c tests descending archive shifts, safe archive sampling, C/NaN
handling, and 400 random affine/threefold-quadratic line sweeps against 1,001
grid positions each (including occasional collinearity targets). All passed.
AddressSanitizer and UndefinedBehaviorSanitizer also passed with leak detection
disabled: LeakSanitizer cannot operate under this environment's ptrace wrapper.

test_cli.py additionally passes malformed/range/nonfinite input checks, zero-step
warm-start completion, minimum-distance penalties, fixed orbit followers and
conflicting symmetry, two-thread native budgets, and two-thread SIGINT/SIGTERM
serialization. Rebuilding upstream.patch in a clean checkout produced exactly
the frozen v3 SHA256 7eed005b90a3298b92aed975d8392ffc46f745559144792d47b674184aae003e
(that revision is now preserved separately as v3.patch). The final v4 binary is
5033c4f1a8c206f28fee43bfa39f82a4b1787b17e7701a795268c2e5d4f7720b and differs
only in optional archive-output support. v4.patch and v5.patch preserve later
intermediate revisions; upstream.patch now reproduces final v6.

## Resumed-hour native additions

v5 adds optional --pair-every K: every Kth proposal moves two points (or two
rotation orbits). Its affected constraints are the deduplicated incident union.
If combined with --line-every, the four-dimensional direction still produces
quadratic determinant equations along its one-dimensional parameter. Default
mode is unchanged. Expanded native tests cover 800 single/paired line sweeps
against 1,001 grid positions each. A 10,000-iteration paired cached/reference
comparison produced identical coordinates; full cache checks passed.

v6 adds optional --ordered-x for label-sensitive cap problems. Cold x coordinates
are strictly ordered, respecting fixed anchors; proposals are bounded by their
neighbors and accepted moves/restart perturbations must preserve strict order.
Unordered warm starts, contradictory fixed anchors, and rotation cycles are
rejected in this mode. This enforces an additional realizability constraint; it
does not relabel an existing warm start. CLI tests cover these cases and rapid
restarts combined with paired/line moves. The default 100,000-iteration seed-42
trajectory remained byte-identical to v5. The final v6 binary SHA256 is
5fab7d4c1fa7709c603f3f75771239b63a5533b2a36644fcc51fee44daf118a7.

The final v6 patch was rebuilt in a fresh checkout at 06:19 UTC. Its executable
SHA256 matched localizer_v6 exactly, and the upstream unit tests passed.

Both --pair-every and --ordered-x are off by default. Line search also remains
off by default: it was not a universal search improvement in held-out tests.
In a separate prospective 54-run test of default/line/pair-line configurations,
no actual geometry was solved. Mean orientation errors were 19.33/19.00/23.50
for 23 points, 116.33/119.67/131.50 for 32, and 37.83/40.50/45.17 for 26. These
small samples contained respectively two, one, and one unique SAT models. The
paired move is therefore an opt-in exploration feature, not a demonstrated
general search improvement.

## Direct 19-point geometry solver

geometry19.cpp is a separate C++17 exact-coordinate search for the actual
property: no convex hexagon with exactly zero or exactly three interior points.
It does not require realizing a fixed SAT orientation model. Compile using
g++ -O3 -std=c++17 -Wall -Wextra improvements/localizer/geometry19.cpp -o improvements/localizer/geometry19_v2

The oracle caches exact signed-128-bit orientations and left-of-edge bitsets.
It enumerates each convex hexagon once as an angularly ordered fan from its
leftmost vertex. Triangle-interior bitsets accumulate the polygon interior;
branches already containing more than three points can be discarded. Rejected
annealing candidates use a score cutoff. Incremental predicates can be fully
recomputed with --check-every K. An independent bigint exhaustive verifier
matched 200 random/adversarial configurations on 6..19 points.

Inputs can be indexed decimal .real files (rounded onto a grid, default scale
1e10) or n followed by integer coordinate pairs. Reported solutions are exact
for the written integer coordinates, not claims about the pre-rounding inputs.
Input components are bounded by 1e15; an initial lattice conversion can reach
2e15. Mutation components are bounded by 1e15, so every cross product is bounded
by 3.2e31, well below signed-128-bit capacity. Independent output audits use
arbitrary-precision integers.

--symmetry uses contiguous triples and a fixed nineteenth point. Indexed
Cartesian input is mapped into a lattice basis, while integer input is already
in that basis. The exact rotation is T(x,y)=(-y,x-y). Its positive-determinant
Euclidean embedding is (x-y/2,sqrt(3)*y/2). The independent verify_c3 --lattice
checker certifies the corresponding exact quadratic-field coordinates.

Search proposals include weighted point moves, paired moves, filling an empty
hexagon, and displacing an interior point of a forbidden three-interior hexagon.
Annealing and a small equal-best pool allow temporary worsening. Optional
--hole-weight/--three-weight change acceptance weights, but best output and
the reported score always minimize the unweighted number of forbidden hexagons.
--min-exponent/--max-exponent choose displacement scales relative to diameter;
--restart-every controls pool restarts. --cycle-iterations makes the temperature
schedule independent of wall-clock timing for reproducible fixed-work runs.

Best output is saved atomically immediately. Current and pool checkpoints are
saved every --checkpoint-seconds (default 60) and on shutdown. Direct SIGTERM
or SIGINT preserves output. Never infer that canceling a wrapping tool session
also stopped a native process: use its recorded host-visible PID.

First 900-second trials improved the actual 19-point deficit from six forbidden
hexagons to three with symmetry and two without symmetry. The unrestricted
two-defect set was reached after 245.926 seconds / 15,236,291 proposals. Exact
verification found two empty hexagons, no three-interior hexagons, and general
position. This is NOT a solution of the 19-point problem.

make_unattended.py freezes seed snapshots and generates single-core jobs for
../batch.py. audit_outputs.py independently audits saved best/pool/archive
candidates and, for lattice runs, exact C3 symmetry. The global supervisor must
enforce the user deadline (2026-09-05 14:00 UTC) and at most two native workers.

The frozen unattended14/jobs.json contains 128 actual-geometry jobs and no
fixed-order-type Localizer jobs. A separate exact biquadratic-final-polynomial
certificate proved model002-relaxed.or nonrealizable, even without symmetry;
it is explicitly excluded. Native target jobs require an explicit BFP-screened
whitelist. Passing that screening means only that this test found no obstruction,
not that a target is realizable.

The geometry queue alternates free and exact-C3 searches, with 900-second native
budgets, 60-second checkpoints, fixed seeds, and independently audited seed
snapshots. The portfolio varies empty/three-interior weights, displacement scales,
and restart schedules. First-job free and C3 smoke tests passed with cached
orientations fully recomputed every proposal; both independent output audits
passed and C3 output received exact quadratic-field certificates. No 19-point
solution existed at queue freeze. manifest.json records binaries, seed hashes,
configuration hash, and the global deadline. The frozen geometry19_v2 binary is
9620b9f1bc4f7d4f158b3cf5569cdc355149245202d046a43d0f24f33de6d62c.

Follow-up 540-second weighted/finer-scale runs evaluated 36,180,793 proposals
without symmetry and 35,059,029 with symmetry. They retained the previous best
deficits of two and three, respectively; this is not evidence of a search win
for those parameter changes. Both geometry versions independently matched the
bigint exhaustive oracle on the same 200-case random/adversarial test corpus.
