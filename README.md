# PointSAT

PointSAT searches for planar point configurations using SAT and a native geometric
realizer. The current workflow includes compact run storage, bounded searches,
automatic integer-coordinate optimization, and independent exact verification.

The underlying research is described in *Toward Satisfiability Modulo
Realizability* by Andrew Krapivin, Benjamin Przybocki, and Marijn J. H. Heule.
The supplied [paper](Happy_ending.pdf) proves that 23 is the largest number of
points avoiding both an empty convex hexagon and a convex heptagon.

## Quick start

Use Python 3.10+, a C/C++ compiler, Make, and Boost headers for the exact checker.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
make
python -m pointsat doctor
```

Kissat and scranfilize must also be built. Existing builds in this repository's
`direct/vendor/` are detected automatically; other locations can be specified
in a settings file. See [installation and usage](docs/USAGE.md). On the current
machine, `direct/vendor/venv/bin/python` already has the Python dependencies.

```sh
# Search for 23-point solutions; automatically compact accepted coordinates.
python -m pointsat run --problem mixed23 --samples 20 --workers 2 --seconds 600 --out runs/demo

# Inspect a run even while it is active.
python -m pointsat status runs/demo
python -m pointsat solutions runs/demo

# Spend more time optimizing every saved solution, retaining hull-layer sizes.
python -m pointsat optimize runs/demo --seconds 60 --mode layers

# Only export files when you want them.
python -m pointsat export runs/demo --mode layers --out exports/demo --svg
```

Successful runs keep **one `run.sqlite` database**, with compressed events,
coordinates, metadata and deduplicated artifacts. SQLite's two temporary WAL
files may exist while a run is open. Native tools use a bounded temporary
workspace; interrupted runs retain recovery files instead of risking lost
coordinates. `python -m pointsat recover runs/demo` independently checks those
files. Existing research output is never deleted or migrated implicitly.

## Automatic coordinate optimization

No manually chosen `.or` / realization pairing is required:

```sh
# The paper example is built in, but it is only one benchmark input.
python -m pointsat optimize --paper --out runs/paper --seconds 60

# Discover, validate and optimize an entire collection.
python -m pointsat optimize --scan improvements/benchmarks/successes --out runs/collection --seconds 30

# Existing legacy PointSAT runs are detected through their realizations/ folder.
python -m pointsat optimize path/to/legacy-run --seconds 30 --problem mixed23
```

Modes are `layers` (default: retain hull-layer sizes), `order-type` (retain every
labeled orientation), and `free` (any configuration satisfying the same geometric
problem). Every candidate is checked independently with exact arithmetic; a
failed attempt never replaces the saved solution. Grid dimensions mean coordinate
spans, e.g. 64×78 means coordinates in `[0,64] × [0,78]`.
Use `solutions --mode layers` or `export --mode layers` to select a preserving
result if the collection also contains earlier free compactions. The standard
optimizer is v1; `--strategy experimental` enables v2, which helped the paper
example but regressed on five of six same-mode comparison inputs.

## Supported problems

| Preset | Points | Forbidden configurations |
| --- | ---: | --- |
| `mixed23` | 23 | convex 7-gon; empty convex 6-gon |
| `holes29` | 29 | empty convex 6-gon |
| `gons32` | 32 | convex 7-gon |
| `caps26` | 26 | convex 7-gon; 5-cap in the actual x direction |

Custom CNFs and the compressed 19-point symmetry encoding remain supported
through `--settings FILE.json`. Automatic geometric optimization currently
supports the four named families above. Full CNF satisfaction is never a
substitute for the separate cap check.

## Implementation, evidence, and compatibility

- [User guide and configuration](docs/USAGE.md)
- [Self-contained optimized Localizer](localizer/README.md)
- [Native optimizer and multi-example benchmarks](optimizer/README.md)
- [Matched feedback-on/off benchmark](benchmarks/README.md)
- [Localizer variants and time-budget scaling study](benchmarks/SCALING_STUDY.md)
- [Consolidated PDF report](reports/PointSAT-improvements.pdf)
- [Earlier exact 19-point solution](improvements/success19/README.md)

`python PointSAT.py run ...` also invokes the new interface. The original
`python PointSAT.py settings.json` entry point remains available with legacy
file output; use `python -m pointsat run --settings settings.json` to select
compact storage. Existing scripts such as `analyze.py` expect legacy output;
export events/artifacts or use `solutions --csv` for the new database.

Run `make test PYTHON=.venv/bin/python` for workflow, pipeline and native tests.
All performance claims distinguish fixed-work evaluation speed, storage overhead,
and actual success rates. Experimental native moves that did not help are not
enabled by default.
