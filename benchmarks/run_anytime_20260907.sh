#!/usr/bin/env bash
# Run inside its own tmux window; the frozen coordinator handles resumability,
# two-core affinity, compressed artifacts, integrity checks and the final PDF.
set -u
cd /home/andrew/PointSAT || exit 1
study_log=/home/andrew/PointSAT/benchmarks/anytime_20260907/run.log
date -u '+%Y-%m-%dT%H:%M:%SZ coordinator_start' >> "$study_log"
direct/vendor/venv/bin/python -u benchmarks/anytime_20260907/frozen/anytime_compare.py run \
    --registration benchmarks/anytime_20260907/registration.json --workers 2 \
    >> "$study_log" 2>&1
study_exit=$?
printf 'coordinator_exit=%s\n' "$study_exit" >> "$study_log"
exit "$study_exit"
