# Native packaging ablation — 6 September 2026

The default remains the established optimized v6 algorithm. **Neither newly
tested micro-optimization was promoted:** measured differences were small or
negative, not a consistent improvement across all four problem families.

All variants used the same included input, seed 42, one thread, 300000 outer
iterations, and five repetitions per family. Caps26 used `--ordered-x` in every
arm. Within each repetition, executable order was deterministically shuffled.
There were 80 serial native runs; every run reached the full iteration cap.
All final coordinate bytes and all search counters matched v6 in every pair.

|Family|v6 CPU s|Known-weight sampling CPU s|Atomic stop CPU s|Both CPU s|
|---|---:|---:|---:|---:|
|23: no7-gon/no6-hole|1.023577|1.014740|1.038305|1.014794|
|29: no6-hole|2.253261|2.334689|2.256050|2.324614|
|32: no7-gon|3.277340|3.347627|3.378931|3.393043|
|26: no7-gon/no5-cap|2.505780|2.459909|2.504810|2.741106|

Values are median child-process CPU seconds, including startup, measured on a
shared loaded machine. These small changes do not support a reliable speedup
claim. In particular, do not infer an improvement from the fastest isolated
run or from the two cases where the sampling median was slightly lower.

The sampling candidate uses the exact invariant that each violated triple
contributes three per-point violations, avoiding reconstruction of the total
sampling weight. It preserves integer thresholds and RNG draws; positive
minimum-distance penalties deliberately retain the general sampler. The atomic
candidate replaces a mutex-protected stop-flag read with an atomic boolean,
without changing archive locking. Both remain compile-time experimental
variants; the default macros are zero.

The source package retains `--reference-evaluation` to isolate established
constraint caching/early-rejection improvements within v6. That is a different
comparison from the micro-optimization ablation here, and neither should be
confused with different-search upstream-versus-v6 success rates.

[RESULTS.json](RESULTS.json) contains exact medians, binary/input hashes,
compiler/platform information, iteration/proposal counts, and ratios. The
reproducible harness is [ablation.py](ablation.py). Original raw local records
are under `runs/ablation-20260906/` (generated files, excluded from Git).

These input files are abstract orientation search targets, not geometric
witnesses. Reported remaining violations were 8, 33, 140, and 51 respectively;
this fixed-work benchmark made no claim of solving the four geometric problems.
