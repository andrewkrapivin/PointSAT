#!/usr/bin/env python3
"""Compare fixed-pool branch-and-bound with direct brute force on small sets."""
import argparse
import itertools
import json
import pathlib
import random
import subprocess
import tempfile


def det(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def hull(points):
    order = sorted(points)
    lo, hi = [], []
    for chain, stream in ((lo, order), (hi, reversed(order))):
        for p in stream:
            while len(chain) >= 2 and det(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
    return lo[:-1]+hi[:-1]


def valid(points, gon, hole):
    for k, empty in ((gon, False), (hole, True)):
        if not k:
            continue
        for polygon in itertools.combinations(points, k):
            boundary = hull(polygon)
            if len(boundary) != k:
                continue
            if not empty:
                return False
            if not any(all(det(boundary[i], boundary[(i+1)%k], p) > 0 for i in range(k)) for p in points if p not in polygon):
                return False
    return True


def brute(points, gon, hole):
    for n in range(len(points), 0, -1):
        for candidate in itertools.combinations(points, n):
            if valid(candidate, gon, hole):
                return n
    raise AssertionError("no singleton solution")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", default="direct/subset")
    parser.add_argument("--cases", type=int, default=24)
    args = parser.parse_args()
    rng = random.Random(20260905)
    with tempfile.TemporaryDirectory(prefix="pointsat-subset-test-") as temporary:
        input_path = pathlib.Path(temporary)/"input.pts"
        output_path = pathlib.Path(temporary)/"output.pts"
        for case in range(args.cases):
            n = 7+case%3
            points = []
            while len(points) < n:
                p = (rng.randrange(-100, 101), rng.randrange(-100, 101))
                if p not in points and all(det(a, b, p) for a, b in itertools.combinations(points, 2)):
                    points.append(p)
            gon, hole = ((4, 4), (5, 4), (0, 5), (6, 0))[case%4]
            expected = brute(points, gon, hole)
            input_path.write_text(str(n)+"\n"+"".join(f"{x} {y}\n" for x, y in points))
            result = subprocess.run([args.subset, "--input", str(input_path), "--output", str(output_path),
                                     "--gon", str(gon), "--hole", str(hole), "--n", str(n), "--seconds", "5"],
                                    text=True, capture_output=True, check=True)
            report = json.loads(result.stdout.splitlines()[-1])
            assert report["status"] in ("target_found", "exhausted_fixed_seed"), report
            assert report["best_n"] == expected, (points, gon, hole, expected, report)
            words = list(map(int, output_path.read_text().split()))
            found = list(zip(words[1::2], words[2::2]))
            assert words[0] == expected and set(found) <= set(points) and valid(found, gon, hole)
    print(json.dumps({"status": "passed", "cases": args.cases, "seed": 20260905}))


if __name__ == "__main__":
    main()
