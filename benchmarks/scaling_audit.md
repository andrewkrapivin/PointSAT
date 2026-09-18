# Independent scaling-study integrity audit

```sh
python3 benchmarks/scaling_audit.py \
  --registration benchmarks/compare19_run/registration.json benchmarks/paper_scaling_20260907/registration.json \
  --output benchmarks/scaling-integrity-NEW.json
```

Replace registration paths with the actual study directories. The output must not already exist. No native executable, geometry predicate, or SAT solver runs; the checker uses only the standard library and opens SQLite read-only. Prefer running after benchmark workers stop so disk/CPU auditing does not affect measured trials.

Checks include registered frozen/source hashes; every streamed, decompressed SQLite artifact SHA256; complete registered arm/budget conditions; SQL/JSON agreement; matched seeds and native allowances; independently reconstructed full and common initial targets; saved-coordinate/audit hash agreement; final-versus-any-checkpoint outcomes; duplicate completed conditions; recorded two-CPU limits; and independent SQL counts/pairing against the published summary.

The JSON distinguishes integrity faults from unfinished studies and records errors, watchdogs, missing outputs, forced kills, and abandoned attempts. A superseded incomplete attempt does not make an otherwise completed study pending. A summary that lags an actively locked controller is explicitly pending and must be rechecked once the controller stops.

- Exit `0`: no detected integrity fault; inspect `status` for `PASSED` versus `PENDING`.
- Exit `1`: integrity fault or the audit could not finish within its bound.
- Exit `2`: invalid invocation, including an existing output path.

Defaults: 600 seconds per study and 256 MiB expanded per artifact; override with `--seconds` and `--max-artifact-mib`. These are integrity/serialization checks, not independent reproofs of recorded geometric or SAT claims, and not signatures from a trusted external archive.

Tests: `python3 -m unittest benchmarks.test_scaling_audit`.
