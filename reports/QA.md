# Final workflow QA — 6 September 2026

From `/home/andrew/PointSAT`:

```sh
make test PYTHON=direct/vendor/venv/bin/python
git diff --check
```

Both exited successfully. The test target passed:

- 22 workflow/persistence tests, with no skips in the supplied virtual environment;
- 25 legacy pipeline tests;
- Localizer unit, exact sampler/line comparisons, CLI, budget and signal tests;
- 133 standard optimizer checks and 138 experimental optimizer checks.

Earlier independent checks include 30 repetitions of the concurrent scratch-file
regression, Localizer variant equivalence and sanitizers. Benchmark evidence has
separate exact validation; passing unit tests is not a solution certificate.

The first top-level test invocation exposed relative `PYTHON` propagation into
recursive Make. The Makefile now resolves explicit interpreter paths before
passing them to subdirectories; the full command above then passed.

## CLI smoke checks

`doctor` found all five native tools and python-sat in the supplied environment.
Automatic paper import, standard-v1 compaction, layer-filtered listing, points/SVG
export and independent re-verification passed. The 0.1-second native smoke budget
produced a valid 448×370 box with layers 3,4,4,6,5,1. This is an interface test,
not an optimization-quality benchmark. Records are in
`runs/standard-default-smoke/run.sqlite`.

Each of the four presets was also run with one sample, one worker, a four-second
search budget, two-second SAT limit, 0.5-second native attempts, and no automatic
compaction. Every command exited zero and left one database, with zero recorded
errors. Mixed23 and holes29 stopped at the SAT budget. Gons32 and caps26 generated
a SAT model, performed a native attempt and attempted feedback. None found a
solution; these very short checks do not measure solve rates. They are saved as
`runs/final-cli-{mixed23,holes29,gons32,caps26}/run.sqlite`.

The matched four-family benchmarks, not these smoke tests, provide search-policy
evidence. All new run/export paths above are ignored diagnostic artifacts;
existing user/research outputs were not replaced.

## Completed matched benchmark

`python3 benchmarks/test_strategy.py` passed five tests. Independent calls to
`benchmarks/check_evidence.py --require-complete` passed for both cohort
databases: all 128 trials, all 64 target/seed pairs and all 2,539 compressed
artifact hashes passed. SQLite integrity and exact subset-count consistency
checks passed. There were no unexpected worker exits, native-stage errors,
operational inspection errors, independent audit errors or external interruptions.
Three deadline-triggered SIGINT exits retained four audited checkpoints each;
their conservative CPU-accounting flags remain visible in the benchmark report.
The coordinator exited zero and reaped/cleaned its workers and process groups.
No owned search sessions remained at completion.
