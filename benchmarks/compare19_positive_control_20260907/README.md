# Known-positive 19-point calibration, 2026-09-07

Both untouched upstream Localizer and improved v4 found independently certified solutions from cold starts. This **known-selected realizable target is excluded from the prospective 20-target corpus**. One pair is calibration, not a general speedup estimate; no settings were tuned from these outcomes.

| Arm | Native wall seconds | Native CPU seconds | Retained constraint violations | Original full-target sign differences |
|---|---:|---:|---:|---:|
| Original upstream | 1.670609 | 1.660796 | 0 / 945 | 3 / 969 |
| Improved v4, line10 | 1.520007 | 1.463576 | 0 / 945 | 6 / 969 |

Both stopped successfully before their 30-second allowances. No timeout, forced kill, warm start, coordinate seed, feedback, or archive was used. The entire calibration, including common preprocessing and both independent audits, took **32.233687 seconds wall / 31.902876 child CPU seconds**, sequentially on CPU 1, under a 300-second total cap.

## Matched input and provenance

The input is the complete 969-sign [known witness orientation](known-full.or), copied from `improvements/success19/witness.or`; its coordinate witness was not used for initialization. The explicit signed adapter projects these signs consistently to 327 C3-orbit variables and roundtrips all 969 signs. A single flippability check against the original CNF removed eight primary orbit variables, producing the same [945 retained constraints](common-initial.or) for both arms.

Both used seed `190907`, one solver thread, `-i 10 -r 30000`, the same six rotational cycles, and fixed center. Improved v4 additionally used `-T 30 --line-every 10 --min-radius 0.000001 -q`. Full commands, binary/source hashes, mapping and CNF hashes are in [registration.json](registration.json) and [result.json](result.json); exact frozen executables and helper sources are retained in `frozen/`.

The original binary is the preserved upstream commit `5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb` build, SHA256 `f5c0819778eba20ac1d8c1f231e922ac0f309372e8d79db9476aca801200b98c`. The v4 binary SHA256 is `5033c4f1a8c206f28fee43bfa39f82a4b1787b17e7701a795268c2e5d4f7720b`.

The original PointSAT script requires the encoding adapter for this compressed 327-variable input. This control shows that the **untouched upstream Localizer executable works when supplied the correctly expanded constraints**; it does not claim the original end-to-end script natively understands this encoding.

## Independent exact checks

For each printed-coordinate output, all 969 triples are noncollinear, there are no duplicate points, and exhaustive enumeration checks all 27,132 six-subsets. Both have 28 convex hexagons, with interior-count histogram `[0,15,12,0,1,0,0,0,0,0,0,0,0,0]`: none is empty and none contains exactly three other points.

Exact C3 reconstructions over `Q(sqrt(3))` preserve every printed-coordinate orientation sign and pass the same exhaustive geometry checks. Both raw and reconstructed chirotopes project consistently to the signed 327-variable encoding; independent SAT extension and clause scans pass all **2,311,196 original CNF clauses**, with zero violated clauses or wrong orientation assumptions. The full-target differences in the table occur only among the omitted constraints; exact checking of the retained 945 constraints gives zero violations in both outputs.

Artifacts:

- Original: [printed coordinates](original/stage0.real), [exact integer points](original/stage0-audit/points.pts), [exact C3 witness](original/stage0-audit/projected_c3.qsqrt3), [certificate](original/stage0-audit/certificate.json).
- Improved v4: [printed coordinates](improved_fixed/stage0.real), [exact integer points](improved_fixed/stage0-audit/points.pts), [exact C3 witness](improved_fixed/stage0-audit/projected_c3.qsqrt3), [certificate](improved_fixed/stage0-audit/certificate.json).

The driver is [compare19_positive_control.py](../compare19_positive_control.py). Reproduction requires a **new output directory** and does not overwrite this evidence.
