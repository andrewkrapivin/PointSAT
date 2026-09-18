"""Exact colexicographic orientation conversion and certificate validation.

Interpret the printed decimals exactly. Predicates use a shared integer scale
instead of allocating Fraction objects for every orientation determinant.
"""
import math
import re
from fractions import Fraction
from functools import cmp_to_key
from pathlib import Path


def C2(k):
    return k * (k - 1) // 2 if k >= 2 else 0


def C3(k):
    return k * (k - 1) * (k - 2) // 6 if k >= 3 else 0


def invert_rank(m, n):
    if not 1 <= m <= C3(n):
        raise ValueError(f"orientation variable {m} outside 1..{C3(n)}")
    lo, hi = 3, n
    while lo < hi:
        mid = (lo + hi) // 2
        if C3(mid) >= m:
            hi = mid
        else:
            lo = mid + 1
    c = lo
    r = m - C3(c - 1)
    lo, hi = 2, c - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if C2(mid) >= r:
            hi = mid
        else:
            lo = mid + 1
    return r - C2(lo - 1), lo, c


def split_line(sol):
    return [int(x) for x in re.findall(r'-?\d+', sol)]


def get_orientations(sol, n=23):
    return ''.join(f"{'A' if lit > 0 else 'B'}_{invert_rank(abs(lit), n)}\n"
                   for lit in sol if lit)


_CONSTRAINT = re.compile(r'([AB])_?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')


def parse_constraints(filename):
    constraints = []
    with open(filename, encoding='utf-8') as file:
        for number, line in enumerate(file, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = _CONSTRAINT.fullmatch(line)
            if not match:
                raise ValueError(f"{filename}:{number}: invalid orientation constraint")
            indices = tuple(map(int, match.groups()[1:]))
            if min(indices) < 1 or len(set(indices)) != 3:
                raise ValueError(f"{filename}:{number}: expected distinct positive indices")
            constraints.append((1 if match[1] == 'A' else -1, indices))
    return constraints


def _read_points(filename):
    indexed = {}
    with open(filename, encoding='utf-8') as file:
        for number, line in enumerate(file, 1):
            fields = line.split()
            if not fields or fields[0].startswith('#'):
                continue
            if len(fields) != 3:
                raise ValueError(f"{filename}:{number}: expected index x y")
            try:
                index = int(fields[0])
                point = (Fraction(fields[1]), Fraction(fields[2]))
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError(f"{filename}:{number}: invalid exact coordinate") from error
            if index < 1 or index in indexed:
                raise ValueError(f"{filename}:{number}: duplicate or invalid point index")
            indexed[index] = point
    if not indexed or set(indexed) != set(range(1, len(indexed) + 1)):
        raise ValueError(f"{filename}: point indices must be exactly 1..n")
    return [indexed[index] for index in range(1, len(indexed) + 1)]


def parse_points(filename):
    points = _read_points(filename)
    return points, [(float(x), float(y)) for x, y in points]


def integer_points(filename):
    points = _read_points(filename)
    scale = math.lcm(*(value.denominator for point in points for value in point))
    return [(x.numerator * (scale // x.denominator),
             y.numerator * (scale // y.denominator)) for x, y in points]


def det(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (c[0] - a[0]) * (b[1] - a[1])


def validate_constraint(sign, a, b, c):
    return sign * det(a, b, c) > 0


def orient(a, b, c):
    a, b, c = sorted((a, b, c))
    if a < 1 or a == b or b == c:
        raise ValueError("orientation requires distinct positive indices")
    return a + C2(b - 1) + C3(c - 1)


def _violations(constraints, points):
    bad_vars = []
    for sign, indices in constraints:
        if max(indices) > len(points):
            raise ValueError("orientation references a missing point")
        a, b, c = (points[index - 1] for index in indices)
        if sign * det(a, b, c) <= 0:
            bad_vars.append(orient(*indices))
    return bad_vars


def _model(points, n):
    if len(points) != n:
        raise ValueError(f"expected {n} points, got {len(points)}")
    model = []
    for k in range(2, n):
        for j in range(1, k):
            for i in range(j):
                determinant = det(points[i], points[j], points[k])
                if determinant == 0:
                    raise ValueError(f"points {i+1}, {j+1}, {k+1} are collinear")
                variable = len(model) + 1
                model.append(variable if determinant > 0 else -variable)
    return model


def validate(constraint_filename, point_filename):
    bad_vars = _violations(parse_constraints(constraint_filename), integer_points(point_filename))
    return not bad_vars, bad_vars


def get_sat_model(point_filename, n):
    return _model(integer_points(point_filename), n)


def inspect_realization(constraint_filename, point_filename, n):
    """Parse once, returning constraint validation and a complete SAT projection.

    Degenerate coordinates have sat_model=None and general_position=False.
    Malformed files or missing points raise ValueError.
    """
    points = integer_points(point_filename)
    if len(points) != n:
        raise ValueError(f"expected {n} points, got {len(points)}")
    bad_vars = _violations(parse_constraints(constraint_filename), points)
    try:
        model = _model(points, n)
    except ValueError:
        model = None
    return {'valid': not bad_vars and model is not None, 'bad_vars': bad_vars,
            'sat_model': model, 'general_position': model is not None,
            'point_count': len(points)}


def radial_relabel(point_filename, output_filename, n):
    """Put an extreme point first and the others in CCW radial order.

    This changes labels, not coordinates. It is appropriate only for problems
    invariant under relabeling, and is NOT a replacement for a full CNF check.
    The saved decimal tokens are copied verbatim. Returned permutation maps
    each new 1-based index to its original 1-based index.
    """
    points = integer_points(point_filename)
    _model(points, n)  # Explicitly require all points and general position.
    anchor = min(range(n), key=lambda index: points[index])

    def compare(i, j):
        determinant = det(points[anchor], points[i], points[j])
        if determinant == 0:
            raise ValueError('radial ordering requires general position')
        return -1 if determinant > 0 else 1

    order = [anchor] + sorted((i for i in range(n) if i != anchor), key=cmp_to_key(compare))
    model = _model([points[i] for i in order], n)
    tokens = {}
    with open(point_filename, encoding='utf-8') as file:
        for line in file:
            fields = line.split()
            if fields and not fields[0].startswith('#'):
                tokens[int(fields[0])] = fields[1:]
    output = ''.join(f'{new} {tokens[old+1][0]} {tokens[old+1][1]}\n'
                     for new, old in enumerate(order, 1))
    Path(output_filename).write_text(output, encoding='utf-8')
    return {'permutation': [i+1 for i in order], 'sat_model': model,
            'point_count': n, 'relabeling': 'lexicographic_extreme_then_ccw'}


def count_caps(point_filename, k=5):
    """Count strict x-monotone convex upper k-chains using exact arithmetic.

    Caps are coordinate-dependent: a SAT order-type certificate alone does not
    certify them when the realization changed the intended x order.
    """
    if k < 3:
        raise ValueError('cap size must be at least three')
    points = sorted(integer_points(point_filename))
    n = len(points)
    if k > n:
        return 0
    previous = [[int(i < j and points[i][0] < points[j][0]) for j in range(n)]
                for i in range(n)]
    for size in range(3, k+1):
        current = [[0]*n for _ in range(n)]
        for i in range(1, n):
            for j in range(i+1, n):
                if points[i][0] >= points[j][0]:
                    continue
                current[i][j] = sum(previous[h][i] for h in range(i)
                                    if previous[h][i] and det(points[h], points[i], points[j]) < 0)
        previous = current
    return sum(map(sum, previous))
