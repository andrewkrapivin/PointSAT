# Symmetry-free lazy SAT and native repair experiments

This branch uses969 individual orientation variables for19 points, in colex
order. Neither combinatorial nor geometric C3 symmetry is imposed. The input
CNF's compressed327-variable C3 encoding is not edited or misinterpreted.

`search.py` starts with937,992 necessary rank3 Grassmann–Pluecker/acyclicity
clauses. The C++ bitset checker`audit.cpp` enumerates all27,132 six-subsets.
For a forbidden convex hexagon, it records signs forcing the hull, every
inside point, and one separating edge for each outside point. Negating that
conjunction gives a sound target-specific clause. Repeat SAT and these cuts
until an abstract candidate passes the complete hexagon audit.

An optional incremental totalizer searches increasing Hamming balls around
an actual geometric seed. Optional BFP filtering adds only independently
verified impossibility clauses. A SAT result remains an abstract candidate,
never a geometric certificate.

## Build and run

```sh
make -C improvements/lazy19
direct/vendor/venv/bin/python improvements/lazy19/search.py --phase-real improvements/symmetry19/search/model002-relaxed-symmetric/points.real --output /tmp/pointsat-lazy19 --seconds 600 --samples 32 --distance-limit 20
```

Add`--bfp-seconds 30` for the exact-proof filter. System Python must provide
SciPy/HiGHS and SymPy. `--proof FILE` loads an earlier certificate only after
the independent checker succeeds. `--phase-points FILE.pts` accepts an exact
integer geometric seed and snapshots it as indexed`phase.real`.

Initial unfiltered experiments produced32 nearby abstract candidates in1.32s
after bootstrapping the known SAT model. Distance-bounded generation took3.91s.
Those are warm candidate-generation times, NOT a fresh solve of the original
CNF or a realization speed claim. All32 were tried with native Localizer for
20s each and analytic-gradient repair for30s each; neither portfolio found a
valid19-point geometry. The best actual count stayed six forbidden hexagons.
Subsequent BFP filtering proved the16 nearest candidates nonrealizable in a
613-second pilot, before any coordinate search was attempted on them.

The better actual19-point geometric seeds come from the separate
`../localizer/geometry19.cpp` search, whose best launch seed has two empty
hexagons and no three-interior hexagons.

## Additional native repair method

`gradient.cpp` is an experimental C++ realization solver with analytic
squared-hinge gradients, limited-memory BFGS, a fixed affine anchor triangle
and randomized restarts. Its1,800 finite-difference checks pass; a deliberately
violated four-point orientation system is repaired and checked exactly in
two iterations. It did not improve the19-point corpus and is not promoted
over Localizer in the overnight portfolio.

The native abstract checker passed independent exact tests on40 random point
sets,2,126 obstruction clauses and3,450,300 real-geometry/base-clause checks.
The search/gradient code is separate from the arbitrary-integer polygon
verifier used to certify outputs.

## Unattended producer and consumer

`overnight/jobs.json` freezes a one-core proof-filtered producer and a one-core
native consumer until14:00UTC. The producer starts with18 independently
verified cuts from prior runs. Completed surviving models have both`.or` and
`.json` files. The consumer checks these agree, tries cold/warm native runs,
and uses direct geometric search when no model is ready. It keeps and audits
the best geometric checkpoint. UNKNOWN or missing BFP proofs are not treated
as realizability certificates.

`overnight/freeze.json` records producer/helper/native checker hashes.
`overnight/corpus/events.jsonl`, `overnight/consumer/checkpoint.json` and each
supervisor's records provide persistent progress and restart information.
