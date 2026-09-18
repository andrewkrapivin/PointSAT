# Matched search-strategy benchmarks

The main unresolved causal question is whether SAT core feedback helps more
than spending the same total budget on ordinary warm retries. This benchmark
holds native code, targets, native seeds, initial flippability removal, and
acceptance rules fixed. It does not repeat the earlier native evaluator-speed
or optional-move experiments.

## Pilot registered before launch

- Four frozen SAT targets per paper family, chosen by increasing case ID and
  deduplicated by orientation hash. This is a reused benchmark corpus, not a
  claim of newly unseen heldout inputs. No SAT generation time is charged.
- Two native seeds, 271 and 811; two arms: ordinary warm retries and target-margin
  UNSAT-core feedback. 64 trials total, prospectively randomized execution order.
- Immutable Localizer v6 in both arms. 15-second native stages; a 60-second
  **whole-trial wall budget from process launch** includes imports, CNF loading,
  initial flippability, native work, feedback/flippability, and operational
  acceptance. Each feedback core-query loop has a 5-second guard; subsequent
  flippability work is also charged to the same whole-trial budget. Feedback
  therefore consumes time the control can spend searching. Fresh solver state
  per trial.
- Caps26 uses `--ordered-x` in both arms. Both use identical label-only radial
  canonicalization for the other families, and identical exact cap/polygon
  acceptance checks. No warm coordinate seed is provided initially.
- A watchdog requests a checkpoint at the budget, then escalates after one
  second. Search CPU and wall time, stage exposure, feedback overhead, budget
  censoring, and external interruption are recorded separately.
- Every saved native checkpoint receives the same independent exact geometry
  audit after the trial. This audit never guides either search and its time is
  recorded separately. Primary outcome is a valid geometric checkpoint, not
  agreement with the initial or repaired target. Discovery timestamps are
  upper bounds at saved checkpoints, not exact first-discovery times.
- At most three single-core trials run concurrently. Temporary trial folders
  are removed after compressed coordinates, target snapshots, and logs are
  committed to SQLite. Initial targets/CNFs and native/verifier/helper hashes
  are recorded in the immutable registration.

```sh
direct/vendor/venv/bin/python benchmarks/strategy.py register \
  --output benchmarks/pilot_20260906 --targets 4 --seconds 60 --seeds 271 811
python3 benchmarks/strategy.py run \
  --registration benchmarks/pilot_20260906/registration.json --workers 3
```

The 64-trial pilot is small: even a genuine benefit may produce too few solution
events for a reliable success-rate conclusion. Target errors after a repair
cannot be compared naively with errors against the original target; the primary
outcome is exact geometric validity.

## Unchanged prospective extension

The next four unique target models per family (zero-based positions 4–7) were
registered on September 6 before launching any extension trial. The extension
copies the pilot's frozen worker, helpers, native binary, seeds and budgets
byte-for-byte. It adds 64 trials, with no new strategy or tuning. The pilot and
extension each retain their own registration and SQLite evidence; the combined
report retains separate cohort outcomes alongside the pooled 128-trial totals.

```sh
python3 benchmarks/extend.py --parent benchmarks/pilot_20260906/registration.json \
  --output benchmarks/extension_20260906 --offset 4 --targets 4
python3 benchmarks/strategy.py run \
  --registration benchmarks/extension_20260906/registration.json --workers 3
python3 benchmarks/report.py summarize --database benchmarks/pilot_20260906/results.sqlite
python3 benchmarks/report.py summarize --database benchmarks/extension_20260906/results.sqlite
python3 benchmarks/combine.py
python3 benchmarks/test_strategy.py
python3 benchmarks/check_evidence.py --database benchmarks/pilot_20260906/results.sqlite --require-complete
python3 benchmarks/check_evidence.py --database benchmarks/extension_20260906/results.sqlite --require-complete
```

Registration commands require a new output directory; do not overwrite an
existing experiment. `run` resumes only unrecorded trials. Combined output is
[combined_20260906.json](combined_20260906.json), with a Markdown report and
paired-residual SVG/PDF alongside it. Exact evidence for the pilot's valid
29-point sets is under [success29/](success29/README.md). Shared-initial-stage
successes occur before either retry strategy acts and are reported separately.
The combined JSON also reports model-level outcomes: success with either seed
on a target counts as one solved target cluster, not two independent models.

## Local paper check

`Happy_ending.pdf`, SHA256
`7a1ea829fb5a83c7e6e8396f74c5098084a2ef0489ce31fcc2cfb2bb76bba5d6`,
contains no 64×78 grid claim. Figure 1 on page 2 prints all 23 coordinates of its
672×566 example; §5.2 on page 10 explicitly states the integer grid
`{0,...,672} × {0,...,566}`. The four benchmark families appear in §6.
The section 5 heading reverses the gon/hole sizes, but the theorem, figure,
and section body consistently specify no 6-hole and no 7-gon.
