# Direct geometry19 arm: final results

Finalized 2026-09-05 14:00 UTC. This arm found **no solution**: its best
unrestricted set still has two empty convex hexagons and no three-interior
hexagons. The overall 19-point problem **was solved by the separate SAT-guided
Localizer feedback arm**, with an independently certified exact-C3 witness;
see [the solution](../../success19/README.md).

| Measure | Unrestricted | Exact C3 |
|---|---:|---:|
| Full 900-second runs | 30 | 30 |
| Additional deadline-censored runs | 1 | 1 |
| Native search wall seconds, including censored runs | 27,604.951 | 27,560.949 |
| Supervisor worker-wall seconds | 27,612.873 | 27,569.487 |
| Proposals evaluated | 1,727,127,211 | 1,624,715,703 |
| Independently audited candidate files | 514 | 527 |
| Distinct coordinate-file hashes within arm | 484 | 498 |
| Best forbidden-hexagon count | 2 | 3 |
| Geometrically valid candidates | 0 | 0 |

The objective is the unweighted count of convex hexagons containing exactly
zero or exactly three points. The queue did not improve its frozen starting
deficits. Acceptance weights, displacement scales, and restart schedules varied
as recorded in [jobs.json](jobs.json); all jobs used the same frozen C++ binary
and independent seeds. They were warm-started from shared audited snapshots,
not independent cold-start trials.

## Resources and cutoff

The two-single-core-worker supervisor ran from 06:19:00 to 13:59:31 UTC, stopping
within the user's 14:00 UTC deadline. Aggregate worker-wall time was 55,182.360
seconds (15.328 hours), excluding post-run audit time. **Process CPU time was
not recorded**; worker-wall time is not a measured CPU-time total.

Sixty runs received their full native 900-second budget. Job060 was cut short
after 604.928 native seconds and job061 after 560.923 seconds by the deadline
watchdog; both saved incumbents and were independently audited. All 62 launched
jobs and all 62 audit commands exited successfully. These partial runs are
censored observations, not full-budget failures.

The static manifest contains 128 jobs, but only jobs000–061 were launched.
Jobs062–127 (66 jobs) were skipped at the deadline and provide no experimental
outcomes. The supervisor's 128 handled events include these skips; they must
not be reported as 128 completed searches. See [supervisor summary](supervisor/summary.json)
and each launched job's batch_result.json for timing and exit records.

## Exact checks and interpretation

All 1,041 saved-candidate audits used the independent arbitrary-integer verifier,
examining every one of the 27,132 six-point subsets and checking general
position. No duplicate points or collinear triples were found. All 527
rotational candidate audits also confirmed exact Euclidean C3 symmetry through
the lattice-to-quadratic-field embedding. Counts include repeated shared seeds;
distinct file hashes do not imply distinct order types.

Representative best snapshots are [free.pts](inputs/free.pts),
[rot.pts](inputs/rot.pts), and [rot-empty.pts](inputs/rot-empty.pts). The latter
two have respectively three empty/zero three-interior hexagons and zero
empty/three three-interior hexagons. Per-job audit.json files contain complete
independent counts and certificate paths. Input and executable hashes are in
[manifest.json](manifest.json).

This is a negative result for this bounded direct-search portfolio, not an
impossibility result or a universal comparison of SAT and geometric search.
The successful SAT-guided arm used a different search mechanism and allocation;
these runs are not a controlled estimate of relative success probabilities.
