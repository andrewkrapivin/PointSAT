# Direct geometric solvers for the 23-point PointSAT problem

The repository's main problem is **23 points in general position, with no
convex 7-gon and no empty convex 6-gon**. A `k`-hole means an empty convex
`k`-gon. The paper proves 23 is maximum for these simultaneous conditions;
searching for 24 would contradict that established upper bound.

All expensive geometry/search loops below are C++17. Python only schedules
processes, records measurements, runs differential tests, and makes figures.
No SAT or realizability dependency is required to build the direct solvers.

See [RESULTS23.md](RESULTS23.md) for measured results. Earlier experiments
on related problems are archived; after the user's refocus, every long
search targets the 23-point problem.

## Build and run

```bash
make -C direct -j2
direct/search --n 23 --gon 7 --hole 6 --mode repair --seconds 600 --seed 11 --output best.pts
direct/verify --input best.pts --gon 7 --hole 6
```

For triangular-hull search and Overmars growth with exhaustive insertion:

```bash
direct/triangle --n 23 --mode anneal --seconds 600 --seed 71 --output triangle23.pts
make -C direct exact
direct/arrangement --grow --n 23 --gon 7 --hole 6 --triangle --exact --boundary --intersections --seconds 600 --seed 104729 --output grow23.pts
```

`make exact` needs Boost headers, either installed normally or under
`direct/vendor/boost/usr/include` (downloaded locally for this session).
The other solvers need only a C++ compiler. Exact insertion uses 128-bit
arithmetic in its hot loop; Boost constructs certificates for feasible cells.

`best.pts` can be a **near miss**: inspect the verifier's `valid` flag.
Search termination is not a proof of impossibility. The search programs
save their best incumbent and emit progress as JSONL. The verifier exits
0 for a valid configuration, 1 for a geometric violation, and 2 for bad
input. Coordinates use `n` on the first line followed by `n` integer `x y`
pairs. Keep the `.pts` coordinates and their verification results together.

## Implemented methods

| Program | Method | Main use |
|---|---|---|
| `overmars` | Incremental insertion, Brownian motion, random backtracking, incumbent reservoir | Grow hole-free configurations directly |
| `search --mode anneal` | Simulated annealing of the number of forbidden polygons | Search from random coordinates |
| `search --mode late` | Late-acceptance local search | An alternative escape rule for local minima |
| `search --mode repair` | Conflict-guided moves, nearby orientation-boundary crossings, annealing | Repair near misses, including failed SAT realizations |
| `triangle` | Triangular hull, incremental orientations, early rejection, diverse incumbent bank | Focused 23-point search |
| `pool` | Candidate coordinates plus exact subset search | Replace several points of a valid 22-point set |
| `arrangement` | All cells of the arrangement of pair-lines | Complete one-point extension or relocation for fixed coordinates |
| `coupled` | Perturb one point, then exhaustively relocate another | Two-point repair of near misses |
| `baseline/fill_hole.cpp` | Hole-directed moves and guided breakout penalties | Escape recurring forbidden polygons in near misses |
| `construct` | Explicit Erdős–Szekeres construction with exact block separation | Known 32-point no-7-gon and 26-point no-7-gon/no-5-cap targets |
| `compact` | Feasible integer coordinate intervals and integer shears | Reduce coordinates while preserving an order type |

The Overmars implementation includes the quadratic angular sweep and a
cubic reference implementation selected with `--oracle cubic`. It uses
bit masks for empty-triangle tests and dynamic programming for convex
chains. See [overmars_notes.md](overmars_notes.md) for algorithm details,
including the differences from the unavailable original program.

The scoring search counts polygons by angular fan dynamic programming.
Each polygon is counted once, at its lexicographically leftmost vertex.
A convex fan is empty exactly when each of its constituent triangles is
empty. The counting oracle costs O(k n^4); the insertion oracle used by
`overmars` is O(n^2), after baseline preprocessing. These are different
operations: do not compare counts per second with insertion proposals per
second as if they were the same benchmark.

`construct` implements a **known mathematical construction**, not an
unconstrained discovery or a new extremal theorem. It solves the same
32-point existence benchmark on which the paper's general PointSAT search
reported no witnesses. See [construct_notes.md](construct_notes.md).

