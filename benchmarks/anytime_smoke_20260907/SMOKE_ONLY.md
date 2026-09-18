# Workflow smoke test — not benchmark evidence

This separate test uses the officially frozen worker/coordinator code with
two 19-point SAT assignments and a 60-second horizon. One assignment is the
known positive control, the other the first fresh corpus target. No coordinates
were supplied. Neither the positive-control runs nor these fresh-target runs
are included in the main 100-target / 560-trajectory study.

The original, v4 continuous, and v4 feedback workflows all returned exact
verified geometry on the positive control (18.34, 20.15 and 19.47 total wall
seconds). All three exhausted their allowance on the fresh target. Its feedback
arm performed a successful SAT repair, recomputed flippability and resumed
native search from the previous coordinates. The control does not establish a
speedup; preparation dominated its short native search.

All six records and 145 preserved artifacts passed the frozen integrity check,
including equal initial partial-target hashes across arms and all three online
certificates. There were no online checker errors. Two timed-out attempts carry
the conservative CPU lower-bound flag; this is not an unflagged exact-cost claim.
The automatic PDF build also completed successfully.

The generic generated smoke report contains parent-corpus provenance text.
That text describes the parent 20-target corpus, **not this selected two-target
smoke**, which deliberately includes the positive control. Do not use the smoke
report as the main experimental comparison or pool its success fractions.

The main registration remains unchanged at SHA256
`bc9b176c5c291e62660c29a78155b06943a0a5f9d92cd754158a429cc9812f58`.
