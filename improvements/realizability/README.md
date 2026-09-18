# Exact nonrealizability filter

`bfp.py` searches for a biquadratic final-polynomial certificate. This is a
classical necessary-condition method, not a complete realizability decision
procedure. The implementation was motivated by the persistent Localizer stall
on the supplied19-point SAT model. [Richter-Gebert's description of the method](https://science-to-touch.com/Articles/jrg/18_TwoInterstingOMs.pdf).

For five distinct labels, determinant brackets satisfy

```text
[abc][ade] - [abd][ace] + [abe][acd] = 0.
```

The orientation signs determine which signed product has the unique sign.
Its absolute magnitude equals the sum of the other two, so it is strictly
larger than either. Taking logarithms turns those two product inequalities
into strict linear inequalities in the log absolute determinant magnitudes.

HiGHS searches for nonnegative weights summing to one whose weighted
coefficient rows cancel. Floating-point feasibility alone is NOT a proof.
Weights are reconstructed as exact rationals, including an exact supported
nullspace calculation when necessary, then cleared to positive integers.
Every weighted coefficient must cancel exactly. The resulting positive sum
of strict inequalities is the contradiction`0 > 0`.

The independent checker in`../benchmarks/verify_bfp.py` shares no producer,
LP, symbolic-algebra or orientation-helper code. It reconstructs determinant
brackets by their triples, checks all sign implications and positive integer
weights, and verifies the matching orientation blocking clause.

## Run

The machine has SciPy1.11.4 and SymPy available in system Python. They are
not installed in the separate PySAT virtualenv.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 improvements/realizability/bfp.py improvements/symmetry19/decoded/center19-adjacent.or --seconds 60 --output /tmp/pointsat-bfp.json
python3 improvements/benchmarks/verify_bfp.py --proof /tmp/pointsat-bfp.json --output /tmp/pointsat-bfp-checked.json
```

Use`--partial` for a reduced Localizer orientation file. Only relations whose
six signs are explicitly present are used. A verified proof then rules out
the partial target itself, independently of every omitted orientation.
`--vertices` restricts the attempted certificate to selected original labels.
Experimental`--relax-mutations` drops GP-mutable signs before the LP to seek
a stronger blocking clause; it is off in the frozen overnight producer.

## Interpretation and safeguards

- `PROVED_NONREALIZABLE`: exact certificate verified by the producer;
  independently verify before adding its blocking clause to SAT.
- `NO_BFP_FOUND`: the restricted dual system was infeasible. This does NOT
  prove that coordinates exist.
- `UNKNOWN`: time limit or other unfinished work.
- `NUMERIC_CANDIDATE_UNCERTIFIED`: numerical weights could not be certified;
  do not prune or claim impossibility.

The LP time limit does not bound the later exact reconstruction. The lazy
driver and unattended supervisor therefore impose an additional process
watchdog. Interrupted/uncertified results never become exclusion clauses.

The full supplied-model proof has882 weighted inequalities and967 orientation
premises. The relaxed model002 proof has846 inequalities and939 premises
drawn from942 retained orientations. Both were independently checked.
They rule out these targets, not the whole19-point problem. Original CNFs
remain untouched; the pipeline creates a separately hashed augmented copy.

A certificate for a full model cannot automatically prune a reduced Localizer
target: every supporting orientation must still be enforced. The pipeline
checks this condition explicitly. The symmetry-free lazy solver instead adds
the exact colex blocking clause, so no real point configuration is excluded.
