# Native handoff, 2026-09-05 06:20 UTC

The final portable Localizer deliverable is upstream.patch plus build.sh. A
clean upstream clone rebuilt to exactly the frozen localizer_v6 binary hash
5fab7d4c1fa7709c603f3f75771239b63a5533b2a36644fcc51fee44daf118a7.
Upstream unit tests, native differential/cache tests, and CLI/shutdown tests
passed. See README.md and ../benchmarks/ for precise benchmark boundaries.

The actual 19-point geometry search is geometry19.cpp, frozen as geometry19_v2
(SHA256 9620b9f1bc4f7d4f158b3cf5569cdc355149245202d046a43d0f24f33de6d62c).
The independent arbitrary-integer oracle matched 200 random/adversarial cases
for both versions. All reported geometry deficits below are exactly audited.

- Best unrestricted 19-point set: two empty convex hexagons, no hexagon with
  exactly three interior points; general position. Source:
  results/resume0526/geometry-free-s1962.pts. Reached after 245.926 seconds /
  15,236,291 proposals in its initial 900-second run. This is not a solution.
- Best C3 deficit: three. Queue seeds include both three empty/zero
  three-interior and zero empty/three three-interior configurations.
- Follow-up weighted/finer-scale 540-second runs retained those best deficits,
  evaluating 36,180,793 unrestricted and 35,059,029 C3 proposals.
- Native fixed-target model002-relaxed is proved nonrealizable by independent
  exact BFP certificate checks. Do not allocate more Localizer time to it.

## Unattended computation

unattended14/jobs.json contains 128 single-core actual-geometry jobs, alternating
unrestricted and C3, each with a native 900-second budget and 60-second atomic
checkpoints. The parent supervisor must enforce at most two concurrent workers
and the user deadline 14:00 UTC (10:00 EDT). No native jobs remained running at
handoff. The parent owns launching and stopping the central supervisor.

unattended14/manifest.json records exact seed snapshots, input and binary hashes,
and command-list hash. Every job includes audit_outputs.py as its post-run
independent exact audit; rotational audits additionally check the lattice's
exact Euclidean C3 realization. Smoke runs of both job types succeeded, including
full cache recomputation after every proposal. Smoke artifacts are retained in
unattended14/smoke-free and unattended14/smoke-rot.

Actual success requires an audit.json with any_valid true and a referenced
exact certificate. A zero native orientation count alone is not sufficient;
neither are low defect counts, stopped runs, or a screening test that found no
nonrealizability certificate.

For later review, inspect each job's audit.json and supervisor event log.
Geometry best output is points.pts; current and equal-best pool states are
points.pts.current.pts and points.pts.pool-N.pts. Direct SIGTERM saves incumbents;
do not assume canceling a wrapping terminal session stops host-visible workers.
