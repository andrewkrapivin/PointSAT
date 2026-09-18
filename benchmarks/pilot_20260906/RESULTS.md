# Equal-total-budget feedback versus warm retries

64/64 registered trials completed; 60s whole-trial wall limit per arm. Native code and starting target/seed are matched. Feedback costs, initial flippability, loading, and operational acceptance are charged to the limit. Independent post-hoc audits are separately timed and never guide search.

## Exact geometry outcomes

| Family | Target models | Paired trials | Retry only | Feedback only | Both | Neither |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | 4 | 8 | 0 | 0 | 0 | 8 |
| holes29 | 4 | 8 | 0 | 1 | 1 | 6 |
| gons32 | 4 | 8 | 0 | 0 | 0 | 8 |
| caps26 | 4 | 8 | 0 | 0 | 0 | 8 |

## Exposure and overhead

| Family | Arm | Trials | Stages | Mean wall | Mean CPU | Mean native CPU | Mean feedback wall | Mean initial flips |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | warm_retry | 8 | 32 | 60.10 | 59.90 | 58.14 | 0.00 | 0.47 |
| mixed23 | core_feedback | 8 | 32 | 60.09 | 59.86 | 57.31 | 0.96 | 0.42 |
| holes29 | warm_retry | 8 | 29 | 54.97 | 54.77 | 51.35 | 0.00 | 1.31 |
| holes29 | core_feedback | 8 | 29 | 54.01 | 53.84 | 47.28 | 3.32 | 1.23 |
| gons32 | warm_retry | 8 | 32 | 60.08 | 59.87 | 58.39 | 0.00 | 0.50 |
| gons32 | core_feedback | 8 | 32 | 60.09 | 59.95 | 57.85 | 0.62 | 0.51 |
| caps26 | warm_retry | 8 | 32 | 60.05 | 59.85 | 59.04 | 0.00 | 0.21 |
| caps26 | core_feedback | 8 | 32 | 60.06 | 59.86 | 58.30 | 0.70 | 0.23 |

## Secondary exact geometry residual

This counts forbidden polygons in the best saved general-position checkpoint, independent of whichever SAT target the arm followed. Zero is a solution. Counts are compared only within a family; fewer polygons is a diagnostic, not a success certificate.

| Family | Median retry count | Median feedback count | Feedback better / tie / retry better |
| --- | ---: | ---: | ---: |
| mixed23 | 18.0 | 14.0 | 6 / 1 / 1 |
| holes29 | 7.0 | 2.0 | 6 / 2 / 0 |
| gons32 | 2709.0 | 2478.0 | 2 / 1 / 5 |
| caps26 | 708.0 | 498.5 | 7 / 1 / 0 |

## Interpretation

Primary outcomes are actual geometric validity, including caps, at saved native checkpoints. A feedback arm is allowed to change its target, so its remaining active-target errors are not an apples-to-apples metric against a fixed-target retry arm. Geometry-invalid trials are budget-censored, not certified nonrealizable. Discovery times, when present, are checkpoint upper bounds.

Successes in the shared initial native stage occur before either warm retries or feedback can act, so they cannot establish an effect of the assigned strategy. Their counts are recorded separately in summary.json.

This small reused-target pilot is not sufficient for a universal success-rate claim. With few or zero solution events, report the paired counts rather than a misleading zero-width bootstrap confidence interval. Native time is expected to be lower in the feedback arm because repair and rechecking consume its fixed total budget.

Nonzero exits are classified in summary.json: a watchdog SIGINT/SIGTERM/SIGKILL after saved checkpoints is a budget-censored exit, not automatically a solver error. Unexpected exits, native-stage exits, operational inspection errors, and independent audit errors have separate counters. Parent-observed CPU is retained exactly as measured; signal-killed trials carry a conservative flag that unreaped descendant CPU might be absent.

See [summary.json](summary.json) for solver errors, budget watchdogs, external interruptions, feedback call counts, and audit costs. Every exact decimal checkpoint and native target/log is stored compressed in [results.sqlite](results.sqlite). JSON paths pointing into temporary trial folders are historical paths; the artifact table is the persistent source of truth.

```sh
python3 benchmarks/report.py summarize --database benchmarks/pilot_20260906/results.sqlite
python3 benchmarks/report.py export --database benchmarks/pilot_20260906/results.sqlite --trial 0 --output benchmarks/export-trial0
```
