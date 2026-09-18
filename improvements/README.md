# PointSAT and Localizer improvements

**Final status: all experiment queues stopped by 10 AM EDT on 5 September 2026.**
The 19-point problem is solved with exact C3 symmetry, and the combined
SAT-guided searches produced at least 15 distinct 23-point order types.
[Final results, speed measurements and limitations](FINAL_RESULTS.md).
[Exact 19-point coordinates and certificates](success19/README.md).
The host process check at 14:00:20 UTC found no experiment workers remaining.
The following sections retain the experiment history and reproduction details.

Work resumed2026-09-05 at05:26:41UTC for another full active hour. The user
then authorized unattended computation until10:00AM EDT, **14:00UTC today**.
These are exploratory research experiments, not a proof that one search
method is universally best.

**Update at07:15UTC: the19-point problem is solved, with exact threefold
rotational symmetry.** The28 convex hexagons have interior counts1 (15times),
2 (12times), or4 (once). Exact checks certify general position, all27,132
six-subsets, and all2,311,196 clauses of the original CNF.
[Original complete certificate](pipeline/unattended_20260905/runs/job013-symmetry19-target_margin/audit/sample4-job14/certificate.json).
The successful batch finished at06:58:38UTC; the result was noticed at the
07:14 unattended check. [Compact exact coordinates, independent certificates
and diagram](success19/README.md) are now independently verified.

## Results and certificates

- [Final consolidated report](FINAL_RESULTS.md).
- [Completed 120-job SAT-feedback portfolio and ten further 23-point solutions](pipeline/unattended_20260905/RESULTS.md).
- [Completed prospective 831-run native comparison](benchmarks/overnight/RESULTS.md).
- [Independent measurements and five23-point solutions](benchmarks/RESULTS.md).
- [Pipeline changes and matched timings](pipeline/RESULTS_20260905.md).
- [Native Localizer changes, build and options](localizer/README.md).
- [Earlier direct-geometric23-point experiments](../direct/RESULTS23.md).
- [Six-panel coordinate diagram](solutions23.svg), with the paper's reference
  and five experimentally found, distinct order types.
- [Additional research targets](RESEARCH_TARGETS.md).

The fixed-work native evaluation step is1.88–2.12times faster on all four
paper problems, with byte-identical trajectories. The isolated orchestration
comparison reduced wall time13.2%. Neither figure is an end-to-end
success-rate guarantee. Optional line/pair moves did not consistently help
in prospective comparisons and remain off by default.

Five independently verified23-point configurations have convex6 counts
772,591,642,606,573, versus753 for the paper's fixture. Their differing counts
prove pairwise nonisomorphism, but no literature-wide novelty claim is made.
All satisfy no convex7/no empty6 and general position. Exact coordinates,
full original-CNF extensions and independent certificates are preserved.

## 19-point problem

No valid19-point realization had been found at the unattended launch.
The best direct geometric seed has exactly two empty hexagons and zero
hexagons with three interior points, checked with arbitrary-size integers.
The C3 seed has three empty hexagons and zero three-interior hexagons.

The particular SAT assignment extracted from the supplied CNF is rigorously
nonrealizable even without geometric symmetry. The942-constraint relaxed
model002 target is also nonrealizable. These statements have independently
verified, exact positive-integer product-inequality certificates; they do
**not** rule out the19-point problem. Sixteen nearby symmetry-free abstract
candidates were also proved nonrealizable in the initial filtered pilot.

- [Full-target proof](realizability/results/supplied19-rational.json) and
  [independent check](benchmarks/supplied19_bfp_independent.json).
- [Relaxed-target proof](realizability/results/relaxed002.json) and
  [independent check](benchmarks/relaxed002_bfp_independent.json).
- [Proof-filter implementation and explanation](realizability/README.md).
- [Symmetry-free lazy SAT and C++ solvers](lazy19/README.md).

## Unattended experiment allocation

| tmux session | Cores | Purpose | Supervisor output |
| --- | ---: | --- | --- |
| pointsat-bench-until10edt |2| Prospective matched tests on all four families | `benchmarks/overnight/supervisor/` |
| pointsat-pipeline-until10edt |2| Fresh SAT, core feedback, archives, exact acceptance | `pipeline/unattended_20260905/supervisor/` |
| pointsat-geometry-until10edt |2| Actual19-point free/C3 geometric objectives | `localizer/unattended14/supervisor/` |
| pointsat-proofsearch-until10edt |2| Proof-filtered symmetry-free SAT producer and native consumer | `lazy19/overnight/supervisor/` |

Each queue records its host PID, manifest hash, deadline, job starts and
completions. Native limits are backed by a watchdog. A job-specific inherited
token tracks native descendants even across new sessions or parent exits.
SIGTERM requests a checkpoint; a bounded fallback kills only tagged job
processes. Independent audits decide whether outputs are genuine solutions.

To stop a queue gracefully, create a file named`STOP` inside its supervisor
output directory, or send SIGTERM to the exact supervisor PID recorded there.
Do not broadly kill all Python/Codex processes. Queues stop themselves by
14:00UTC, leaving time to save incumbents. Inspect existing records before
resuming so experiments are not duplicated.

The19 CNF is preserved unchanged. The pipeline uses a separate augmented
copy with independently verified, signed-map-projected impossibility cuts.
The new uncompressed solver imposes neither combinatorial nor geometric C3.

## Validation commands

```sh
direct/vendor/venv/bin/python improvements/test_helpers.py
direct/vendor/venv/bin/python improvements/test_batch.py
make -C improvements/lazy19
direct/vendor/venv/bin/python improvements/lazy19/test_gradient.py
direct/vendor/venv/bin/python improvements/benchmarks/test_lazy19.py
python3 improvements/benchmarks/verify_bfp.py --proof improvements/realizability/results/supplied19-rational.json --output /tmp/pointsat-proof-check.json
```

Some test scripts require the provided PySAT virtualenv; the BFP producer
uses system Python's SciPy/HiGHS and SymPy. Search kernels are native C/C++;
Python orchestrates solvers, reads exact decimals and verifies certificates.
