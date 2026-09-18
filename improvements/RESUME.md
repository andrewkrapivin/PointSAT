# PointSAT / Localizer improvement checkpoint

FINAL STATUS — 14:00:20 UTC, 5 September 2026: all four experiment queues
have finished and the host process check shows no remaining experiment workers.
Do not automatically restart. The requested additional active hour and
unattended computation through the 10 AM EDT cutoff are complete.

The 19-point problem is solved with exact Euclidean C3 symmetry; compact
coordinates, independent certificates and a diagram are in `success19/README.md`.
The SAT-guided searches found at least 15 distinct 23-point order types.
See `FINAL_RESULTS.md` for the final handoff and all four paper benchmarks.
The rest of this file is historical context; any references below to running
workers, pending cap fixes or incomplete hours are superseded by this status.

## Historical active-run checkpoint

BREAKTHROUGH07:15UTC:19-point problem SOLVED with exact C3 symmetry. Certificate:
`improvements/pipeline/unattended_20260905/runs/job013-symmetry19-target_margin/audit/sample4-job14/certificate.json`.
Histogram[0,15,12,0,1,0,...], GP, all27,132sixsets, originalCNFall2,311,196clauses
pass independently both rational coordinates and exactQsqrt3 reconstruction.
Batchended06:58:38UTC; rootnoticed07:14duringlowtokenmonitor. Validationagent
reawakened for independentcompactwitness at`improvements/success19/`.
All8experimentworkersstillrunninguntil14UTC; noothercodeeditsplanned.

CURRENT STATUS (2026-09-05): user resumed at05:26:41 UTC and requested an
additional active improvement hour, through at least06:26:41 UTC. They then
extended computation until **10:00AM Eastern Daylight Time =14:00UTC today**,
asking for low token use after the active hour. Prepare bounded unattended
queues with checkpoints and automatic exact audits. Do not launch duplicate
jobs when reconnecting: inspect `improvements/batch.py` supervisor records and
host-visible process IDs first. The old pause notes below are historical.

Resumption fixes: caps26 exact acceptance gate integrated and tested; all650
projection intervals of the misleading known26 order-type realization still
have at least27caps. Native-parent interruption now saves/checks incumbents.
Supervisor separately tracks tagged descendants across setsid/orphaning.

New work lives in `improvements/lazy19/` (uncompressed no-symmetry lazy SAT,
minimum-Hamming geometry feedback, C++ abstract checker and L-BFGS repair),
`improvements/localizer/geometry19.cpp` (actual geometric0/3-interior objective),
and `improvements/realizability/bfp.py` (exactly verified BFP proof filter).
At06:04 the full supplied model was independently proved nonrealizable;
at06:09 the942-constraint relaxed002 target was independently proved too.
Sixteen nearby symmetry-free targets were also certified impossible. Exact
proofs are in realizability/results/ and lazy19/results/bfp19691/bfp/.

Five distinct new23solutions are independently certified, with
convex6 counts772,591,642,606,573 (paper753), under benchmarks/successes/.
Best actual19geometry at unattended launch has two emptyhexagons and zero3-interiorhexagons,
still NOT a solution. Native files update atomically; snapshot before auditing.

All four2-worker supervisors launched in tmux by06:19:21UTC. Names, manifests,
stop instructions and reports are in improvements/README.md. Native/helper
code is frozen for the unattended comparison. Run `python3 improvements/monitor.py`
for a compact status; inspect exact certificates before announcing a solution.

## Historical pause notes

User requested pausing all runs to reconnect inside tmux on 2026-09-05,
about 05:23 UTC. Do not automatically restart computation until requested.

This improvement session started 04:46:53 UTC. About 37 minutes were spent
before the pause; the requested **at least one hour** is not yet complete.
Allow at least another 24 minutes of active work on resumption (prefer more
for final validation). The earlier direct-geometric hour was a separate task.

## Active user scope

- Improve both PointSAT's scripts and Bernardo Subercaseaux's Localizer.
- Test all four paper problems: 23/no7gon/no6hole; 26/no7gon/no5cap;
  29/no6hole; 32/no7gon.
- Identify other promising research targets.
- Attempt the supplied 19-point problem: every convex hexagon must contain
  neither zero nor three other points. Geometric threefold symmetry is optional;
  user explicitly accepts any realization and requested both treatments.

## Important safety/correctness TODO before resuming cap experiments

