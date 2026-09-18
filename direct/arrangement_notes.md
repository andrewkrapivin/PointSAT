# Exact one-point extension and relocation

`arrangement.cpp` searches every possible order type obtained by adding one
point to fixed integer coordinates. Its geometric decisions use exact signed
128-bit integers. The hot loop calls the quadratic Overmars-style insertion
oracle; `--crosscheck` also evaluates the independent cubic recurrence.

## Why the enumeration is complete

Each pair of old points defines a line. A new point in general position must
avoid every such line, and its orientation with every old pair is constant
inside each open arrangement cell. Each cell is an intersection of open
half-planes. Since the old set contains a noncollinear triple, the arrangement
has nonparallel lines and every cell, including each unbounded cell, touches
at least one finite vertex.

At every intersection of two nonparallel pair-lines, the implementation tests
the four symbolic infinitesimal directions `+d1+d2`, `+d1-d2`, `-d1+d2`, and
`-d1-d2`, where each `d` is a direction along its line. This also handles
vertices where three or more lines concur: for each pair of angularly adjacent
rays bounding a cell sector, the sum of those rays lies strictly inside that
sector, and that pair appears in the enumeration. Directions lying on another
incident line are rejected; an interior direction from an adjacent pair
remains available. Therefore every cell is represented.

For a homogeneous intersection `(X,Y,W)`, with `W>0`, and perturbation direction
`(dx,dy)`, a line `a*x+b*y+c=0` has the sign of `a*X+b*Y+c*W` if this is
nonzero. Otherwise its sign is the sign of `a*dx+b*dy`. No numeric epsilon or
floating-point tolerance is used for these decisions. Complete sign vectors
deduplicate cells.

The default mode requires an already valid seed. `--allow-base-holes` permits
old empty holes and requires the new point to lie strictly inside every one
of them. Old convex gons make extension impossible. Every forbidden polygon
in the augmented set either uses the new point, in which case the insertion
oracle detects it, or uses only old points. The latter gons were rejected
already, and the latter holes are precisely the old holes that must be filled.
Thus the test covers all forbidden polygons in the final set.

## Arithmetic and certificates

Input coordinate magnitudes are limited to `10^9`. The largest bound needed
for homogeneous line evaluation is `48*(10^9)^4`, below the signed128-bit
limit. If a symbolic extension succeeds, an exact rational epsilon is chosen
small enough to preserve every line sign. The program first tries common
integer scalings within `10^18`, accepting rounded coordinates only when all
orientation signs still match. If this fails, it emits an exact integer
certificate with Boost arbitrary-precision integers. The independent
`verify.cpp` or `verify_big.cpp` exhaustively validates the emitted coordinates.

## Observed results and checks

A positive calibration removed a hull vertex from the published 23-point
solution. Enumeration found a valid 23-point extension in about 19 ms; independent
validation checked all 245157 convex 7-subsets and 100947 empty 6-subsets. Further
positive controls removed interior points. These are calibration runs from a
known solution, not discoveries from random coordinates. A separate control
started from a convex hexagon with an existing empty 6-hole; the generalized
mode inserted an interior point and the resulting 7-point set passed exhaustive
validation. This checks the hole-filling branch explicitly.

For the frozen direct-search candidate
`results/2026-09-05/one-hole-local-trap23.pts`, all 23 possible point deletions
were scanned with hole filling enabled and both insertion recurrences checked.
Each scan visited 22617 distinct cells and found no valid extension. The data
are in `results/2026-09-05/arrangement-all-relocations/summary.json`.
Consequently no single-point relocation repairs that particular candidate.
The statement concerns these fixed coordinates, not all configurations with
the same score or all 23-point sets.

The count 22617 equals the generic cell count for 231 pair-lines after accounting
for the 22 forced vertices where 21 lines concur:
`1 + 231 + binom(231,2) - 22*binom(20,2) = 22617`.
This is a useful additional coverage check; completeness does not require the
arrangement to be generic.

`arrangement --grow --exact` attaches this complete extension test to the
Overmars-style geometric search whenever a 22-point state stalls. `coupled.cpp`
instead perturbs one point of a near-solution across a nearby pair-line, then
completely searches the location of a second point. Its first perturbation is
heuristic; only the subsequent one-point search is exhaustive. It may walk
among configurations with one or two holes to diversify its starting state.

The 240-second coupled run made 1209 perturbation proposals and 1068 cell
scans, of which 1067 exhausted their arrangement and the final scan timed out.
It accepted 993 walks among near-solutions and finished with one hole; no new
23-point solution was found. Its historical JSON field `complete_scans`
counts all 1068 scans despite that name; newer code calls this field `scans`.
The separate `exhausted_scans` field records the 1067 completed scans correctly.
