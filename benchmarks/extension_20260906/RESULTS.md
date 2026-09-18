# Equal-total-budget feedback versus warm retries

64/64 registered trials completed; 60s whole-trial wall limit per arm. Native code and starting target/seed are matched. Feedback costs, initial flippability, loading, and operational acceptance are charged to the limit. Independent post-hoc audits are separately timed and never guide search.

## Exact geometry outcomes

| Family | Target models | Paired trials | Retry only | Feedback only | Both | Neither |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | 4 | 8 | 0 | 0 | 0 | 8 |
| holes29 | 4 | 8 | 0 | 4 | 0 | 4 |
| gons32 | 4 | 8 | 0 | 0 | 0 | 8 |
| caps26 | 4 | 8 | 0 | 0 | 0 | 8 |

## Exposure and overhead

| Family | Arm | Trials | Stages | Mean wall | Mean CPU | Mean native CPU | Mean feedback wall | Mean initial flips |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | warm_retry | 8 | 32 | 60.07 | 60.06 | 58.76 | 0.00 | 0.33 |
| mixed23 | core_feedback | 8 | 32 | 60.08 | 60.05 | 58.22 | 0.55 | 0.32 |
| holes29 | warm_retry | 8 | 32 | 60.13 | 60.11 | 57.61 | 0.00 | 0.96 |
| holes29 | core_feedback | 8 | 26 | 47.53 | 47.51 | 42.68 | 2.22 | 0.91 |
| gons32 | warm_retry | 8 | 32 | 60.07 | 60.03 | 58.85 | 0.00 | 0.36 |
| gons32 | core_feedback | 8 | 32 | 60.07 | 60.04 | 58.36 | 0.48 | 0.38 |
| caps26 | warm_retry | 8 | 32 | 60.05 | 60.03 | 59.40 | 0.00 | 0.14 |
| caps26 | core_feedback | 8 | 32 | 60.04 | 60.01 | 58.96 | 0.42 | 0.15 |

## Secondary exact geometry residual

This counts forbidden polygons in the best saved general-position checkpoint, independent of whichever SAT target the arm followed. Zero is a solution. Counts are compared only within a family; fewer polygons is a diagnostic, not a success certificate.

| Family | Median retry count | Median feedback count | Feedback better / tie / retry better |
| --- | ---: | ---: | ---: |
| mixed23 | 26.5 | 24.5 | 4 / 1 / 3 |
| holes29 | 5.5 | 0.5 | 8 / 0 / 0 |
| gons32 | 2028.0 | 1756.0 | 3 / 2 / 3 |
| caps26 | 381.5 | 412.5 | 4 / 3 / 1 |

## Interpretation

Primary outcomes are actual geometric validity, including caps, at saved native checkpoints. A feedback arm is allowed to change its target, so its remaining active-target errors are not an apples-to-apples metric against a fixed-target retry arm. Geometry-invalid trials are budget-censored, not certified nonrealizable. Discovery times, when present, are checkpoint upper bounds.

Successes in the shared initial native stage occur before either warm retries or feedback can act, so they cannot establish an effect of the assigned strategy. Their counts are recorded separately in summary.json.

This small reused-target pilot is not sufficient for a universal success-rate claim. With few or zero solution events, report the paired counts rather than a misleading zero-width bootstrap confidence interval. Native time is expected to be lower in the feedback arm because repair and rechecking consume its fixed total budget.

Nonzero exits are classified in summary.json: a watchdog SIGINT/SIGTERM/SIGKILL after saved checkpoints is a budget-censored exit, not automatically a solver error. Unexpected exits, native-stage exits, operational inspection errors, and independent audit errors have separate counters. Parent-observed CPU is retained exactly as measured; signal-killed trials carry a conservative flag that unreaped descendant CPU might be absent.

See [summary.json](summary.json) for solver errors, budget watchdogs, external interruptions, feedback call counts, and audit costs. Every exact decimal checkpoint and native target/log is stored compressed in [results.sqlite](results.sqlite). JSON paths pointing into temporary trial folders are historical paths; the artifact table is the persistent source of truth.

```sh
python3 benchmarks/report.py summarize --database benchmarks/extension_20260906/results.sqlite
python3 benchmarks/report.py export --database benchmarks/extension_20260906/results.sqlite --trial 0 --output benchmarks/export-trial0
```
