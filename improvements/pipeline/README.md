# PointSAT pipeline improvements

The public entry point remains `PointSAT.py SETTINGS.json`. Its implementation
is in `improvements/pipeline/runner.py`; the original source was preserved at
`improvements/baseline/PointSAT.py` before edits (SHA256
`c75793148927ccc039ec7910f1a0698973cfc6f33e66793124e3d572835a604b`).
Existing user settings and result directories were not modified.

## What changed

- Each process worker retains one parsed base CNF and one incremental CaDiCaL
  instance. Root `FlippabilityChecker` supplies exact clause-screened flips;
  the same solver checks concrete coordinate orientations under assumptions.
- Clause shuffling occurs only for new SAT samples, never on realization jobs.
- Bounded in-flight jobs prioritize realizing each SAT result immediately;
  the old pipeline queued every SAT sample ahead of all realization jobs.
- SAT competition comments, explicit SAT/UNSAT/UNKNOWN, incomplete assignments,
  contradictory literals, exit codes, missing coordinates, and worker errors
  are handled explicitly. Empty/UNKNOWN output is not a model.
- External stages have isolated process groups. Timeout handling drains pipes,
  allows a bounded SIGINT save interval, then escalates to SIGKILL. Keyboard
  interruption first asks native workers to save, drains and logs in-flight
  results for a bounded grace interval, then terminates remaining groups.
- Exact coordinate decoding is shared with validation: printed decimals are
  converted to integers once. A general-position concrete assignment must
  satisfy the entire original CNF before being copied to `realizations/`.
- The26-point cap problem also requires exact zero actual5-cap count; a SAT
  realization can violate the encoding's implicit label/x-order assumption.
  Both primary and archived candidates have this additional geometric gate.
- Retry levels are integers (fixing the undefined `localizer_next_attempt`).
  Seeds derive deterministically from original SAT sample, root seed, and
  branch path. Optional retries warm-start the best previous partial.
- Every stage has separate timing: shuffling, SAT, checker initialization,
  flippability, Localizer, exact decoding, concrete CNF check, and feedback.
- `-n` now overrides the settings. A pre-existing `raw_results.jsonl` is never
  overwritten or ambiguously resumed: use a fresh output directory.

Settings are compatible with the original SAT/scranfilize and subcase workflows.
Important default changes: SAT calls are bounded to90s; `continue_if_realized`
defaults to false. A localizer timeout is not itself failure: its saved incumbent
is still exactly checked. In-flight jobs finish after `stop_on_solution`; no new
jobs are submitted. Stage times are sums of worker elapsed time, not isolated
CPU measurements.

## Optional native features

With the revised Localizer binary, enable
`"localizer_native_time_limit": true` and `"warm_start_retries": true`.
The pipeline supplies `-T SECONDS` and `-w PREVIOUS.real`; the external timeout
still acts as a fallback. `localizer_extra_args` is a JSON array, e.g.
`["-c", "rotation.constraints", "-f", "fixed.points", "-q"]`.
Those arguments are passed verbatim, without a shell. All indexing conventions
must match the chosen CNF; a different variable order requires conversion before
using the standard orientation decoder.

For the repository's unlabeled problems only, optionally set
`"radial_relabel_check": true` with `"problem_family": "mixed23"`, `"holes29"`,
or `"gons32"` (and the corresponding n). A concrete geometry can be valid but
fail the CNF's label-symmetry-breaking clauses. This mode tries an exact radial
permutation without moving any point, then rechecks the *entire* CNF. Accepted
permutations, canonical orientations, a full SAT assignment, and a JSON
certificate are saved separately. The original orientation-target violation
count is retained; relabeling is not reported as realizing that original target.
This option is rejected for the label-sensitive26-point cap problem and for
unspecified problem families. It is disabled by default.

`orientation_map_file` optionally supplies an explicit signed variable map:
`{"n":19,"primary_variables":327,"entries":[{"triple":[1,2,3],"literal":1},...]}`.
Every sorted point triple must appear exactly once. A negative literal reverses
the variable's orientation sign. SAT parsing projects onto exactly the mapped
variables; removing a flippable primary removes all of its orbit constraints.
Concrete coordinates are checked for agreement of *every* triple sharing a
primary variable. Inconsistencies are reported as `MAPPING_CONFLICT`, never
converted into an invented SAT assignment. This enables the user's compressed
19-pointC3 encoding; its explicit symmetry/fixed-point files still belong in
`localizer_extra_args`. Radial relabeling is disabled with compressed mappings.