The 26-point cap CNF assumes coordinate order. An exact order-type realization
can contain geometric 5-caps. Independent validation caught this on a known
positive control. `sat_orient_conversion.count_caps(realfile,5)` is implemented
and tested, but **the pipeline cap acceptance gate was not integrated when the
user requested the pause**. Integrate it before accepting any caps26 result.
Do not mistake full CNF satisfaction alone for this geometric certificate.
Optional all-direction cap projection recovery was planned, not completed.

## Implemented work

- `PointSAT.py` is now a compatibility entry point for
  `improvements/pipeline/runner.py`: bounded process workers, persistent CNF/SAT,
  exact statuses, safe process groups, warm starts, deterministic retries,
  per-stage timing, optional UNSAT-core-guided geometric feedback.
- `flippable2.FlippabilityChecker` caches CNF/SAT and safely screens flips using
  projected clauses. API `.check(model)`, `.solver`, `.last_stats`, `.close()`.
  `helper_all_problems.json` contains identical-answer paired benchmarks on all
  four problems. One-time initialization is reported separately.
- `sat_orient_conversion.py`: exact printed-decimal interpretation using integer
  predicates, strict parsing (no eval), shared realization inspection, exact
  radial relabeling, and the new cap-counting helper.
- Native Localizer edits are in `direct/vendor/localizer/src/` (ignored vendor).
  Portable patches, build script, docs, immutable binaries and tests are in
  `improvements/localizer/`. Latest is v4; v1 and v3 are frozen benchmark versions.
  Features: cached incident-constraint evaluation, early rejection, correct orbit
  moves, archive fixes, warm starts, native time/iteration budgets, safe signals,
  round-trip output, optional line optimization including quadratic orbit motion,
  and optional archive export.
- Signed orientation-map adapter and archive checking are integrated into the
  pipeline, opt-in. See `improvements/pipeline/README.md`.

## Two new independently verified 23-point solutions

Neither started from known geometric coordinates.

1. `improvements/benchmarks/successes/sat-guided23-case33/`
   - Native v1 matched test, SAT sample33/seed1; two orientation mismatches but
     valid actual geometry. Radial relabeling of exactly the same coordinates
     restores full original CNF satisfaction; all 519426 clauses checked.
   - 772 convex six-subsets, distinct from the paper's753.
   - `radial_canonical.pts`, `radial_canonical.model`, `radial_certificate.json`.
2. `improvements/benchmarks/successes/feedback23-sample3/`
   - Core-guided feedback revises four orientation targets then warm Localizer
     reaches zero mismatches. Full original CNF SAT without relabeling.
   - 591 convex six-subsets, distinct from both paper and sample33.
   - `normalized.pts`, full model and independent certificates in this directory.
   - Original pipeline result:
     `improvements/pipeline/feedback_pilot/mixed23-core_feedback/realizations/3_14.real`.

Both were checked with independent arbitrary-precision and int128 exhaustive
geometry, plus full CNF assignments. Short coordinate-compaction refinements
were also verified; these preserve order type and are not additional discoveries.

## Measured results already available

- Isolated Python-pipeline comparison, same upstream Localizer and eight identical
  SAT assignments/flippable sets: 91.945→79.791 wall seconds;
  179.932→156.726 CPU seconds (about13% less). Both0/8 solutions.
  `improvements/pipeline/paired_pipeline/manifest.json`.
- Legacy60 matched Localizer tests: geometric0/60→1/60, mean orientation
  violations14.9667→14.2833. Exploratory small sample, not a universal success rate.
  `improvements/benchmarks/legacy23_comparison.json`.
- Fresh baseline/v1 comparison covers all FOUR problems: 48 paired runs, including
  one late29 SAT model and three realization seeds per model.
  `improvements/benchmarks/fresh_v1_comparison.json`.
- Revised reference-versus-cached kernel runs had identical trajectories; known
  controls showed roughly1.5–2.2× speedups, but some solved too early. A stronger
  fixed100k-iteration ablation on fresh SAT inputs was running; inspect checkpoint.
- Warm retry versus core feedback pilot completed for23/26/32. Mixed23 control
  found0/4, feedback1/4; consumed budgets differ because attempts may end early.
  Other completed results are in `feedback_pilot/manifest.json`.

## Supplied19 CNF and recovered mapping

