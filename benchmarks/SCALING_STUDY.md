# Matched Localizer and time-budget comparison

This study uses 20 targets per problem: the 19-point hexagon-interior problem
and the four paper families. Each target has one fixed seed and fresh starts at
10, 30, and 60 seconds. These are single-thread **native wall-time allowances**,
not whole-pipeline deadlines. Preparation, SAT feedback, verification, CPU time,
and worker wall time are recorded separately.

The 19-point arms are untouched upstream Localizer, fixed-target v4, and v4
with one target-margin repair and a warm restart. The paper-family arms are
upstream, v6 plain, v6 with line moves, v6 with line and paired moves, and v6
with repair/restart. Repair splits the native allowance equally around the
SAT step; it is a compound strategy, not an isolated feedback ablation.
The 19-point runs all enforce the same C3 cycles and fixed center. Ordered-x
is disabled in every paper-family arm for upstream compatibility; exact
5-cap checking is still mandatory.

Each registration freezes executables, helpers, targets, seeds, condition
order, and hashes before running. A SQLite database holds compressed trial
artifacts and resumable progress. Exact final-checkpoint geometry is the
primary endpoint; any earlier saved valid checkpoint is secondary.

## Running and resuming

The active two-core queue is supervised by `run_scaling_suite.py`. Its progress
is in `scaling_suite_20260907/state.json` and its single append-only log is
`scaling_suite_20260907/suite.log`. It runs the 19-point study, resumes the paper
study, checks integrity, then builds `reports/scaling_20260907/scaling-report.pdf`.

Creating `scaling_suite_20260907/STOP` requests a graceful pause. Remove that
marker explicitly before resuming with the same supervisor command. Use the
marker or Ctrl-C rather than assuming the recorded PIDs are host PIDs: execution
can occur inside a PID namespace. The supervisor refuses changed source hashes
and existing final report/audit outputs rather than silently overwriting them.

Use the frozen harness belonging to the registration:

```sh
direct/vendor/venv/bin/python STUDY/frozen/compare19.py run \
  --registration STUDY/registration.json --workers 2

direct/vendor/venv/bin/python PAPER_STUDY/frozen/compare_families.py run \
  --registration PAPER_STUDY/registration.json --workers 2
```

Do not run both commands concurrently with two workers each: this experiment
has a two-core total cap. The paper harness accepts `--max-cases 1` for a clean
one-target batch. Ctrl-C or SIGTERM to the coordinator checkpoints and stops
owned workers; rerunning the same command skips completed conditions and
retries interrupted ones. Incomplete attempts remain in the database.

Use the harness's `summarize --registration ...` command for a current
snapshot. See [report instructions](SCALING_REPORT.md) for plots and tables.
The known-positive calibration is [reported separately](compare19_positive_control_20260907/README.md)
and is not part of the target comparison.

## Cost and a later 100-target study

At 20 targets per family, the registered native allowance is 46,000
single-thread seconds: 12.78 worker-hours, or 6.39 hours at two fully occupied
slots, before preparation and audits. Early successes may use less.

Registration accepts a target count and explicit budgets, but never invents
missing targets or repeats them to fill a requested count. A 100-target study
needs a larger independently prepared corpus and a new registration. The same
design has five times the native allowance (63.89 worker-hours). The current
harness deliberately restricts execution to one or two workers; higher-core
dispatch should be enabled and checked on the larger machine, with memory
usage and SAT/audit concurrency included in that resource limit.
