"""Small exact coordinate utilities; independent of SAT/native search code."""
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def read_points(path):
    rows = [line.split() for line in Path(path).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]
    if not rows:
        raise ValueError(f"No coordinates in {path}")
    if len(rows[0]) == 1:
        n = int(rows.pop(0)[0])
        if len(rows) != n or any(len(row) != 2 for row in rows):
            raise ValueError("A .pts file needs n followed by exactly n rows of x y")
    elif all(len(row) == 3 for row in rows):
        indexed = {int(row[0]): row[1:] for row in rows}
        if len(indexed) != len(rows) or set(indexed) != set(range(1, len(rows)+1)):
            raise ValueError("Indexed coordinates must have unique labels 1..n")
        rows = [indexed[i] for i in range(1, len(rows)+1)]
    elif not all(len(row) == 2 for row in rows):
        raise ValueError("Expected .pts coordinates or indexed .real coordinates")
    if not 3 <= len(rows) <= 40:
        raise ValueError("Expected 3..40 points")
    try:
        rational = [[Fraction(value) for value in row] for row in rows]
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Coordinates must be finite exact numbers") from exc
    scales = [math.lcm(*(p[axis].denominator for p in rational)) for axis in (0, 1)]
    return normalize([[int(p[axis]*scales[axis]) for axis in (0, 1)] for p in rational])


def normalize(points):
    """Translation and positive independent axis scaling preserve the order type."""
    minima = [min(p[k] for p in points) for k in (0, 1)]
    result = [[int(p[k]-minima[k]) for k in (0, 1)] for p in points]
    divisors = [math.gcd(*(p[k] for p in result)) or 1 for k in (0, 1)]
    return [[p[k]//divisors[k] for k in (0, 1)] for p in result]


def signs(points):
    values = [cross(points[a], points[b], points[c]) for a, b, c in combinations(range(len(points)), 3)]
    if any(value == 0 for value in values):
        raise ValueError("Points are not in general position (a collinear triple exists)")
    return bytes(1 if value > 0 else 0 for value in values)


def hull(points, indices):
    ordered = sorted(indices, key=lambda i: tuple(points[i]))
    if len(ordered) <= 2:
        return ordered
    lower, upper = [], []
    for sequence, target in ((ordered, lower), (ordered[::-1], upper)):
        for index in sequence:
            while len(target) >= 2 and cross(points[target[-2]], points[target[-1]], points[index]) <= 0:
                target.pop()
            target.append(index)
    return lower[:-1]+upper[:-1]


def describe(points):
    orientations = signs(points)
    remaining, layers = set(range(len(points))), []
    while remaining:
        outer = hull(points, remaining)
        layers.append(len(outer))
        remaining.difference_update(outer)
    width = max(p[0] for p in points)-min(p[0] for p in points)
    height = max(p[1] for p in points)-min(p[1] for p in points)
    return dict(n=len(points), width=width, height=height, area=width*height,
                grid_convention="coordinate spans; grid has (width+1)*(height+1) sites",
                hull_layers=layers, orientation_sha256=sha256(orientations).hexdigest(),
                coordinate_sha256=sha256(json.dumps(normalize(points), separators=(',', ':')).encode()).hexdigest(),
                general_position=True)


def bounded_points(points, limit=10**12):
    """Find smaller integer coordinates only when every orientation is preserved."""
    points = normalize(points)
    target = signs(points)
    width, height = max(p[0] for p in points), max(p[1] for p in points)
    candidates = [10**power for power in range(2, 13) if 10**power <= limit]
    for scale in candidates:
        if max(width, height) <= scale:
            return points
        trial = [[(2*p[0]*scale+width)//(2*width), (2*p[1]*scale+height)//(2*height)] for p in points]
        try:
            if signs(trial) == target:
                return normalize(trial)
        except ValueError:
            continue
    if max(width, height) <= limit:
        return points
    raise ValueError("Cannot safely round this realization into the native coordinate range; original retained")


def pts_text(points):
    return str(len(points))+"\n"+"".join(f"{x} {y}\n" for x, y in points)


def real_text(points):
    return "".join(f"{i} {x} {y}\n" for i, (x, y) in enumerate(points, 1))
