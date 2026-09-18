#!/usr/bin/env python3
"""Round large integer coordinates onto smaller grids, retaining every orientation."""
import argparse
from fractions import Fraction
import itertools
from pathlib import Path


def orientations(points):
    signs = []
    for a, b, c in itertools.combinations(points, 3):
        det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        signs.append((det > 0) - (det < 0))
    return signs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    tokens = [int(x) for x in args.input.read_text().split()]
    n = tokens[0]
    if len(tokens) != 1 + 2 * n:
        raise ValueError("Expected n and n coordinate pairs")
    points = list(zip(tokens[1::2], tokens[2::2]))
    signs = orientations(points)
    if 0 in signs:
        raise ValueError("Input has collinear triples")
    min_x, min_y = min(x for x, y in points), min(y for x, y in points)
    extent = max(max(x for x, y in points) - min_x, max(y for x, y in points) - min_y)
    candidate = points
    best_grid = extent
    # This geometric progression reports the best tested grid, not a global minimum.
    grid = 32
    while grid < extent:
        rounded = [(round(Fraction((x - min_x) * grid, extent)),
                    round(Fraction((y - min_y) * grid, extent))) for x, y in points]
        if orientations(rounded) == signs:
            candidate, best_grid = rounded, grid
            break
        grid = max(grid + 1, round(grid * 1.2))
    args.output.write_text(str(n) + "\n" + "".join(f"{x} {y}\n" for x, y in candidate))
    print(f"Preserved all {len(signs)} orientations at tested grid extent {best_grid}")


if __name__ == "__main__":
    main()
