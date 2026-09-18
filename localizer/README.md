# Localizer: standalone PointSAT native solver

This is the optimized native v6 Localizer used in the PointSAT experiments,
packaged so it builds without the research workspace or an external checkout.
It searches for coordinates satisfying signed point-orientation constraints.
It does not use SAT internally, and unsuccessful search is not a proof of
nonrealizability.

Based on Bernardo Subercaseaux's Localizer, upstream revision
`5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb`. **The pinned upstream source did not
include a license grant.** Attribution and exact baseline sources are preserved;
see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) before redistributing.

## Build and test

Requires a C11-capable compiler, POSIX threads, and libm. Python 3, with no
third-party packages, is needed only for tests and benchmark orchestration.

```sh
make -C localizer
localizer/build/localizer --help
localizer/build/localizer localizer/benchmarks/inputs/mixed23.or -T 15 -s 42 -o points.real
make -C localizer test
```

From inside this directory, `make`, `build/localizer`, and `make test` work
equivalently. `CC`, `CFLAGS`, `LDFLAGS`, and `PYTHON` can be overridden through
Make. Avoid `-ffast-math`: finite-value checks and floating-point predicate
behavior must not be optimized away. Build artifacts live only under `build/`.

`make baseline` builds `build/localizer_v6` from the preserved v6 sources.
`make upstream` builds `build/localizer_upstream` from byte-identical original
sources, including their historical limitations. The upstream executable lacks
native iteration/wall limits and improved argument checking; use an externally
bounded harness and explicit empty `-f`/`-c` arguments when reproducing it.
It is not the default implementation.

## Input and output

An orientation file contains one constraint per line:

```text
A_(1, 2, 3)
B_(1, 2, 4)
```

Indices are 1-based, distinct within each triple, and at most 81. The number of
points is the largest referenced index. A means positive determinant of the
ordered triple; B means negative. The native threshold is `1e-6`: A requires
`det > 1e-6`, B requires `det < -1e-6`. C requires `abs(det) <= 1e-6` and is
therefore an approximate collinearity constraint, not a general-position
certificate. Nonfinite determinants always violate their constraint. Blank
lines and full-line `#` comments are accepted in orientation files.

Outputs and warm starts use exactly N indexed rows `index x y`. Output uses
17 significant digits, preserving round trips of the computed doubles. Fixed
points use `index:x,y`. Symmetry files contain one rotation orbit per line,
for example `1 2 3`; those points are successive rotations by 120 degrees about
the origin. Cycles must be disjoint. A fixed orbit member fixes its full orbit.

The final output says `SOLVED` or `STOPPED`, followed by `Violations: N` and a
JSON statistics row per worker. Successful execution/budget exhaustion returns
0 in either case: **exit 0 alone does not mean the constraints were solved**.
Each JSON row reports iterations, proposals, accepted moves, evaluations,
restarts, final/current violations, and the global best violation count.

For mathematical claims, validate the printed coordinates with exact arithmetic
and check the actual geometric problem. Floating-point rotational construction
does not by itself certify exact algebraic symmetry. The PointSAT pipeline
performs additional checks, including direction-dependent cap constraints.

## Options

|Option|Meaning / default|
|---|---|
|`-h`, `--help`|Show usage and exit without running search|
|`-o FILE`|Coordinate output; default `output.txt`|
|`-s SEED`|Nonnegative 31-bit seed; default 42|
|`-t THREADS`|Worker threads; default 1, maximum 256|
|`-i COUNT`|Subproposals per outer iteration; default 10|
|`-r COUNT`|Stagnation reset interval; default 30000, minimum 2|
|`-T SECONDS`, `--seconds`|Positive wall budget per worker; unset means unbounded|
|`-I COUNT`, `--max-iterations`|Positive outer-iteration limit; unset means unbounded|
|`-w FILE`, `--warm-start`|Initial indexed coordinates; requires all N points|
|`-f FILE`|Fixed coordinates; fixed points override warm coordinates|
|`-c FILE`|Rotation orbit constraints|
|`-d DISTANCE`|Optional minimum L1-distance penalty; nonpositive disables it|
|`-q`|Suppress periodic progress messages; final status/stats still appear|
|`--reference-evaluation`|Recompute old incident violations and disable rejection cutoff; isolates cache speed within revised search|
|`--check-every COUNT`|Recompute and assert complete cache consistency periodically|
|`--line-every COUNT`|Optional threshold-interval line search every Nth proposal; off by default|
|`--pair-every COUNT`|Optional paired point/orbit proposals; off by default|
|`--min-radius R`|Minimum proposal radius; default 0.1|
|`--max-radius R`|Largest proposal radius; default 15|
|`--archive-prefix PATH`|Save up to ten candidates as `PATH-00.real`, etc.; off by default|
|`--ordered-x`|Preserve strict label x-order; rejects unordered warm starts and rotation cycles|

Use an explicit budget for unattended work. SIGINT and SIGTERM request graceful
stop: workers join and the best coordinates are saved. Multithreaded searches
are scheduling-dependent; fixed-work reproducibility tests use `-t 1 -I ...`.
Archive entries may be duplicates and each requires independent validation.

## What is optimized

The established v6 implementation caches each constraint's violation flag and
per-point violation totals. Proposals touch only constraints incident to the
moved point or orbit; unsuccessful trials stop as soon as acceptance is
impossible. Symmetry moves use deduplicated incident unions, and corrected
top-K archive management supports safe restarts. Warm starts, optional line and
paired proposals, ordered-x search, input validation, signal-safe stopping, and
round-trip serialization are included.

Optional line/pair neighborhoods change the search and are not claimed to be
universally better. `--reference-evaluation` compares evaluation kernels within
the same revised algorithm; it is not a comparison with the original upstream
algorithm. The newly tested sampling/atomic-stop alternatives are separate
compile-time experiments and remain disabled unless supported by measurements.

## Reproducible fixed-work benchmark

```sh
make -C localizer baseline variants
python3 localizer/benchmarks/ablation.py --output /tmp/localizer-ablation-new --iterations 300000 --repeats 5
```

The harness uses four included PointSAT orientation fixtures, one per paper
problem, identical seeds/work limits, and randomized within-block execution
order. It runs one native process at a time and refuses an existing output
directory. Coordinates and every search counter must match v6 before any
speed comparison is accepted. Raw CPU and wall timings, hashes, and summaries
are written to the requested directory. Different solve rates or different
amounts of search work must not be presented as fixed-work speedups.

[PROVENANCE.json](PROVENANCE.json) records original/v6 source hashes and fixture
origins. Those research paths are provenance only: this folder has no runtime
dependency on them. See `benchmarks/RESULTS.md` for the local measurements.
