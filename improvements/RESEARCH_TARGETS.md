# Additional problems worth targeting

These are proposed future experiments, not newly solved results. The current
overnight allocation remains focused on the four PointSAT problems and the
supplied19-point question.

## Colored garment avoidance

The2026 garment-number paper reports13-point and15-point-sized gaps that
look suitable for the same SAT/order-type/realization workflow:

- Try13 points avoiding both a necklace and a pant; the reported bounds are
  `12 < G(necklace or pant) <= 21`.
- Try15 points avoiding a necklace; the reported lower bound is14.

These structures have specific colored geometric definitions, not merely
convex quadrilaterals. An encoder should implement those definitions and
cross-check the authors' configurations first. The existing public code is
also a useful source of independent test fixtures. [Garment-number paper](https://arxiv.org/abs/2603.05339),
[authors' code and coordinates](https://github.com/N-Coder/garment-numbers-colored-point-sets).

## Minimize empty red-red-blue triangles

For balanced sets withn red andn blue points, run finite extremal searches
with12–24 total points and minimize empty triangles with exactly two red
vertices. Published work proves an Omega(n^1.5) lower bound and discusses a
quadratic conjecture. Small optimized configurations could reveal structure
or provide test data; they would not settle the asymptotic conjecture.
[Chao, Dong and Wu](https://arxiv.org/abs/2409.17078).

## Why these fit the implementation

The orientation representation can be reused, with color variables or fixed
color labels added in SAT. Native left-of-edge/interior bitsets provide fast
actual-objective evaluation. Verified biquadratic impossibility cuts can
discard some nonrealizable abstract targets, while Localizer and direct
geometry supply complementary attempts to realize the survivors. None of
these methods alone decides realizability in general.

Do not allocate time to30 points with no empty hexagon: the universal30-point
empty-hexagon statement already has a computer-assisted proof.
[Heule and Scheucher](https://arxiv.org/abs/2403.00737).
