# Proof-filtered symmetry-free 19-point search: final results

This arm **did not find a 19-point geometric solution**. The successful exact-C3
configuration came from the separate SAT-guided symmetry-constrained pipeline:
[witness and certificates](../../success19/README.md). Nonrealizability of
individual abstract targets does not imply nonexistence for the geometric problem.

## Exact proof filtering

- **639 new independently verified nonrealizability certificates** were
  saved, separately from **18 previously verified cuts reused at startup**.
- Proof-file statuses: `{'PROVED_NONREALIZABLE': 639, 'UNKNOWN': 2}`. There are 1 candidate
  orientation files without a complete proof output at cutoff; these are not
  counted as impossibility proofs.
- 2 abstract targets survived the filter with UNKNOWN status and were
  exported. UNKNOWN is not a realizability certificate.
- The producer used 969 orientation variables, 937992 base clauses, no C3
  constraints, geometric phase preferences, lazy forbidden-hexagon cuts, and
  increasing Hamming balls with configured maximum distance 60. Every proof cut
  was independently checked with exact integer arithmetic before use.

The configured BFP LP limit was 30 seconds per target. Complete proof output can
take longer because rational certificate reconstruction and checking are
additional stages; the subprocess allowance was 120 seconds. Summed reported
proof-stage elapsed time was 27101.104s.
This is not CPU time; overall producer CPU usage was not logged.

## Two surviving targets and geometric fallback

The consumer processed 2 targets, with
4 native runs total: 45 seconds of cold native v1 and 45 seconds of
warm native v6 plus line search per target. These were exploratory treatments,
not matched cold-start or fixed-work speed comparisons. All saved
coordinate outputs failed independent geometric validation.

|Target /native treatment|Orientation errors|Empty hexagons|Hexagons containing 3 points|
|---|---:|---:|---:|
|attempt000000-acbfcfd3f94f /v1_cold|4|3|4|
|attempt000000-acbfcfd3f94f /v6_line10_warm|4|3|4|
|attempt000001-881d62f4fb6b /v1_cold|3|3|3|
|attempt000001-881d62f4fb6b /v6_line10_warm|3|3|3|

Logged native totals were 180.308s
wall and 179.983s CPU. No success was obtained.

While waiting for proof-screened targets, the consumer started
457 bounded actual-geometry fallbacks; 457 have
saved result records. They used 60-second nominal budgets, except at cutoff.
Their logged totals were 27414.455s wall and
27082.321s CPU. The best independently checked geometry
still contains **2 empty hexagons and 0 hexagons with exactly three
interior points**, so it is a near-miss, not a witness. Its full histogram is
`[2, 19, 15, 0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0]`. No geometric solution was found (`success=False`).

## Cutoff and artifacts

Both one-core jobs shared the 14:00UTC supervisor deadline and were budgeted
for 30000 seconds internally. Shutdown grace reserves time before that deadline;
unfinished work is **cutoff-censored**, not an UNSAT or exhaustive-search result.
The producer ended with SIGTERM (exit -15); the consumer saved its checkpoint
and exited 0. Both deadline-stop records show no remaining tagged children.
One final geometry fallback was interrupted and retained its result record.
The two exported UNKNOWN models and any incomplete last proof remain unresolved.
Producer counts above require both a claimed proof file and an existing
independent checker report; no numerical LP candidate alone is counted.

[aggregate.json](aggregate.json) records proof/checker paths and hashes, status
counts, all consumer results, CPU/wall totals, the final checkpoint, and the
supervisor's termination records. [corpus/events.jsonl](corpus/events.jsonl)
records sound-cut insertion; [consumer/checkpoint.json](consumer/checkpoint.json)
locates the best near-miss and its exact verification. Frozen sources,
parameters, and startup proofs are in [freeze.json](freeze.json) and [jobs.json](jobs.json).
This report only reads existing logs; no new search or proof runs were launched.
