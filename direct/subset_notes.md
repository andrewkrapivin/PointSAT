# Geometric candidate-pool search for 23 points

`pool.cpp` seeks 23 points avoiding convex heptagons and empty convex hexagons.
It starts from a valid 22-point configuration found by direct coordinate search,
adds several proposed integer points, and searches subsets of the resulting
pool. Proposals include small Gaussian perturbations around existing points,
points spread across the bounding box, and perturbations of intersections of
lines through existing pairs. The original run used a 28-point pool: 22 old
points plus six proposed points.

The subset solver precomputes each convex forbidden polygon's vertex mask.
For a potential empty hexagon it also stores the mask of all pool points in
its interior. During search a hexagon is forbidden exactly when all its
vertices remain and none of its interior points remain. This handles the
fact that deleting a point can create an empty hole.

A search node branches by deleting one vertex of a currently forbidden
polygon. Every valid descendant must make one of those deletions; it cannot
restore a previously deleted interior point. A greedy family of vertex-disjoint
violated polygons gives a lower bound on further deletions. A memo table avoids
repeating retained masks. Timeouts preserve the known valid incumbent and are
reported explicitly. Exhaustion concerns only the coordinates in that one
pool, not arbitrary planar point sets.

If a pool has no 23-point solution, a second short search may find a different
valid 22-point subset after excluding an old vertex. This makes simultaneous
point replacement possible and evolves the geometric starting configuration.
Replacements prefer configurations with fewer hull vertices, because every
23-point solution has a triangular hull. All validity decisions use exact
integer determinants; floating point is used only to propose coordinates.

The initial precomputation enumerated all relevant subsets and took about
125 ms for a 28-point pool. The optimized version directly enumerates convex
angular chains and records interior masks through their triangle fans. In a
short smoke test this reduced precomputation to approximately 0.5–0.8 ms and
raised total throughput from roughly 7 to 69 pools per second. These are
short, concurrent-workload observations, not a controlled speedup benchmark.

Validation is independent of the search logic:

- `test_subset.py` compares maximum-subset results with direct brute force on
  24 small point sets, including mixed hole/gon conditions.
- `test_fans.cpp` compares every polygon vertex mask and interior mask from
  fan enumeration with exhaustive subset enumeration on 120 random cases.
- `verify.cpp` exhaustively checks every saved candidate claimed as a solution.

Examples:

```sh
g++ -O3 -std=c++17 direct/subset.cpp -o direct/subset
g++ -O3 -std=c++17 direct/pool.cpp -o direct/pool
direct/pool --input valid22.pts --pool-size 28 --pool-seconds 0.25 \
  --seconds 600 --seed 3903 --output pool-best.pts
direct/verify --input pool-best.pts --gon 7 --hole 6
```

`subset.cpp` remains a standalone exact solver for one fixed pool; its default
precomputation uses the simpler exhaustive implementation. `pool.cpp` includes
that search engine and uses the faster independently tested fan precomputation.

The final 600-second pool run processed 32356 pools, proposed 194136 additional
points, and accepted 4373 valid 22-point replacements. All 32356 tested pools
were exhausted without a 23-point subset. The final 22-point incumbent passed
exhaustive verification and had hull layers 3, 4, 4, 6, 4, 1. A subsequent
exact arrangement scan also ruled out adding a single point to those final
fixed coordinates. These observations do not rule out solutions after
additional coordinate changes.
