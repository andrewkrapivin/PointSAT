# PointSAT user guide

## Installation

Run commands from the repository root. Python dependencies are in
`requirements.txt`; a virtual environment is recommended. `make` builds the
repository-owned `localizer/build/localizer`, `optimizer/compact`, and
`direct/verify_big`. The last requires Boost multiprecision headers, commonly
provided by a system Boost development package. No upstream checkout needs to
be modified to build the optimized Localizer.

The SAT pipeline additionally needs Kissat and scranfilize. If not already
present, build them in separate directories:

```sh
git clone https://github.com/arminbiere/kissat.git
cd kissat
./configure
make
cd ..
git clone https://github.com/arminbiere/scranfilize.git
cd scranfilize
./configure
make
cd ..
python -m pointsat doctor
```

The CLI checks these normal locations, existing `direct/vendor` builds, and
PATH. A JSON settings file may override `cadical_loc`, `scranfilize_loc`, and
`localizer_loc`. Relative settings paths are interpreted from the current
working directory, matching the older script. Use absolute paths for jobs
launched from elsewhere. The repository-owned Localizer contains an upstream
license-status notice; no new upstream redistribution grant is asserted.

## Search controls

```sh
python -m pointsat run --problem mixed23 --samples 20 --workers 2 \
  --seconds 600 --attempt-seconds 15 --feedback hash --out runs/example
```

Defaults are 20 SAT samples, two single-thread workers, a 600-second search wall
budget, 15-second native attempts, up to three feedback rounds, and 10 additional
native optimization seconds per accepted solution. `--seconds` covers search;
shutdown can use the bounded checkpoint grace. Automatic optimization has a
separate, explicit per-solution budget. Use `--no-optimize` to disable it.

`--feedback off` uses ordinary warm retries; `hash` and `target-margin` select
different conflict-core release heuristics. The evidence does not establish
that either universally dominates. Optional Localizer line/paired moves are off
by default. The cap preset preserves label x order, and checks actual caps
independently. `--seed` controls native search/retries; settings `sat_seed_start`
controls the separate clause-shuffling sequence.

`--settings FILE.json` accepts advanced legacy settings, with explicit CLI
overrides. A contradictory `--problem` and known settings CNF/n/family is rejected
rather than silently searching a different problem. The original standalone
`PointSAT.py SETTINGS.json` retains its older output convention.

## Storage, inspection, and interruption

A normal completed modern run contains only `run.sqlite`. The coordinator is
the sole writer; readers can query a running WAL database. Events use zlib JSON
instead of executable serialization. Original artifacts are content-addressed
and compressed once, even when several events refer to the same bytes.
An event, its artifacts, and any accepted solution commit in one transaction.
Coordinates are never discarded solely because they missed the abstract target:
the concrete geometry can still satisfy the full CNF.

```sh
python -m pointsat status runs/example --json
python -m pointsat solutions runs/example --csv
python -m pointsat export runs/example --out exports/example --svg --events --artifacts
```

`--artifacts` writes one ZIP with an index mapping event/role/original filename
to archived content. Events retain original temporary paths as provenance; the
ZIP index is the supported way to recover those bytes after cleanup. Events
are exported in job-ID order and retain completion timestamps in their payloads.

Ctrl-C/SIGTERM stops submission and asks active native tools to save. A run
interrupted during persistence retains its bounded `.work-*` workspace and
records its location. `recover RUN` independently checks these candidate files,
imports valid geometries, and leaves the source files intact. It is idempotent
for an already imported labeled order type. It does not pretend to resume the
same random search state. A fresh search requires a fresh output directory;
no run database is silently overwritten. For SIGKILL/power failure, inspect the
database and any surviving `.work-*` files, then run recovery.

`--storage legacy` retains the historical files for debugging/comparison.
Existing research directories are not automatically deleted, vacuumed, or packed.

## Optimization and hull-layer studies

```sh
python -m pointsat optimize --paper --out runs/paper --seconds 60 --mode layers
python -m pointsat optimize --scan PATH/TO/COLLECTION --out runs/layers --seconds 30
python -m pointsat optimize runs/layers --seconds 120 --mode order-type
python -m pointsat solutions runs/layers --csv
```

The scanner prefers one normalized/compact/points file per result directory,
skips scratch trees, and validates every imported configuration. It imports at
most 100 inputs by default (`--max-inputs` overrides this). Duplicate labeled
orientation hashes are not counted as independent examples; differing hashes
alone do not prove nonisomorphism under relabeling.

Decimal `.real` files are parsed exactly, not through binary floats. Positive
axis scaling clears denominators. If necessary, bounded integer rounding is
accepted only after every orientation sign agrees; cap semantics are rechecked.
The original coordinates always remain in the database.
Preservation refers to those original coordinates: a previous `free` optimization
does not silently redefine the layers or order type of a later preserving run.
Use `solutions RUN --mode layers` and `export RUN --mode layers --out DIRECTORY`
to select the smallest saved result retaining those layers (`order-type` also
works). Without `--mode`, these commands show/export the smallest result overall,
including any earlier free compaction; they always report its actual layer sizes.

`--strategy standard` is the default improved optimizer (v1).
`--strategy experimental` selects the extended projective/centering portfolio
(v2). In a same-mode, same-budget six-input comparison, v2 improved one output
but worsened five; consequently it is not the default despite its better paper
example. The 101×78 paper result used experimental v2 for 600 seconds. Search
autooptimization exposes the same choice as `--optimize-strategy`.

The default `layers` mode fixes only the sizes of successive convex hulls, not
the complete orientation type or membership of each layer. `order-type` fixes
every labeled triple sign. `free` may change both. This permits comparisons
between geometric validity, layer-constrained compaction and the stricter
realization problem. Switching modes is explicit; the optimizer does not tune
itself toward the paper's particular coordinates or a hard-coded 64×78 target.

Every accepted optimized result includes before/after spans, area, hull-layer
sizes, orientation changes, seed, binary hash, timings, and a separate exhaustive
exact certificate. The native optimizer does not certify satisfaction of an
arbitrary custom CNF after changing order type; only the selected geometric
family is claimed for those outputs. Exported point labels may differ from a
CNF's symmetry-breaking convention.

## Benchmarks and limitations

The storage replay is reproducible with:

```sh
python -m pointsat.bench_storage --samples 200 --repeats 3 --out storage-results.json
```

This isolates storage/coordinator overhead with identical semantic records;
it is not a SAT benchmark. Native and geometric benchmarks are documented in
`localizer/benchmarks/RESULTS.md`, `optimizer/README.md`, and `benchmarks/README.md`.
Bounded failures mean no solution was found within a budget, never UNSAT.
The PDF report separates exploratory tuning examples from frozen tests and
does not claim a universal time-to-solution multiplier.
