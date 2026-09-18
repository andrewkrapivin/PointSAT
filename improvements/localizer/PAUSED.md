# Native Localizer pause checkpoint — 2026-09-05 05:23 UTC

## Recovery update — 2026-09-05 05:27 UTC

The initial assessment below was incomplete: tool-session Ctrl-C stopped the
wrappers but orphaned native PIDs 172303 and 172329. The root worker subsequently
sent direct SIGTERM, and BOTH fine-run coordinate files were saved successfully:

- relaxed-model002-rot-line10-fine-s1911.real: 590.866 s, 10,670,215 iterations,
  252,078,138 proposals, best/final 3 orientation violations.
- free-line10-fine-s1912.real: 589.693 s, 33,346,234 iterations,
  800,239,474 proposals, best/final 6 orientation violations.

They are in results/search19/ and supersede the older restart seeds below.
The user resumed a new hour at 05:26:41. Future jobs must be stopped by direct
signals to verified native PIDs, not by assuming wrapper-session exit stops them.
The historical initial notes are retained below for transparency.

Search was stopped immediately at the user's request. No native jobs or queued
native orchestrators remain owned by the Localizer worker. No paired-orbit
proposal implementation was started.

## Stopped jobs

- Exec session 96277: v3, model002 relaxed orientation constraints, rotational
  symmetry, warm start, seed 1911, 24 subiterations, minimum radius 1e-6,
  line sweep every 10 proposals. Last flushed progress: approximately 402 s,
  6.50 million outer iterations, 3 orientation violations.
- Exec session 16255: v3, full 19-point orientation constraints, unrestricted
  coordinates, warm start, seed 1912, same fine/line options. Last flushed
  progress: approximately 454 s, 22.9 million iterations, 6 violations.

Both tool sessions returned exit 130 after tool-level Ctrl-C at about 05:23:09.
Unlike a direct SIGINT to the native process, this tool cancellation did not
allow final serialization: the two planned fine-run output .real files do NOT
exist. Their full coordinate states are therefore not recoverable. The previous
saved warm-start coordinates remain intact; no improvement beyond their scores
was observed in flushed logs. Native direct SIGINT/SIGTERM shutdown and output
serialization were separately tested successfully, including two workers.

## Saved restart inputs

Rotational relaxed model002 (3 reported orientation violations):
improvements/symmetry19/search/model002-relaxed-symmetric/points.real

Full unrestricted model (6 orientation violations):
improvements/localizer/results/search19/free-line10-s1902.real

These are warm restarts, not exact RNG/state continuation. Use new seeds to avoid
replaying the same truncated trajectories. Do not launch until the user resumes.

## Commands for a user-managed tmux session

Run from /home/andrew/PointSAT, one command in each of two panes. Foreground exec
ensures that a normal tmux Ctrl-C targets the native program directly.

    exec improvements/localizer/localizer_v4 \
      improvements/symmetry19/variants/model002-relaxed.or \
      -w improvements/symmetry19/search/model002-relaxed-symmetric/points.real \
      -c improvements/symmetry19/decoded/center19-adjacent.cycles \
      -f improvements/symmetry19/decoded/center19-adjacent.fixed \
      -T 600 -s 1921 -i 24 --min-radius 0.000001 --line-every 10 \
      --archive-prefix improvements/localizer/results/search19/resume-rot-s1921 \
      -o improvements/localizer/results/search19/resume-rot-s1921.real

    exec improvements/localizer/localizer_v4 \
      improvements/symmetry19/decoded/center19-adjacent.or \
      -w improvements/localizer/results/search19/free-line10-s1902.real \
      -T 600 -s 1922 -i 24 --min-radius 0.000001 --line-every 10 \
      --archive-prefix improvements/localizer/results/search19/resume-free-s1922 \
      -o improvements/localizer/results/search19/resume-free-s1922.real

## Completed search evidence

Earlier two runs each completed their native 600-second budget and saved output:

- rotational-s1901.real: 15 orientation violations, 41,614,559 outer iterations,
  337,694,603 proposals. Exact geometry: general position, 3 empty hexagons and
  6 hexagons containing exactly three points. Not a solution.
- free-line10-s1902.real: 6 violations, 105,092,302 outer iterations,
  1,050,891,580 proposals. Exact geometry: general position, 3 empty hexagons and
  3 hexagons containing exactly three points. Not a solution.

Files and logs are in improvements/localizer/results/search19/. Adjacent
.exact.pts files were produced by the independent bigint verifier workflow.

The earlier v1 benchmark produced an actual valid 23-point no-7-gon/no-6-hole
configuration with two orientation mismatches; the independent validation
worker owns that result under improvements/benchmarks/results/legacy23_v1/.

## Reproducible implementation

Final native binary localizer_v4:
SHA256 5033c4f1a8c206f28fee43bfa39f82a4b1787b17e7701a795268c2e5d4f7720b.
upstream.patch reproduces final v4; v1.patch and v3.patch preserve frozen
benchmark revisions. README.md describes exact changes and fixed-trajectory
performance results. native_tests.c and test_cli.py passed. Baseline binary was
preserved before all edits and remains unchanged.
