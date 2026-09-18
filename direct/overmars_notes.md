# Overmars-style direct coordinate search

`overmars.cpp` implements grow, Brownian motion, and random backtracking,
following the search strategy in Mark Overmars,
[Finding sets of points without empty convex 6-gons (2001)](https://ics-archive.science.uu.nl/research/techreps/repo/CS-2001/2001-07.pdf).
The report describes finding 29 points after about four days, and testing
approximately 15,000 insertion candidates per second at n=29 on a 500 MHz
Pentium III. Those historical numbers concern pure empty hexagon avoidance;
they are not measurements for PointSAT's additional convex heptagon constraint.

## Implementation

Build with `g++ -O3 -std=c++17 -DNDEBUG direct/overmars.cpp -o direct/overmars`.

The default insertion oracle is quadratic in the number of existing points
(for the implemented limit of 63 points). It sorts around the new point,
then sweeps angularly ordered incoming and outgoing edges at every old point.
Each edge stores the latest possible starting vertex for every chain length.
Later starts dominate earlier starts because the complete fan must span less
than pi. Prefix maxima allow linear processing per pivot. The radial orders
around old points are computed once for each baseline point set and reused.

A fan triangle is empty exactly when three left-half-plane bit masks have
empty intersection. Every geometric predicate uses integer coordinates and
`__int128` determinants. There are no floating-point geometric decisions;
floating point is used only to propose coordinates, which are rounded to
integers before checking. Accepted coordinates are bounded well below the
determinant overflow limit. Polygon sizes 3 through 10 are supported; size 0
disables that constraint.

`--oracle cubic` selects the simpler cubic DP recurrence. `--crosscheck`
evaluates both recurrences for every query and aborts on disagreement.
`--check` validates the whole final set. `--benchmark` measures repeated
insertion tests into an unchanged, verified input set.

Deletion can expose a previously blocked empty polygon. The search therefore
uses hull vertices for backtracking. A point move that preserves all triangle
orientations preserves validity immediately. A move that changes the order
type gets both an insertion test and a complete check at every pivot.
Similarly, the full-set checker never rejects a set just because a prefix
contains an empty polygon: a later point might fill it.

The heuristic draws proposals uniformly in several bounding boxes, close to
existing points at several scales, and inside random triangles. It retries
growth after Brownian motion before backtracking (`--patience`, default 4),
and maintains a reservoir of up to 64 valid incumbent configurations. This
is a stochastic construction heuristic, not an impossibility proof.
After backtracking, exact translation and integer dilation restore coordinate
resolution lost as repeated hull deletions shrink the cloud.

`--intersections` targets small insertion cells by sampling sectors around
intersections of point-pair lines. The distance to every other line controls
the perturbation size. `--boundary` directs half the Brownian proposals across
the nearest point-pair line along a random ray. This explores adjacent
realizable order types instead of relying entirely on random displacements.
Both are proposal heuristics: the same exact integer oracle makes every
acceptance decision, including complete checks for changed order types.

`--triangle` fixes the outer three vertices and searches only inside their
triangle. A cold run starts with a large integer triangle. With input, outer
vertices are safely deleted until the hull is triangular, then placed first
in the point array. Interior backtracking deletions receive complete checks
because they may expose holes. The deepest convex layer receives extra
insertion proposals. This concentrates the search on the triangular-hull
structure required by the 23-point target: see Theorem 5.1 in
[Toward Satisfiability Modulo Realizability, section 5.3](https://arxiv.org/html/2607.02958v1#S5.SS3).
The structural restriction comes from that theorem; the coordinate search
itself does not call a SAT solver or use published 23-point coordinates.

The optional arrangement wrapper can install `extension_search` and invoke
the regular search with `--exact`. After random insertion fails at 22 points,
the wrapper can enumerate every line-arrangement cell with symbolic exact
orientations. `Oracle::insertion_signs` evaluates these cells directly, and
the extension callback supplies verified integer coordinates if it succeeds.
Full cell coverage can rule out extending the *fixed* current configuration;
Brownian motion and backtracking then produce different configurations.

## Commands

```sh
direct/overmars --seconds 600 --seed 104729 --n 23 --gon 7 --hole 6 --output direct/results/2026-09-05/overmars_cold23.pts
direct/overmars --seconds 600 --seed 130363 --n 29 --gon 0 --hole 6 --output direct/results/2026-09-05/overmars_cold_hole6.pts
direct/overmars --input direct/seeds/paper23.pts --check --gon 7 --hole 6
direct/overmars --input direct/seeds/paper23.pts --benchmark --seconds 10 --output /tmp/overmars_benchmark.pts
```

Coordinates are written as a point count followed by integer pairs. Progress is
JSONL on stdout and in `<output>.jsonl`. Wall-clock time bounds the run; each
process uses one CPU thread. The solver stops early if it reaches `--n`.

## Verification and preliminary measurements

The initial cubic checker passed 1,836 independent exhaustive comparisons on
459 random and parabola configurations of 6 through 14 points, including
disabled constraints and polygon sizes 3 through 8. The quadratic replacement
passed the same suite independently. The published 23-point solution also
passes both algorithms. The exhaustive reference is `verify.cpp`, and the
reproducible differential harness is `test_oracles.py`.

The first development version (cubic DP, immediate backtracking after shaking,
no incumbent reservoir) ran cold for 300 seconds with seed 104729, gon=7,
hole=6. It reached 20 points in 0.916 seconds and 21 in 31.701 seconds, then
finished at 21 points after 3,108,028 candidate tests (10,359.96 per second,
including all shaking and full-set validation costs). Its saved configuration
is `overmars_cold23_best.pts`. This run predates automatic JSONL logging.
Later runs use the quadratic oracle and revised search and are recorded under
`results/2026-09-05/`.

Additional insertion-by-insertion checks ran the quadratic and cubic oracles
on 924,942 proposals into the published 23-point set and 1,129,570 proposals
into Overmars's published 29-point set, with no disagreement. Of the latter,
993,818 proposals were in general position. A ten-second insertion benchmark
at n=29 measured 169,242 proposals/s for the quadratic implementation and
142,216/s for the cubic recurrence, under concurrent search load. These are
proposal rates, including general-position rejection (about 12% of proposals
were degenerate), and are not complete-search solution rates. Current logs
also record process CPU seconds to distinguish scheduling contention.

With process CPU accounting, a further pair of ten-second n=29 benchmarks
measured 187,971 proposals/CPU-second for quadratic and 166,560 for cubic
(about 1.13 times faster). The end-to-end search improvement is larger:
orientation-preserving Brownian moves avoid repeated complete validation,
and exact normalization prevents the integer grid from becoming coarse.
The normalized cold pure-hole6 run, seed 130363, reached n=23 in 1.258 seconds,
n=24 in 9.144 seconds, and n=25 in 32.674 seconds. Exhaustive validation of
that 25-point configuration checked all 177,100 hexagon subsets and found
no empty hexagon or degeneracy.

## Focused 23-point search

After the task was restricted to the 23-point problem, the broader pure-hole6
run was stopped. Subsequent construction runs used cold coordinates or
22-point sets obtained by direct geometry search and pool evolution. Published
23-point coordinates were used only as correctness fixtures for the oracles.

The normalized unrestricted-hull cold run (seed 104729) first reached 22 points
after 70.652 seconds. The fixed-triangle cold run (seed 32452843) first reached
22 after 599.578 wall seconds / 474.270 CPU seconds. Both configurations passed
the independent exhaustive verifier. These are construction times for 22,
not successful construction times for the requested 23.

The focused variants also tested line-intersection insertion proposals,
boundary-directed motion, deeper-layer sampling, and a triangular hull prior.
The strongest insertion check enumerates the complete arrangement of the
231 pair-lines of a fixed 22-point set. In generic position this has 22,617
distinct cells; scanning them took about 0.2 seconds per configuration during
the evolving search. Exact extension checks were interleaved with geometric
motion and safe backtracking, so a failed check led to a different embedding.

Final focused runs completed at approximately 04:40 UTC on 2026-09-05:

| Variant | Wall seconds | CPU seconds | Work completed | Largest valid set |
|---|---:|---:|---|---:|
| Triangle, intersection proposals, boundary motion; direct pool22 seed 49979687 | 1,380.000 | 1,062.252 | 80,141,005 proposals; 1,376,717 accepted moves | 22 |
| Exact arrangement checks plus Brownian motion; cold-derived triangle22 seed 67867967 | 600.000 | 504.718 | 1,856 complete fixed22 cell scans; 2,972,385 additional random proposals; 444,084 accepted moves | 22 |

The first run processed 58,073 proposals/wall-second or 75,444/CPU-second.
The second covered about 42 million insertion cells in addition to its random
proposals. No 23-point construction was obtained in either run. Both final
saved 22-point configurations passed exhaustive checking of all 170,544
seven-point subsets and all 74,613 six-point subsets, with no forbidden polygon
and no degeneracy. Logs and coordinates are respectively:

- `results/2026-09-05/overmars_triangle_pool22_seed49979687.pts[.jsonl]`
- `results/2026-09-05/overmars_exact_triangle22_seed67867967.pts[.jsonl]`

The actual cold triangular-hull configuration used by the exact run is saved
at `results/2026-09-05/overmars_triangle_cold23_seed32452843.pts`.
