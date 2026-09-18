# Direct geometric repair experiments

These later experiments focus only on 23 points with no convex heptagon and no
empty convex hexagon. All their inputs descend from cold geometric searches or
Overmars-style 22-point sets. They use neither SAT models nor published witnesses.
The earlier SAT comparison and SAT-seeded hybrid are documented separately in
`README.md`; their results should not be counted as cold direct constructions.

`fill_hole.cpp` reuses the validated exact scoring engine from `../search.cpp`
through `POINTSAT_GEOMETRY_ONLY`. Its neighborhood implementations are:

- Direct filling: choose a point outside an empty hexagon and relocate it just
  inside the polygon boundary, toward an interior target.
- Hole-directed cell steps: aim toward the empty polygon, but cross only the
  first line through two other points. This avoids jumping across many
  orientation constraints at once. Polygon vertices may also move.
- Guided breakout: remember up to 100 stubborn forbidden polygons by their point
  masks. After 5,000 scored evaluations without a best improvement or penalty
  update, increase a remembered polygon's weight. Exact hull and emptiness tests
  determine whether each remembered polygon is still present. Actual polygon
  counts, rather than weighted scores, determine successful solutions.

Optional hull penalties encourage a triangular outer hull; `--require-triangle`
preserves hull size three while permitting its vertices to move. This uses the
necessary triangular-hull condition for a valid 23-point set ([Theorem 2 of the
PointSAT paper](https://arxiv.org/pdf/2607.02958)). An optional
insertion stage samples a new point in a 22-point set before repair.

Floating-point arithmetic proposes directions and intersections. General
position, convexity, emptiness, and final success are checked with exact integer
predicates. Every saved best configuration is independently exhaustively checked
by `direct/verify`, with the certificate stored in its `.meta.json` file.

Build and run from the repository root:

```bash
c++ -O3 -std=c++17 -DNDEBUG direct/baseline/fill_hole.cpp -o direct/baseline/fill_hole_breakout
direct/baseline/fill_hole_breakout --input points23.pts --output best23.pts --seconds 400 --seed 71 --breakout --hull-penalty 1
direct/verify --input best23.pts --gon 7 --hole 6
```

Omit `--breakout` for direct filling, or replace it with `--adjacent-cells` for
hole-directed cell steps without remembered penalties. Add `--require-triangle`
when the input hull is triangular, or `--insert-samples 10000` when the input has
22 points and a 23-point start is desired. Input coordinates must have absolute
value at most 1e9.

Manifests and output folders preserve the staged experiments:

- `fill_hole_jobs.json` / `fill_hole_runs/`: four 120-second direct-filling trials.
- `fill_hole_cell_jobs.json` / `fill_hole_cells_runs/`: two 300-second directed-cell
  trials with a hull penalty.
- `breakout_jobs.json` / `breakout_runs/`: one guided-breakout trial interrupted
  after 362 seconds and one completed at 400 seconds. Two queued trials were
  cancelled before starting when a better geometric seed became available.
- `breakout_strong81.json`, `breakout_strong82.json` / `breakout_strong_runs/`:
  600- and 500-second trials from the new triangular one-hole 23-point set, both
  preserving a triangular hull. The frozen input and its provenance are saved.

The reprioritized queue's parent was paused before stopping its weaker worker;
this prevented queued trials from starting. The other worker completed normally.
`finalize_reprioritized.py` recovered both exact certificates and their complete
`/usr/bin/time` records after the paused parent was cancelled. Interrupted and
cancelled experiments are explicitly marked and are not treated as full runs.

The binaries used by the earlier stages are retained alongside their recorded
hashes. The source contains the final implementation of all three modes. Build
that source under the executable name used by a manifest when replaying it.
`summarize_direct.py` generates `direct_comparison.json`, including actual CPU
time and verified polygon counts. These searches remain heuristics; a failed run
does not prove impossibility.

## Results

| Neighborhood | Trials executed | CPU seconds | Fewest remaining forbidden polygons |
|---|---:|---:|---:|
| Direct filling | 4 | 444.68 | 2 holes |
| Hole-directed cell steps | 2 | 406.30 | 1 hole |
| Guided breakout | 4, including one interrupted | 1440.41 | 1 hole |

Across these ten runs, approximately 15.8 million candidates were scored in
2291.39 CPU seconds. No valid 23-point construction was found in this branch.
The directed-cell search improved an Overmars22-plus-one start from two holes to
one, with zero heptagons. Guided breakout also tried the stronger, independently
obtained triangular one-hole configuration for 600 and 500 seconds; neither run
removed its last hole. All final counts were independently certified. Two weaker
queued breakout trials were cancelled without running.

These figures describe staged searches, including reused near misses; they are
not a success-rate estimate from ten independent cold starts. The final direct
searches completed before 04:38 UTC on 2026-09-05. Machine sharing is reflected in
the difference between wall time and actual CPU time.