## Optional geometric feedback

`feedback_rounds` defaults to0. A positive value enables a new, experimental
feedback step after ordinary retries are exhausted: use an UNSAT core of the
actual coordinate orientations to select assumptions to release; phase-prefer
the current geometry; find a nearby satisfiable abstract orientation assignment;
then warm-start Localizer from the current coordinates on that revised target.
Only UNSAT-core literals are released. No permanent blocking clause is added
because Localizer failed. This greedy method is not a minimum correction-set
algorithm and does not prove non-realizability.

Limits: `feedback_max_relaxed`, `feedback_max_solves`,
`feedback_conflict_budget` (per SAT call), `feedback_seconds` (checked between
SAT calls). A conflict budget is not an exact wall-clock bound on a single SAT
call. `feedback_remove_flippable` controls relaxation of the repaired target.
Core feedback requires a Localizer that supports `-w` and remains off by default.

`feedback_core_choice` accepts `hash` (default), `target_hash`, `margin`, or
`target_margin`. The target variants prioritize currently violated target
orientations; margin variants prefer small normalized triangle altitudes.
Margins are only a proposal heuristic: all acceptance predicates remain exact.
`feedback_radial_scaffold` optionally uses canonical radial labels as the SAT
feedback scaffold even when that concrete candidate still fails the CNF. It
requires `radial_relabel_check` and preserves the permutation and warm-start file.
Repeated full projected assignments have an exact bounded flippability cache
(`flippability_model_cache_size`,128bydefault); cache hits report zeroSATqueries.

`audit_run.py` independently validates all distinct accepted geometries using a
fresh SAT solver, every original clause, independent geometric enumeration, and
exact algebraicC3 reconstruction where requested. `build_unattended.py` freezes
pipeline source files and deterministic job settings for the deadline supervisor;
its manifest includes an independent audit command for every completed job.

`nonrealizability_proof_files` optionally lists exact product-inequality
certificates. A separate integer-only verifier checks every positive weight,
orientation premise, and exact cancellation before a certificate is used.
Localizer is skipped only when **all** certified premises remain in its actual
target, including after flippable orientations have been omitted.
`prepare_verified_cnf.py` creates a new CNF with independently verified sound
cuts, translating signed colex literals through the explicit map. It never
modifies the original CNF. These are mathematical impossibility cuts, not
heuristic exclusions based on failed search. The frozen 19-point queue uses
fresh SAT models from `verified19/with_two_verified_cuts.cnf`, with two verified
mapped cuts of327 and318 literals; it does not recycle fixed-model cubes.

The frozen queue is `unattended_20260905/jobs.json`; `freeze.json` records source,
native-binary, and CNF hashes. The root supervisor runs two single-core jobs at
a time until the specified deadline, gracefully saves native checkpoints, and
audits accepted geometries against the original problem CNF. For caps26,
nativev6 `--ordered-x` preserves strict label x-order during search and the
independent exact convex5-cap acceptance gate remains mandatory.

With nativev4, `localizer_archive_candidates` (0bydefault, at most10) requests
the final top-K coordinate archive and audits each distinct candidate exactly,
including full CNF and optional radial relabeling. The accepted archive file and
its target violation count are recorded separately from the best-objective file.
Archive duplicates are skipped by hash; search trajectories are unchanged by
export. `initial_warm_start_file` can seed the first realization from a specified
coordinate file, independently of whether retries are warm-started.

## Reproduce tests and experiments

```
direct/vendor/venv/bin/python -m unittest improvements.pipeline.test_pipeline -v
direct/vendor/venv/bin/python -m unittest improvements.pipeline.test_orientation_map -v
direct/vendor/venv/bin/python -m unittest improvements.pipeline.test_verified_cuts -v
direct/vendor/venv/bin/python PointSAT.py improvements/pipeline/smoke23.json --out /tmp/pointsat-new-smoke
direct/vendor/venv/bin/python improvements/pipeline/benchmark_pipeline.py
direct/vendor/venv/bin/python improvements/pipeline/run_feedback_portfolio.py
```

The benchmark runners refuse to overwrite their existing results. Use a fresh
checkout or change the dedicated output location before repeating. The paired
pipeline test uses the same immutable upstream Localizer on both sides to
isolate Python/helper changes; the feedback pilot is a separate search trial.
`generate_corpus.py` freezes tuning/held-out splits before SAT generation; its
manifest includes all timeouts, not only successful samples.