User file: `convex_hexagon_inside_19_3sym.cnf` (53MB; preserve it).
Kissat default SAT in281.88wall/281.82CPU seconds. Full model:
`improvements/symmetry19/input_sat.out`.

Straight lex/colex triple decoding was wrong. The first327 variables are
symmetry-orbit representatives of969 triples, with cycles(1,2,3),...,(16,17,18)
and fixed point19. Burnside count: (969+2*6)/3=327.
Thirty-eight layout/center hypotheses were tested; only this one passed all3876
four-point hull checks and the target interior-count audit. Also checked58140
Grassmann–Plücker relations, with zero violations. This is not a realizability proof.

- `improvements/symmetry19/decoded/center19-adjacent.or`, `.cycles`, `.fixed`.
- `improvements/symmetry19/variants/mapping.json`: explicit signed CNF-to-triple map.
- `prepare_variants.py` generated eight SAT-neighbor models and safely omitted
  their flippable orbit variables. Complete metadata in `variants/modelNNN.json`.
- First SAT abstract model:34convex hexagons; interior histogram
  `[0,15,12,0,4,3,0,...]`, exactly the desired abstract property.
- `verify_hexagons.cpp` independently enumerates all27132 six-subsets with
  arbitrary-precision integer arithmetic. Twenty differential histogram tests
  against an independent supporting-edge Python oracle passed, including80-digit
  affine scaling.
- Sixteen30-second relaxed realization runs, with and without symmetry, completed
  in `improvements/symmetry19/search/`; none valid. Some have3target mismatches
  but still forbidden hexagons. Consult exact histograms, not orientation score.
- Two600-second full-model searches completed in
  `improvements/localizer/results/search19/`: free best6 mismatches, rotational15.
  Both independently invalid geometrically. Two finer warm runs were interrupted
  at user request; inspect native pause notes and saved final outputs.
- Root's second independent Kissat run seed19023 was explicitly terminated at
  pause; `second_sat.out/.time` are partial, not a completed600-second trial.
- Mapped19core-feedback pilot was interrupted before completing a realization:
  `improvements/pipeline/symmetry19_feedback/run/summary.json`.

## Restart commands (fresh output directories required)

From `/home/andrew/PointSAT`, after reviewing the pending cap gate:

```bash
direct/vendor/venv/bin/python -m unittest improvements.pipeline.test_pipeline -v
direct/vendor/venv/bin/python improvements/test_helpers.py
python3 improvements/symmetry19/test_verifier.py
direct/vendor/venv/bin/python PointSAT.py improvements/pipeline/symmetry19_feedback/settings.json --out improvements/pipeline/symmetry19_feedback/run-resumed
direct/vendor/venv/bin/python PointSAT.py improvements/pipeline/archive23.json --out improvements/pipeline/archive23-resumed
```

Do not launch every portfolio simultaneously: the machine has8vCPUs and8.7GiB RAM.
Use at most8native search workers total; large19SAT Python state uses about1GiB.
Existing result directories are immutable; interrupted jobs require new names.
Native warm19 restart details are in Localizer pause notes. Restarting a process
from its saved coordinates does not restore its RNG/archive/SAT learned state.

## Further research candidates identified (not solved)

- The 2026 paper *Garment numbers of bi-colored point sets in the plane* gives
  12-point examples avoiding empty monochromatic necklace/pant structures and
  upper bound21. Seeking a13-point example is a plausible small PointSAT target.
  Another target is15points avoiding necklaces (published example14).
  https://arxiv.org/abs/2603.05339
  Construction/code repository: https://github.com/N-Coder/garment-numbers-colored-point-sets
- Small balanced two-color configurations minimizing empty red-red-blue triangles
  could supply finite extremal data for the conjectured quadratic lower bound;
  a finite example does not settle the asymptotic conjecture.
  https://arxiv.org/abs/2409.17078
- Generalize the supplied19benchmark to forbidden interior-count sets, retaining
  exact histogram verification and explicit variable maps.

## Workspace/provenance

Root settings and original CNFs were not edited. Root Python source changes are
uncommitted; `direct/` comes from the previous task. `improvements/` is new and
untracked. Original source/helper/binary snapshots are under
`improvements/baseline/` and `improvements/benchmarks/baseline_snapshot/`.
No upstream pushes or external messages were made. No global dependencies were
installed: venv, Boost headers and upstream repositories are under ignored
`direct/vendor/`. Do not discard these uncommitted files.
