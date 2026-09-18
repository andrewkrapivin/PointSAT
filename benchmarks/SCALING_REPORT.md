# Combined checkpoint-scaling report

The report generator reads existing19-point and four-paper-family benchmark
registrations, neighboring `summary.json` files, and read-only `results.sqlite`
attempt records. It never launches SAT, Localizer, or geometry audits.

```sh
direct/vendor/venv/bin/python benchmarks/scaling_report.py \
  --nineteen-registration PATH/TO/19-STUDY/registration.json \
  --paper-registration PATH/TO/PAPER-STUDY/registration.json \
  --machine-info benchmarks/scaling_machine_20260907.json \
  --positive-control-result benchmarks/compare19_positive_control_20260907/result.json \
  --out NEW_REPORT_DIRECTORY
```

Use `--draft` for incomplete snapshots. First refresh summaries using the
benchmark harnesses' read-only aggregation commands; this generator does not
rewrite source summaries. The output directory must be new, preserving earlier
reports and making each snapshot reproducible.

Outputs include a self-contained `scaling-report.pdf` (and LaTeX source),
`README.md`, `report.json`, and checkpoint/compute figures in both
vector PDF and PNG. Source registrations, summaries, available corpus manifests,
and output figures are hashed. The JSON retains per-arm metrics, paired target
outcomes, cost-field coverage, and all persisted error/interrupt diagnostics.
The optional machine snapshot is linked and hashed, not executed. The optional
known-positive-control result is reported separately, never added to study
denominators. PDF generation uses the already-installed `pdflatex`, with shell
escape disabled and a45-second compilation cap; it installs no dependencies.

Within-target10→30,30→60, and10→60-second changes are computed by
[`scaling_effects.py`](scaling_effects.py), with same-input/seed checks and
hash/content-checked stored certificates. Both validity gains and losses are
reported. Residual changes are medians of paired differences, not differences
of unrelated group medians. Missing/invalid certificate pairs are explicitly
excluded from residual comparisons, never converted into measured zeroes.

For the19-point mixed fresh/historical corpus, the report prefers the frozen
corpus manifest copied into the benchmark registration. It discloses selection
strata and exclusion of the known control type. Fresh-generation CPU and
combined-corpus original-CNF revalidation CPU are separate, avoiding double
counting or attributing historical generation costs to the current batch.

The primary endpoint is exact geometric validity of the final checkpoint.
Actual forbidden-polygon residual medians use only general-position outputs,
with those denominators reported. Any saved valid checkpoint is secondary.
For19 points, exact C3 reconstruction is not substituted for the numeric
geometry endpoint.

Only20 targets and one seed per target are planned per problem. Budget curves
describe fresh10/30/60-second starts, not time-to-first-success distributions.
No unobserved first-success time is interpolated. Missing observations remain
unknown; incomplete targets are not converted into failures. CPU, summed worker
wall time, native allowance, and estimated calendar duration remain distinct.

Synthetic report tests, with no search or audit work:

```sh
direct/vendor/venv/bin/python -m unittest benchmarks.test_scaling_report
```
