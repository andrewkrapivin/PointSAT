#!/usr/bin/env python3
"""Differential tests against the exhaustive C++ verifier (search is never mocked)."""
import argparse
import json
import pathlib
import random
import subprocess
import tempfile
import time


def orientation(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def random_gp(rng, n):
    points = []
    while len(points) < n:
        p = (rng.randrange(-1000, 1001), rng.randrange(-1000, 1001))
        if p not in points and all(orientation(a, b, p) for i, a in enumerate(points) for b in points[i+1:]):
            points.append(p)
    return points


def run_json(argv, allowed=(0,)):
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    if result.returncode not in allowed:
        raise AssertionError(f"Command failed: {argv}\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", default="direct/verify")
    parser.add_argument("--search")
    parser.add_argument("--overmars")
    parser.add_argument("--overmars-oracle", choices=("quadratic", "cubic"), default="quadratic")
    parser.add_argument("--test-caps", action="store_true", help="also compare the search cap-counting DP")
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()
    if not (args.search or args.overmars):
        parser.error("specify --search and/or --overmars")
    rng = random.Random(20260905)
    start = time.monotonic()
    configurations = 0
    comparisons = 0
    with tempfile.TemporaryDirectory(prefix="pointsat-differential-") as temporary:
        fixture = pathlib.Path(temporary)/"input.pts"
        cases = []
        for n in range(6, 15):
            for _ in range(args.rounds):
                cases.append(random_gp(rng, n))
            cases.append([(x, x*x) for x in range(n)])
        for points in cases:
            configurations += 1
            fixture.write_text(str(len(points))+"\n"+"".join(f"{x} {y}\n" for x, y in points))
            # Cover disabled constraints, triangles, and larger polygons independently.
            targets = [(0, 6), (7, 0), (3, 3), (rng.randrange(3, 9), rng.randrange(3, 8))]
            for gon, hole in targets:
                common = ["--input", str(fixture), "--gon", str(gon), "--hole", str(hole)]
                truth = run_json([args.verify]+common, allowed=(0, 1))
                if args.search:
                    got = run_json([args.search]+common+["--count"])
                    assert (got["gons"], got["holes"]) == (truth["convex_gons"], truth["empty_holes"]), (points, gon, hole, truth, got)
                    comparisons += 1
                if args.overmars:
                    got = run_json([args.overmars]+common+["--check", "--oracle", args.overmars_oracle], allowed=(0, 1, 2))
                    assert got["valid"] == truth["valid"], (points, gon, hole, truth, got)
                    comparisons += 1
            if args.test_caps and args.search:
                for cap in (3, 5, rng.randrange(3, 9)):
                    common = ["--input", str(fixture), "--gon", "7", "--hole", "0", "--cap", str(cap)]
                    truth = run_json([args.verify]+common, allowed=(0, 1))
                    got = run_json([args.search]+common+["--count"])
                    assert (got["gons"], got["caps"]) == (truth["convex_gons"], truth["convex_caps"]), (points, cap, truth, got)
                    comparisons += 1
    print(json.dumps({"status": "passed", "random_seed": 20260905, "configurations": configurations,
                      "oracle_comparisons": comparisons, "seconds": time.monotonic()-start}))


if __name__ == "__main__":
    main()
