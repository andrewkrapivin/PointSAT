# Equal-total-budget feedback versus warm retries

8/8 registered trials completed; 3s whole-trial wall limit per arm. Native code and starting target/seed are matched. Feedback costs, initial flippability, loading, and operational acceptance are charged to the limit. Independent post-hoc audits are separately timed and never guide search.

## Exact geometry outcomes

| Family | Target models | Paired trials | Retry only | Feedback only | Both | Neither |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | 1 | 1 | 0 | 0 | 0 | 1 |
| holes29 | 1 | 1 | 0 | 0 | 0 | 1 |
| gons32 | 1 | 1 | 0 | 0 | 0 | 1 |
| caps26 | 1 | 1 | 0 | 0 | 0 | 1 |

## Exposure and overhead

| Family | Arm | Trials | Stages | Mean wall | Mean CPU | Mean native CPU | Mean feedback wall | Mean initial flips |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | warm_retry | 1 | 1 | 3.06 | 3.04 | 1.85 | 0.00 | 0.34 |
| mixed23 | core_feedback | 1 | 1 | 3.06 | 3.03 | 1.75 | 0.00 | 0.29 |
| holes29 | warm_retry | 1 | 1 | 3.10 | 3.08 | 0.76 | 0.00 | 0.93 |
| holes29 | core_feedback | 1 | 1 | 3.14 | 3.08 | 0.51 | 0.00 | 0.93 |
| gons32 | warm_retry | 1 | 1 | 3.06 | 3.03 | 1.90 | 0.00 | 0.39 |
| gons32 | core_feedback | 1 | 1 | 3.06 | 3.03 | 2.06 | 0.00 | 0.36 |
| caps26 | warm_retry | 1 | 1 | 3.01 | 3.00 | 2.41 | 0.00 | 0.13 |
| caps26 | core_feedback | 1 | 1 | 3.01 | 3.01 | 2.32 | 0.00 | 0.13 |

## Interpretation

Primary outcomes are actual geometric validity, including caps, at saved native checkpoints. A feedback arm is allowed to change its target, so its remaining active-target errors are not an apples-to-apples metric against a fixed-target retry arm. Geometry-invalid trials are budget-censored, not certified nonrealizable. Discovery times, when present, are checkpoint upper bounds.

This small reused-target pilot is not sufficient for a universal success-rate claim. With few or zero solution events, report the paired counts rather than a misleading zero-width bootstrap confidence interval. Native time is expected to be lower in the feedback arm because repair and rechecking consume its fixed total budget.

See [summary.json](summary.json) for solver errors, budget watchdogs, external interruptions, feedback call counts, and audit costs. Every exact decimal checkpoint and native target/log is stored compressed in [results.sqlite](results.sqlite). JSON paths pointing into temporary trial folders are historical paths; the artifact table is the persistent source of truth.

```sh
python3 benchmarks/report.py summarize --database benchmarks/smoke_20260906/results.sqlite
python3 benchmarks/report.py export --database benchmarks/smoke_20260906/results.sqlite --trial 0 --output benchmarks/export-trial0
```
