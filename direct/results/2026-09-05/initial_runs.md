Session started 2026-09-05 03:42:47 UTC; first sustained C++ scoring
experiments started about 03:46:24 UTC. Initial executable was the first
version of search.cpp, before conflict-guided moves were added.

All following runs used one process each, concurrently on the exposed
8-vCPU AMD Ryzen AI 9 365 environment. Coordinates start from random
integer points on [0,1000000]^2, except explicitly named seeded runs.

```
/tmp/pointsat-search --seconds 600 --n 23 --mode anneal --seed 1 --stop-on-solution --output direct/results/2026-09-05/anneal-23-s1.pts
/tmp/pointsat-search --seconds 600 --n 23 --mode late --seed 2 --stop-on-solution --output direct/results/2026-09-05/late-23-s2.pts
/tmp/pointsat-search --seconds 600 --n 29 --gon 0 --hole 6 --mode anneal --seed 3 --stop-on-solution --output direct/results/2026-09-05/anneal-29-s3.pts
/tmp/pointsat-compact --seconds 600 --input direct/seeds/paper23.pts --output direct/results/2026-09-05/compact-paper23-s1.pts --seed 1
```

Each stdout is retained as a same-stem JSONL file. These initial runs
record elapsed time and operation counts, but do not separately measure
per-process CPU time. Later portfolio jobs record wall time, CPU time,
maximum resident memory and binary hashes in `.meta.json` files.
Wall limits make operation counts scheduling-dependent even for fixed seeds.

`compact-paper23-s1` starts from the published witness and is a coordinate
optimization experiment, not a discovery from scratch.
