#!/usr/bin/env python3
"""Deadline-charged exact online acceptance, without CNF or symmetry checks.

API: audit(real_path, family, config) -> JSON-serializable result.
Required config: output_directory (NEW), verifier_path (frozen exact binary),
deadline_monotonic (the WORKER'S absolute overall wall deadline).
Optional config: expected_verifier_sha256. Caller must impose its own process-
group watchdog too. Acceptance time is measured only after the exact certificate
and integer witness have been committed; late-valid candidates never count.

Supported families: symmetry19, mixed23, holes29, gons32, caps26. The 19-point
primary is unrestricted GP geometry with no convex hexagon having 0 or 3 inside.
Caps use strictly increasing x within each counted cap, exactly as in the
earlier checker; repeated x coordinates are reported, not separately rejected.
No relabeling, projection, rounding, C3 reconstruction or SAT feedback occurs.
"""
import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import subprocess
import time

FAMILIES = {'symmetry19': (19, 0, 0, 0), 'mixed23': (23, 7, 6, 0),
            'holes29': (29, 0, 6, 0), 'gons32': (32, 7, 0, 0), 'caps26': (26, 7, 0, 5)}


class DeadlineExceeded(Exception):
    pass


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer_points(data, n):
    """Read one captured byte snapshot, using exact rational arithmetic only."""
    if len(data) > 262144:
        raise ValueError('Coordinate snapshot exceeds 256 KiB')
    rows = [line.split() for line in data.decode('ascii').splitlines() if line.strip()]
    if rows and rows[0] == [str(n)] and len(rows) == n+1 and all(len(r) == 2 for r in rows[1:]):
        tokens = rows[1:]
    elif len(rows) == n and all(len(r) == 3 and r[0] == str(i+1) for i, r in enumerate(rows)):
        tokens = [r[1:] for r in rows]
    else:
        raise ValueError(f'Expected exactly {n} indexed i x y rows or n followed by coordinate pairs')
    for pair in tokens:
        for token in pair:
            if len(token) > 512:
                raise ValueError('Coordinate token too long')
            exponent = re.search(r'[eE]([+-]?\d+)$', token)
            if exponent and abs(int(exponent[1])) > 1024:
                raise ValueError('Coordinate exponent exceeds bounded parser limit')
    rational = [(Fraction(x), Fraction(y)) for x, y in tokens]
    scale = math.lcm(*(value.denominator for point in rational for value in point))
    points = [(int(x*scale), int(y*scale)) for x, y in rational]
    x0, y0 = points[0]; points = [(x-x0, y-y0) for x, y in points]
    divisor = math.gcd(*(abs(v) for p in points for v in p)) or 1
    points = [(x//divisor, y//divisor) for x, y in points]
    if any(abs(v).bit_length() > 12000 for point in points for v in point):
        raise ValueError('Normalized integer coordinate exceeds bounded parser limit')
    return points


def count_caps(points, k=5, guard=lambda: None):
    """Exact x-monotone concave-chain DP, independent of the native search."""
    points = sorted(points); n = len(points)
    previous = [[int(i < j and points[i][0] < points[j][0]) for j in range(n)] for i in range(n)]
    for _length in range(3, k+1):
        current = [[0]*n for _ in range(n)]
        for j in range(n):
            guard()
            for i in range(j):
                if not previous[i][j]:
                    continue
                for v in range(j+1, n):
                    if points[j][0] < points[v][0] and cross(points[i], points[j], points[v]) < 0:
                        current[j][v] += previous[i][j]
        previous = current
    return sum(map(sum, previous))


def _count(value, maximum=None):
    return (isinstance(value, int) and not isinstance(value, bool) and value >= 0
            and (maximum is None or value <= maximum))


def validate_output(geometry, family, collinear, duplicates):
    """Check predicate claims and exhaustive coverage, not merely valid=true."""
    n, gon, hole, _cap = FAMILIES[family]
    if geometry.get('n') != n or geometry.get('collinear_triples') != collinear:
        raise ValueError('Independent n/GP checks disagree with verifier')
    if not isinstance(geometry.get('valid'), bool):
        raise ValueError('Verifier validity is not Boolean')
    if family == 'symmetry19':
        histogram = geometry.get('interior_histogram')
        checked = math.comb(n, 6)
        if (geometry.get('six_subsets_checked') != checked or geometry.get('duplicate_pairs') != duplicates
                or not isinstance(histogram, list) or len(histogram) != n-5
                or any(not _count(v, checked) for v in histogram) or sum(histogram) > checked):
            raise ValueError('Incomplete or malformed exact hexagon enumeration')
        forbidden = histogram[0]+histogram[3]
    else:
        if geometry.get('gon') != gon or geometry.get('hole') != hole:
            raise ValueError('Verifier used different polygon parameters')
        for size, count_key, checked_key in ((gon, 'convex_gons', 'gon_subsets_checked'),
                                             (hole, 'empty_holes', 'hole_subsets_checked')):
            expected = math.comb(n, size) if size else 0
            if geometry.get(checked_key) != expected or not _count(geometry.get(count_key), expected):
                raise ValueError('Incomplete or malformed exact polygon enumeration')
        forbidden = geometry['convex_gons']+geometry['empty_holes']
    if geometry['valid'] != (not collinear and not duplicates and forbidden == 0):
        raise ValueError('Verifier validity contradicts exact counts')
    return forbidden


def audit(real_path, family, config):
    start = time.monotonic()
    deadline = config['deadline_monotonic']
    if not isinstance(deadline, (int, float)) or isinstance(deadline, bool) or not math.isfinite(deadline):
        raise ValueError('An absolute finite deadline_monotonic is required')
    if family not in FAMILIES:
        raise ValueError('Unknown family: '+str(family))
    result = {'family': family, 'accepted': False, 'valid_geometry': None,
              'accepted_timestamp_monotonic': None, 'started_monotonic': start,
              'deadline_monotonic': deadline, 'status': 'STARTED',
              'primary_requires_CNF': False, 'primary_requires_C3': False}
    def guard():
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise DeadlineExceeded('Overall worker wall deadline reached')
        return remaining
    try:
        guard()
        n, gon, hole, cap = FAMILIES[family]
        data = Path(real_path).read_bytes()
        points = integer_points(data, n); guard()
        directory = Path(config['output_directory']).resolve()
        directory.mkdir(parents=True, exist_ok=False)
        source = directory/'snapshot.real'; source.write_bytes(data)
        integer_file = directory/'points.pts'
        integer_data = (str(n)+'\n'+''.join(f'{x} {y}\n' for x, y in points)).encode()
        integer_file.write_bytes(integer_data)
        result.update(snapshot=str(source), snapshot_sha256=digest(data), integer_points=str(integer_file),
                      integer_points_sha256=digest(integer_data), n=n)
        duplicates = sum(a == b for a, b in itertools.combinations(points, 2)); collinear = 0
        for index, triple in enumerate(itertools.combinations(points, 3)):
            collinear += cross(*triple) == 0
            if index % 256 == 0:
                guard()
        x_ties = sum(a[0] == b[0] for a, b in itertools.combinations(points, 2)) if cap else 0
        result.update(general_position=not duplicates and not collinear,
                      duplicate_pairs=duplicates, collinear_triples=collinear, cap_x_ties=x_ties)
        if duplicates or collinear:
            result.update(status='INVALID', valid_geometry=False,
                          rejection='not_general_position')
            return result
        caps = count_caps(points, cap, guard) if cap else 0
        result['convex_caps'] = caps
        if caps:
            result.update(status='INVALID', valid_geometry=False, rejection='convex_5_cap')
            return result
        verifier = Path(config['verifier_path']).resolve(); verifier_sha = digest(verifier.read_bytes())
        if config.get('expected_verifier_sha256') and verifier_sha != config['expected_verifier_sha256']:
            raise ValueError('Frozen exact-verifier hash mismatch')
        command = [str(verifier), str(integer_file)] if family == 'symmetry19' else [
            str(verifier), '--input', str(integer_file), '--gon', str(gon), '--hole', str(hole)]
        result.update(verifier=str(verifier), verifier_sha256=verifier_sha, verifier_command=command)
        child = None; launched = time.monotonic()
        try:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = child.communicate(timeout=guard())
        except subprocess.TimeoutExpired as error:
            raise DeadlineExceeded('Exact verification exceeded the overall worker wall deadline') from error
        finally:
            if child is not None and child.poll() is None:
                child.kill(); child.communicate()
        result['verifier_wall_seconds'] = time.monotonic()-launched
        guard()
        if child.returncode not in (0, 1):
            raise ValueError('Exact verifier failed: '+stderr.decode(errors='replace')[:1000])
        geometry = json.loads(stdout)
        forbidden = validate_output(geometry, family, collinear, duplicates)
        if child.returncode != (0 if geometry['valid'] else 1):
            raise ValueError('Verifier return code contradicts its validity claim')
        result.update(geometry=geometry, forbidden_polygons=forbidden+caps,
                      valid_geometry=geometry['valid'] and not caps, status='VALID' if geometry['valid'] else 'INVALID')
        guard()
        # The certificate contains the exact verified snapshot and claims, not
        # an early timestamp that could retroactively count a late verification.
        certificate = directory/'certificate.json'
        proof = dict(result, certificate_validated_monotonic=time.monotonic(),
                     timing_note='This is a geometric certificate, not an online acceptance timestamp.')
        proof.pop('accepted'); proof.pop('accepted_timestamp_monotonic')
        temporary = certificate.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(proof, indent=2, allow_nan=False)+'\n'); temporary.replace(certificate)
        proof_bytes = certificate.read_bytes()
        if json.loads(proof_bytes) != proof or integer_file.read_bytes() != integer_data:
            raise ValueError('Saved certificate/witness readback differs from verified data')
        result.update(certificate=str(certificate), certificate_sha256=digest(proof_bytes))
        ready = time.monotonic()
        if ready > deadline:
            result.update(status='DEADLINE_EXCEEDED', rejection='Certificate completed after overall deadline')
        elif result['valid_geometry']:
            result.update(accepted=True, accepted_timestamp_monotonic=ready)
        return result
    except DeadlineExceeded as error:
        result.update(status='DEADLINE_EXCEEDED', error=str(error)); return result
    except (OSError, ValueError, ZeroDivisionError, UnicodeError) as error:
        result.update(status='CHECK_ERROR', error=f'{type(error).__name__}: {error}'); return result
    finally:
        result['finished_monotonic'] = time.monotonic()
        result['check_wall_seconds'] = result['finished_monotonic']-start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real', required=True)
    parser.add_argument('--family', choices=FAMILIES, required=True)
    parser.add_argument('--verifier', required=True)
    parser.add_argument('--verifier-sha256')
    parser.add_argument('--deadline-monotonic', type=float, required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = audit(args.real, args.family, {'verifier_path': args.verifier,
        'expected_verifier_sha256': args.verifier_sha256, 'deadline_monotonic': args.deadline_monotonic,
        'output_directory': args.out})
    print(json.dumps(result, allow_nan=False))
    return 0 if result['status'] != 'CHECK_ERROR' else 1


if __name__ == '__main__':
    raise SystemExit(main())
