# Constructive geometric baselines

`construct.cpp` implements the known Erdős–Szekeres construction, following
Sections 2.1, 2.3, and the final-step compression in Section 3 of
[Duque, Fabila-Monroy, and Hidalgo-Toscano](https://arxiv.org/pdf/1602.03075).
No SAT or stochastic realizability search is needed. Exact orientation
inequalities determine the translations of recursively constructed cup/cap
blocks. We search 1000 uniform inter-block gaps and apply an integer vertical
shear to reduce bounding-box area. These are finite coordinate choices inside
an already known constructive solution.

With `--gon 7`, all six blocks contain 32 points and forbid convex heptagons.
With `--gon 7 --cap 5`, the first four blocks have sizes 1, 5, 10, and 10;
their union has 26 points and additionally forbids 5-caps. A cap uses at most
`i+1` points from its first block `i` and one from each later block, hence at
most four vertices. The general heptagon restriction is hereditary under
deletion. Vertical shear preserves x order and therefore preserves caps.

The initial generated grids are 264 by 488 and 95 by 196. Each result has
been checked by `verify.cpp`, an independent exact validator that enumerates
all subsets and computes monotone convex hulls. The 32-point check examines
3,365,856 7-subsets. The 26-point check examines 657,800 7-subsets and 65,780
5-subsets for caps. Both outputs are in general position and have zero
forbidden configurations.

`benchmark_construct.py` measured 100 independent executable invocations per
target; generated files were identical across repetitions. On this machine,
median child CPU time was 24.178 milliseconds for 32 points and 11.233
milliseconds for 26. CPU times include process startup and output writing;
they exclude independent exhaustive verification. Median C++ wall times were
23.166 and 10.003 milliseconds, respectively. Other experiments were running
concurrently, so the report records both CPU and wall clocks. Complete
statistics and certificates are in `results/2026-09-05/construct_benchmark.json`.

The [PointSAT paper](https://arxiv.org/pdf/2607.02958), Section 6, reports zero
realizations for the 32-point problem after 2191 core hours and 200,000
abstract solutions. The constructive approach therefore handles a known
target that the paper's generic search did not solve. This is not a new
existence theorem or a fair speedup ratio between interchangeable solvers:
the constructive program encodes mathematical knowledge specific to these
targets, whereas PointSAT accepts more general constraints.

Short order-type-preserving compression runs also produced smaller integer
grids. Their coordinates and exact provenance are in
`results/2026-09-05/polished/README.md`. For cap restrictions, use
`compact --preserve-x-order`; general orientation preservation alone does not
preserve caps when x order changes.
