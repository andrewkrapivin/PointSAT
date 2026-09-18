# Equal-total-time reporting

This is the corrected total-wall-time study, not a conversion of the earlier
native-budget diagnostics. Each arm has one trajectory per registered target;
milestones are readings on that trajectory, not fresh budget restarts.

```sh
direct/vendor/venv/bin/python benchmarks/anytime_report.py \
  --registration PATH/TO/ANYTIME-STUDY/registration.json \
  --machine-info benchmarks/scaling_machine_20260907.json \
  --positive-control-result benchmarks/compare19_positive_control_20260907/result.json \
  --out NEW_REPORT_DIRECTORY
```

Add `--draft` for partial data. The output directory must be new. Registration,
SQLite data and all earlier reports are read-only. More than one nonoverlapping
family registration may be supplied with repeated `--registration` flags.

Outputs are README.md, report.json, a self-contained anytime-report.pdf and its
LaTeX source, plus vector PDF/PNG step curves. Reporting runs no SAT solver,
native search or geometry audit. The bounded PDF build uses the existing
pdflatex installation, with shell escape disabled. A frozen deployment needs
both anytime_report.py and its sibling anytime_pdf.py; no old report imports
are required.

This is a cold realization-workflow comparison, not the literal unmodified
PointSAT driver and not steady-state batch throughput. The original arm uses
the original flippability implementation and untouched native solver. Updated
arms use the revised checker, persistent only within that trajectory; there
is no cross-target or cross-arm solver cache. Conversion, the required327-variable
adapter, geometry acceptance and storage are common. Original-to-updated
continuous therefore includes both preparation and native-package changes.
Updated plain/line/pair comparisons isolate optional native flags; retry-only
versus feedback adds retargeting plus its SAT overhead on the same schedule.

The success clock includes runtime preparation/import, native work, feedback
and completed online verification. Each credited event is checked against its
stored compressed certificate hash, geometric-validity/GP claims, and logged
acceptance timestamp relative to the parent launch clock. A posthoc audit can
never create or backdate a primary success. Numeric geometry is primary; exact
C3/CNF checks are secondary for the19-point family.

Every registered target remains in empirical success-curve denominators.
Failures retain censor timestamps; unstarted and early-interrupted observations
remain explicit rather than being silently treated as complete exposure.
The report includes matched arm gains/losses, and specifically retry-only
versus SAT-feedback controls. Duplicate completed case/arm records are an
integrity error. Incomplete attempts remain in all-attempt CPU/error accounting.

Costs include all recorded attempts, not only successes. Preparation, native,
feedback and online-verification components are separate from posthoc auditing.
Parent CPU totals overlap component CPU and are not added to them. Forced-kill
CPU lower bounds and missing measurement coverage stay explicit. Native wall
seconds are never substituted for CPU or reconstructed into total-time events.

The target corpus mixes fresh and historical SAT sources and is reused after
the native-budget diagnostic. It is not an unseen or IID test set. Corpus
construction costs and the earlier known positive control are reported outside
the primary experiment, never pooled into its target denominators.

Synthetic tests, with no searches or exact-audit reruns:

```sh
direct/vendor/venv/bin/python -m unittest benchmarks.test_anytime_report
```
