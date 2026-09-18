# Independently certified 29-point witnesses from the matched benchmarks

All listed point sets are in general position and contain no empty convex hexagon.
Every one of the 475,020 six-point subsets was checked exactly. Their decimal
outputs, native targets/logs, original-CNF extension, and sign-preserving integer
normalization are preserved in their respective folders.

| Trial | Policy and provenance | Whole-trial wall | Integer box | Convex6 count |
| --- | --- | ---: | ---: | ---: |
| [11](trial11/certificate.json) | Native seed 811, success in shared initial 15-second stage |18.70s |1,000,000×723,094 |4628 |
| [19](trial19/certificate.json) | Native seed 271, success after three SAT-feedback repairs |53.30s |1,000,000×808,458 |4513 |
| [62](trial62/certificate.json) | Native seed 811, matching feedback arm; shared initial stage |17.92s |300,000×222,962 |4670 |

They use the same pre-existing SAT target, `holes29-s42200`, without a known
coordinate seed. SAT generation is excluded from this realization benchmark.
Different convex6 counts prove these three resulting order types are different;
this is not a literature-wide novelty claim. All have hull layers 3,4,7,7,7,1.
The two seed-811 runs follow the same initial policy; their time-capped native
trajectories stop at different checkpoints, explaining their differing geometry.

Trial 11 succeeded before retries or feedback could affect the run; it is not
evidence in favor of its assigned warm-retry policy. Trial 19 followed repairs
changing 7, 6, and 2 orientations, but its causal comparison is the matching
warm-retry trial at seed 271, not trial 11's different seed. That matching
warm-retry trial (55) did not save a valid set within its 60-second budget.
The seed-811 pair succeeded in both arms before either strategy acted.

The normalization preserves all 3654 orientation signs. Fresh independent SAT
checks extend the exact geometries, after label-only radial canonicalization,
to full models satisfying all 825,978 clauses of the original 29-point CNF.
The point geometry is also checked independently from that SAT encoding.

## Prospective extension

Extension trial 8 used the disjoint SAT target `holes29-s42206`, native seed 271,
and the feedback arm. One repair changed six orientations; the next 15-second
native stage saved a valid set. Whole-trial wall time was 33.71 seconds. This
was not a shared-initial-stage success. Its matching retry outcome is reported
in the benchmark summary, not inferred from the successful run alone.

[extension-trial8/normalized.pts](extension-trial8/normalized.pts) has box
357,248 × 1,000,000, 4,770 convex six-point subsets, and the same hull layers
3,4,7,7,7,1. Its different convex-six count proves a different order type from
all three pilot outputs above. The [fresh certificate](extension-trial8/certificate.json)
checks all 475,020 six-point subsets and all 825,978 original CNF clauses.

Extension trial 17 is the second native seed (811) on that same SAT target.
It also succeeded after one six-orientation repair, in 33.87 seconds total.
[extension-trial17/normalized.pts](extension-trial17/normalized.pts) has box
59,483 × 100,000, minimum determinant 17, and 4,675 convex six-point subsets.
Its [fresh certificate](extension-trial17/certificate.json) likewise passes
the independent geometry and full original-CNF checks. The two extension
successes still represent only one source-target cluster.

Extension trial 32 used another disjoint target, `holes29-s42207`, seed 811,
and feedback, succeeding in 35.30 seconds total. Its certified integer set
[extension-trial32/normalized.pts](extension-trial32/normalized.pts) has box
100,000 × 90,198, minimum determinant 214, and 4,684 convex six-point subsets.
The [certificate](extension-trial32/certificate.json) again independently
checks the full geometric property and original CNF.

The last success, extension trial 61, is seed 271 on `holes29-s42207`, also
with feedback, in 36.82 seconds. Its
[integer witness](extension-trial61/normalized.pts) has box
3,000,000 × 2,029,655, minimum determinant 11,607, and 4,454 convex six-point
subsets; the [certificate](extension-trial61/certificate.json) passes both
independent exact checks. All seven listed witnesses
have different convex-six counts; this distinguishes their resulting order
types, not their novelty relative to published constructions.

The completed prospective extension found four feedback successes and no
warm-retry successes, across two source target models. Pooled with the pilot,
29-point outcomes are feedback 6/16 versus warm retries 1/16, or three versus
one solved source models out of eight. Five matched seed pairs favor only
feedback, one succeeds in both arms, and ten succeed in neither. The other
three problem families had no success in either arm at this budget.

## Reproduction

Reproduce a certificate from the compact SQLite benchmark evidence:

```sh
direct/vendor/venv/bin/python benchmarks/certify_trial.py \
  --database benchmarks/pilot_20260906/results.sqlite --trial 11 \
  --output benchmarks/a-new-certificate-folder
```

Use [trial11/normalized.pts](trial11/normalized.pts) or
[trial19/normalized.pts](trial19/normalized.pts), or
[trial62/normalized.pts](trial62/normalized.pts) as plain `n`+integer-pair inputs
to geometric tools. These grids are simple sign-preserving normalizations, not
claimed optimal coordinate bounds.
