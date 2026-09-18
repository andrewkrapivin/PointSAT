# Prospective overnight native-move comparison

Snapshot: 2026-09-05T13:54:33.707101+00:00. All 80 jobs completed.

This measures optional native search moves on newly generated SAT targets. It is **not** the earlier fixed-work 1.88–2.12× evaluator-speed test, and it is not an upstream-versus-improved pipeline benchmark.

## Registered protocol

Before target generation, registration froze 20 SAT draws per family, binaries, and treatments. Clause-only shuffling preserves every variable and sign; default Kissat generates the models. Native runs use one thread, `-i 10 -r 30000`, seeds 1/17/101, no warm coordinates, and the same **45-second wall budget**. Treatment order is prospectively randomized within each SAT draw. These are equal-time, **not equal-iteration/evaluation**, comparisons; actual CPU time is recorded because the shared machine was loaded. Failed SAT draws are retained, not replaced.

The three main treatments share the same frozen v5 binary: default, `--line-every 10`, and `--pair-every 10 --line-every 10`. The cap-specific comparison separately uses the same frozen v6 binary with `--ordered-x` off/on. Native orientation success is not accepted as geometric success without exact polygon/cap checks.

## SAT generation and denominators

| Family | Registered | SAT | SAT timeout | Unique orientation models | SAT CPU seconds | Native saved / expected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed23 | 20 | 20 | 0 | 20 | 409.3 | 180 / 180 |
| holes29 | 20 | 19 | 1 | 19 | 15850.5 | 171 / 171 |
| gons32 | 20 | 20 | 0 | 20 | 95.0 | 180 / 180 |
| caps26 | 20 | 20 | 0 | 20 | 25.9 | 300 / 300 |

Families: mixed23=no convex7/no empty6; holes29=no empty6; gons32=no convex7; caps26=no convex7/no5cap. SAT caps were respectively300/1800/180/180 seconds. Every generated target independently passed the original CNF check. Duplicate orientation hashes are clustered rather than treated as independent models.

## Native quality and timing

| Family | Treatment | Audited runs | Mean orientation errors | Exact orientation successes | Valid geometries | Mean CPU seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| mixed23 | v5_default | 60 | 20.02 | 0 | 0 | 44.49 |
| mixed23 | v5_line10 | 60 | 20.37 | 0 | 0 | 44.37 |
| mixed23 | v5_pair_line10 | 60 | 21.40 | 0 | 0 | 44.57 |
| holes29 | v5_default | 57 | 37.96 | 0 | 0 | 44.41 |
| holes29 | v5_line10 | 57 | 39.16 | 0 | 0 | 44.65 |
| holes29 | v5_pair_line10 | 57 | 39.95 | 0 | 0 | 44.51 |
| gons32 | v5_default | 60 | 126.75 | 0 | 0 | 44.44 |
| gons32 | v5_line10 | 60 | 128.05 | 0 | 0 | 44.20 |
| gons32 | v5_pair_line10 | 60 | 137.78 | 0 | 0 | 44.39 |
| caps26 | v5_default | 60 | 45.18 | 0 | 0 | 44.45 |
| caps26 | v5_line10 | 60 | 48.77 | 0 | 0 | 44.54 |
| caps26 | v5_pair_line10 | 60 | 51.82 | 0 | 0 | 44.59 |
| caps26 | v6_default | 60 | 45.10 | 0 | 0 | 44.50 |
| caps26 | v6_ordered_x | 60 | 72.03 | 0 | 0 | 44.34 |

## Matched effects

Positive reductions mean fewer errors with the optional treatment. Wins/ties/losses compare identical model hashes and native seeds. Intervals are exploratory 95% bootstrap intervals clustered by unique orientation model, not independent repetitions of each seed.

| Family | Comparison | Pairs | Models | Wins / ties / losses | Mean error reduction | Cluster interval |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| mixed23 | v5_default → v5_line10 | 60 | 20 | 21 / 10 / 29 | -0.35 | [-1.35, 0.67] |
| mixed23 | v5_default → v5_pair_line10 | 60 | 20 | 19 / 7 / 34 | -1.38 | [-2.42, -0.42] |
| holes29 | v5_default → v5_line10 | 57 | 19 | 22 / 4 / 31 | -1.19 | [-2.42, -0.04] |
| holes29 | v5_default → v5_pair_line10 | 57 | 19 | 15 / 7 / 35 | -1.98 | [-3.26, -0.88] |
| gons32 | v5_default → v5_line10 | 60 | 20 | 25 / 1 / 34 | -1.30 | [-4.65, 2.17] |
| gons32 | v5_default → v5_pair_line10 | 60 | 20 | 20 / 1 / 39 | -11.03 | [-16.02, -6.02] |
| caps26 | v5_default → v5_line10 | 60 | 20 | 18 / 4 / 38 | -3.58 | [-5.75, -1.25] |
| caps26 | v5_default → v5_pair_line10 | 60 | 20 | 11 / 3 / 46 | -6.63 | [-8.55, -4.68] |
| caps26 | v6_default → v6_ordered_x | 60 | 20 | 2 / 1 / 57 | -26.93 | [-32.98, -21.37] |

## Interpretation and reproduction

Total recorded native CPU: 36946.5s; SAT CPU: 16380.7s. Exact geometry successes: 0. SAT timeouts and unsuccessful realization searches are empirical failures under these budgets, not impossibility proofs. Lower orientation error is only a search proxy; the coordinate geometry remains the acceptance criterion.

In this prospective sample, both optional v5 treatments have worse mean orientation error than default in every family; the paired move is consistently worse. These data do not support enabling either universally. Ordered-x also has a substantial search cost here, although enforcing x order addresses a genuine cap-semantics constraint; the independent cap acceptance check remains necessary whichever proposal method is used. These conclusions concern cold 45-second searches, not warm SAT-feedback portfolios or all possible budgets.

The successful19-point discovery came from the separate SAT-feedback portfolio, not this cold four-family benchmark. These results also do not erase the separately measured evaluator speedup.

Reproduce this aggregation without rerunning any search:

```sh
python3 improvements/benchmarks/overnight/aggregate.py
```

Machine-readable [summary.json](summary.json) includes full denominators, duplicate clusters, interruptions, CPU totals, and paired effects. [registration.json](registration.json) records immutable binary/CNF hashes and prespecified treatments; per-draw raw records are under [runs/](runs/).
