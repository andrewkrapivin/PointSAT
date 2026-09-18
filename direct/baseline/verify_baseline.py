#!/usr/bin/env python3
"""Independently verify saved Localizer coordinates as exact printed decimals."""
import argparse
from fractions import Fraction
import functools
import itertools
import json
import math
from pathlib import Path
import subprocess


def integer_points(source):
    rows = [line.split() for line in source.read_text().splitlines() if line.strip()]
    points = [(Fraction(row[1]), Fraction(row[2])) for row in rows]
    scale = functools.reduce(math.lcm, (x.denominator for p in points for x in p), 1)
    integers = [(int(x * scale), int(y * scale)) for x, y in points]
    ox, oy = integers[0]
    integers = [(x - ox, y - oy) for x, y in integers]
    common = functools.reduce(math.gcd, (abs(x) for p in integers for x in p), 0) or 1
    return [(x // common, y // common) for x, y in integers]


def binary64_orientation_disagreements(source, decimal_points):
    rows = [line.split() for line in source.read_text().splitlines() if line.strip()]
    # PointSAT validates Fraction(float(...)); compare that exact binary64
    # interpretation with the exact decimal coordinates independently checked here.
    binary = [(Fraction(float(row[1])), Fraction(float(row[2]))) for row in rows]
    scale = functools.reduce(math.lcm, (x.denominator for p in binary for x in p), 1)
    binary = [(int(x * scale), int(y * scale)) for x, y in binary]
    def sign(points, ids):
        a, b, c = (points[i] for i in ids)
        d = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return (d > 0) - (d < 0)
    return sum(sign(binary, ids) != sign(decimal_points, ids)
               for ids in itertools.combinations(range(len(binary)), 3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run = args.run.resolve()
    out = run / "exact_points"
    out.mkdir(exist_ok=True)
    records = []
    for source in sorted((run / "scratch").glob("*.real")):
        points = integer_points(source)
        dest = out / (source.stem + ".pts")
        dest.write_text(str(len(points)) + "\n" + "".join(f"{x} {y}\n" for x, y in points))
        result = subprocess.run([str(root / "direct/verify"), "--input", str(dest),
                                 "--gon", "7", "--hole", "6"],
                                capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"Verifier failed for {source}: {result.stderr}")
        data = json.loads(result.stdout)
        data["source"] = str(source.relative_to(root))
        data["integer_points"] = str(dest.relative_to(root))
        data["decimal_vs_binary64_orientation_disagreements"] = binary64_orientation_disagreements(source, points)
        records.append(data)
    (run / "exact_verification.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    ranked = sorted(records, key=lambda r: (r["collinear_triples"] + r["duplicate_pairs"],
                                            r["convex_gons"] + r["empty_holes"]))
    summary = {"count": len(records), "valid": sum(r["valid"] for r in records),
               "best": ranked[:5],
               "decimal_vs_binary64_orientation_disagreements": sum(r["decimal_vs_binary64_orientation_disagreements"] for r in records),
               "verification_seconds": sum(r["seconds"] for r in records)}
    (run / "exact_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