## Other targets and seeded searches

```bash
# Overmars-style growth, pure no-empty-hexagon problem.
direct/overmars --n 29 --gon 0 --hole 6 --seconds 600 --seed 130363 --output growth.pts

# Constructive benchmarks, followed by exact independent verification.
direct/construct --gon 7 --output es32.pts
direct/verify --input es32.pts --gon 7 --hole 0
direct/construct --gon 7 --cap 5 --output es26.pts
direct/verify --input es26.pts --gon 7 --hole 0 --cap 5

# Count actual geometric violations in a failed realization.
direct/search --input candidate.pts --gon 7 --hole 6 --count

# Repair it directly. This is a seeded/hybrid search, not a cold search.
direct/search --input candidate.pts --mode repair --seconds 600 --seed 4102 --temperature 0.5 --stop-on-solution --output repaired.pts

# Search on a smaller grid starting from a published configuration.
direct/search --input direct/seeds/paper23.pts --grid 400 --mode repair --temperature 0.5 --seed 12 --seconds 60 --stop-on-solution --output smaller.pts

# Preserve all orientation signs while compressing coordinates.
direct/compact --input smaller.pts --seconds 10 --seed 1 --output compact.pts

# Caps also depend on x order; enable this when compressing cap-free sets.
direct/compact --input es26.pts --preserve-x-order --seconds 10 --output compact26.pts
```

Search coordinates must have magnitude at most 10^9; its maximum size is
40 points and supported forbidden polygon sizes are 3–9. The exhaustive
verifier supports coordinates up to 10^18 with signed 128-bit determinants.
The search checks every proposal using exact integer predicates. Floating
point is used only to propose moves, rescale starts, and choose random
acceptance probabilities. Scaling a seed to a small grid can change its
order type; the resulting configuration is scored afresh and only the
independent exact verifier certifies a solution.

Removing an interior point can expose a hole. Accordingly, the Overmars
search checks a moved point's final configuration when needed, restricts
its ordinary backtracking to hull deletions, and never assumes that an
arbitrary subset of a hole-free set is hole-free. The independent verifier
enumerates subsets and builds their convex hulls; it shares no geometric
oracle code with the search programs.

For complete relocation of one point, delete it and run `arrangement
--allow-base-holes --input deletion.pts`. This also handles holes exposed
by deletion: the new point must fill every old hole while avoiding new
forbidden polygons. Without that flag the seed must already be hole-free.
`no_extension_fixed_seed` proves nonextendibility only for those fixed
coordinates. `verify_big` independently checks integer certificates too
large for the 128-bit verifier.

## Reproduce experiments and checks

```bash
make -C direct test
python3 direct/test_verify.py
python3 direct/test_oracles.py --search direct/search --overmars direct/overmars --test-caps
python3 direct/run_experiments.py direct/portfolio23.json --output direct/results/new-run --workers 8
```

The focused portfolio runs eight 23-point searches for up to one hour at
eight concurrent jobs. Run `make -C direct exact` first. Fewer workers
increase elapsed time because jobs queue. The earlier mixed-problem
`portfolio.json` is retained for reproducing the initial experiments.
Each job records its command, seed, executable hash, wall and CPU
seconds, peak memory, stdout, best coordinates, and exhaustive validation.
Fixed seeds reproduce random decisions for a fixed binary, but a wall-time
limit makes the final iteration count depend on scheduling and load.

The session's measurements and artifacts are under
[results/2026-09-05](results/2026-09-05). SAT baseline and hybrid experiments
are under [baseline](baseline), with original dependency commits recorded
in [baseline/versions.json](baseline/versions.json). Locally built external
dependencies and their virtual environment are under ignored `vendor/`.
The root PointSAT source and settings are not changed by these experiments.

## Sources

- Krapivin, Przybocki, Heule, [Toward Satisfiability Modulo Realizability](https://arxiv.org/abs/2607.02958), 2026.
- Overmars, [Finding sets of points without empty convex 6-gons](https://ics-archive.science.uu.nl/research/techreps/repo/CS-2001/2001-07.pdf), 2001 technical report.
- Duque, Fabila-Monroy, Hidalgo-Toscano, [Point sets with small integer coordinates and no large convex polygons](https://arxiv.org/abs/1602.03075), 2016.
