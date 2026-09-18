# Independent Localizer benchmark

`matched.py` schedules native-C runs and independently audits their saved decimal
coordinates. It does not perform the geometric search in Python.

The immutable upstream executable is `../localizer/localizer_baseline`, SHA256
`f5c0819778eba20ac1d8c1f231e922ac0f309372e8d79db9476aca801200b98c`, from upstream
commit `5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb`. The original pipeline and Python
helpers are in `baseline_snapshot/`; these were copied before source changes.

## Protocol registered before improved runs

- All 60 legacy SAT-produced n=23 orientation files are tuning/development data.
  Their immutable copies and hashes are in `legacy23_manifest.json`.
- Fresh four-problem models use the prospectively frozen split in
  `../pipeline/fresh_corpus/frozen_manifest.json`: first two SAT seeds per
  problem tune, last three are held out. None are known-coordinate seeds.
- Matched pairs use the identical orientation-file hash and Localizer seed.
  Each native process gets one thread, 10 subiterations, reset interval 30000,
  and a 15-second wall limit. SIGINT requests a final coordinate dump, with a
  3-second grace period; forced kills and missing outputs count as failures.
- Both old and new binaries receive explicit empty `-f` and `-c` options
  unless symmetry is requested. This works around upstream uninitialized
  filename buffers identically; it does not change the search trajectory.
- Every run records process user/system CPU time separately from wall time.
  Baseline and improved batches occur at different times under shared-machine
  load. Equal wall budgets are practical quality comparisons, not a pure
  kernel-throughput speedup claim. Native fixed-work microbenchmarks are separate.
- Each run batch snapshots its binary, so subsequent rebuilds cannot contaminate
  the executable hash. The first baseline batch predates this convenience and
  uses the immutable baseline executable directly.
- Search success and exact output success are distinct: decimal tokens are
  converted to exact integers using common denominators, without a float
  roundtrip; all requested orientation signs and all GP triples are checked.
  The independent C++ subset validator then exhaustively checks the geometric
  target. No Localizer success claim bypasses this audit.
- For the 26-point cap problem, caps are first checked on raw output. Separately,
  an exact rational interval calculation tests whether a positive-determinant
  affine map can put labels in increasing x order. Its transformed witness and
  cap count are reported separately, never substituted for raw validity.
- Paired means/medians, wins/ties/regressions, and exploratory paired-bootstrap
  intervals are reported. Clusters are unique orientation-file SHA256 values,
  not SAT seeds: distinct seeds sometimes return identical models. A tiny
  heldout set does not establish a general
  success-rate improvement or resolve realizability of failed order types.

## Independent certificates and unattended work

`independent_audit.py` accepts a saved indexed decimal `.real`, explicit family,
optional original CNF, optional compressed orientation map, and optional C3
cycles. It independently checks geometry, extends exact orientation literals
with a fresh CaDiCaL solver, and scans every original clause. Use
`direct/vendor/venv/bin/python`; the C++ verifiers are built separately.

`verify_c3` reconstructs six exact Euclidean 120-degree orbits around the
remaining center in Q(sqrt(3)); every arithmetic predicate is integer-exact.
With `--lattice`, input coordinates use the native affine C3 basis
`T(x,y)=(-y,x-y)`. The positive-determinant map
`L(x,y)=(2x-y,sqrt(3)*y)` turns T into Euclidean rotation, preserving all
orientation signs and polygon interiors. Output rows give coefficients
`x_a x_b y_a y_b` for `(x_a+x_b*sqrt(3), y_a+y_b*sqrt(3))`.
Reconstruction is not an assertion that rounded input is exactly symmetric:
the number of changed triple signs is explicitly reported.

`verify_bfp.py` independently checks impossibility certificates produced by
`../realizability/bfp.py`, without importing its LP or sign code. For a signed
Grassmann–Pluecker identity P-Q+R=0, the uniquely signed product has magnitude
equal to the sum of the other two. Its log magnitude therefore strictly exceeds
either smaller product. A positive integer combination whose bracket exponents
cancel says `0 > 0`, proving this orientation assignment nonrealizable. This
does not prove the geometric problem has no solution. The original supplied19
model has such a verified certificate with 882 inequalities; see
`supplied19_bfp_independent.json`.

`overnight/registration.json` freezes 80 new interleaved four-problem SAT draws,
native binaries, treatment flags, seeds, and budgets before generation. The
corresponding `overnight/jobs.json` is consumed by the root `improvements/batch.py`
supervisor with one or two workers and an explicit UTC deadline. Each job is
single-core. SAT failures remain in accounting, treatment order is randomized,
and no published coordinate seed is supplied. The harness checkpoints on
SIGTERM and excludes interrupted native runs from matched comparisons.

Independent regression suites include `test_audit.py`, `test_cap_projection.py`,
`test_c3.py`, `test_lazy19.py`, `test_geometry19.py`, `test_matched_stop.py`, and
`test_overnight.py`. Some require the PySAT virtual environment. Long-running
experiment artifacts are not unit tests.

`consume_lazy19.py` is a separate exploratory worker for completed root lazy19
models: only JSON-completed, BFP-screened full target files are consumed, with
hash deduplication and independent exact19 geometry checks. `UNKNOWN` and
`NO_BFP_FOUND` do not imply realizability. Each target receives45s cold nativev1
and45s warm nativev6 with line10; this is deliberately not a fair paired
algorithm benchmark. When the queue is empty,60s direct actual-geometry
searches use the independently checked v2 oracle and retain the best incumbent.
The worker is single-core, checkpoints on SIGTERM, and has an explicit UTC
deadline. Its root-supervisor entry is `lazy19_consumer_job.json`.

Example:

```sh
python3 improvements/benchmarks/matched.py run \
  --manifest improvements/benchmarks/legacy23_manifest.json \
  --binary improvements/localizer/localizer_baseline --label baseline \
  --output improvements/benchmarks/results/legacy23_baseline \
  --seconds 15 --seeds 1 --jobs 2
python3 improvements/benchmarks/test_audit.py
```
