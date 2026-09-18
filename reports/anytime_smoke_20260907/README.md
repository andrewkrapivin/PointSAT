# Equal-total-time PointSAT study

Primary endpoint: first accepted solution returned by completed online verification within the total wall-time limit. The clock includes runtime preparation/import, native search, feedback, and online verification. SAT target sampling is outside it. Posthoc audits do not create or backdate primary success events.

Every registered target remains in each empirical success-curve denominator. Failures have no success event and retain censoring times. These are deliberately diverse, non-IID SAT targets with one seed each; no population success rate or universal speed multiplier is claimed. Retry-only arms help distinguish repeated geometric attempts from the additional SAT-feedback step. Exact settings remain in the registration.

This is a **cold realization-workflow comparison**, not the literal untouched PointSAT driver or steady-state batch throughput. The original arm combines the frozen original flippability implementation with the untouched native solver. Updated arms use the revised checker, persistent only within that trajectory. Conversion, required mapping, storage and geometry acceptance are common; no solver/cache is shared across targets or arms. Original → updated continuous includes both preparation and native-package changes. Updated plain/line/pair comparisons isolate those optional native flags; retry-only → feedback adds retargeting and its SAT overhead under the same segmented check schedule. Cold preparation can dominate short runs, especially for19 points.

Earlier native-budget runs are a distinct, partially completed diagnostic study—not equal-total-time controls and not pooled here.

The same fixed targets are reused after that diagnostic study; this is not an unseen holdout evaluation. Target-selection provenance is preserved below.

[Self-contained PDF](anytime-report.pdf)

![Verified-return curves](verified-returns.png)

[Vector figure](verified-returns.pdf)

## 19: no empty/3-interior hexagon

Registered targets: 2 per arm; total-time horizon: 60 s.

|Arm|Elapsed wall s|Verified returns / all targets|Observed through milestone or solved|Unobserved/early censored|
|---|---:|---:|---:|---:|
|Upstream|30|1 / 2|2|0|
|Upstream|60|1 / 2|2|0|
|v4 continuous|30|1 / 2|2|0|
|v4 continuous|60|1 / 2|2|0|
|v4 SAT feedback|30|1 / 2|2|0|
|v4 SAT feedback|60|1 / 2|2|0|

Matched outcomes on the same registered targets (all arm pairs are retained in JSON):

|First → second|Wall s|First only|Second only|Both|Neither|Provisional pairs|
|---|---:|---:|---:|---:|---:|---:|
|Upstream → v4 continuous|30|0|0|1|1|0|
|Upstream → v4 continuous|60|0|0|1|1|0|
|Upstream → v4 SAT feedback|30|0|0|1|1|0|
|Upstream → v4 SAT feedback|60|0|0|1|1|0|

## Compute and interruptions

All recorded attempts are counted below, including failed and interrupted attempts—not only successes. Component CPU is measured processor consumption; wall is not a CPU substitute. Summed worker wall is not calendar duration. Parent totals and component totals overlap and must not be added. Posthoc audit costs are outside the primary clock and separate.

|Family|Arm|Attempts|Preparation CPU s|Native CPU s|Feedback CPU s|Online verification CPU s|Parent CPU s|Posthoc CPU s|Parent wall s|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|symmetry19|Upstream|2|33.52|41.37|not recorded|0.03|75.04|4.36|78.39|
|symmetry19|v4 continuous|2|36.39|40.24|not recorded|0.04|77.67|4.54|81.10|
|symmetry19|v4 SAT feedback|2|35.19|28.93|12.14|0.06|77.32|4.51|80.44|

Persisted attempts: 6; incomplete attempts: 0; repeated case/arm attempts: 0; verified events after the horizon (excluded): 0.

Statuses: `{"SOLVED": 3, "TIME_LIMIT": 3}`.

Online deadline-exceeded checks: 0; online checker errors: 0. Search CPU lower-bound attempts: 2; posthoc CPU lower-bound attempts: 0. Abruptly killed descendants can leave unrecorded CPU; these are explicitly lower bounds, not exact complete totals.

Source registration: [registration.json](<../../benchmarks/anytime_smoke_20260907/registration.json>), SHA256 `22457096a82ba67122f0c4c581b208b976d42f88a76fc512f0baa80a50b8f319`.

Corpus provenance: `{"fresh": 9, "historical_initial_sat": 11}`. Fresh and reused/proof-filtered SAT target strata remain distinct. Historical selection did not inspect realization outcomes. The known positive-control type is excluded. The original benchmark CNF does not acquire generation-only cuts.

Outside-clock corpus construction: 1798.74 fresh-generation CPU s; 12.54 combined-corpus revalidation CPU s; 1.50 combine-controller CPU s. Fresh and combine timers are separate; historical generation sunk costs are not attributed to this batch.

## Separate earlier positive control

The known realizable control is excluded from the main target corpus. Its earlier native-budget diagnostic is not an equal-total-time trial; native timings are not interpreted as first verified-return times or pooled into these curves.

[Control provenance](<../../benchmarks/compare19_positive_control_20260907/result.json>), SHA256 `a3f57133eba3db0f7931ccdee4752ad52c460164fb86e3ac778683d7046b3b12`.

Machine snapshot: [reported hardware and environment](<../../benchmarks/scaling_machine_20260907.json>), SHA256 `0bd3a26900459081798e7de741a64ea7b80b292deea816ff2f7ee117ffe99099`. The recorded environment is virtualized; CPU topology is not evidence of dedicated physical cores. The benchmark has a two-worker limit.

The complete JSON retains event timestamps and certificate hashes, per-target censoring, all matched pairs, component timing coverage, and errors. No first-success time is inferred from a final coordinate file or posthoc audit. Operational failure is not an impossibility proof.

[Machine-readable report](report.json)
