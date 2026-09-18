#!/usr/bin/env python3
"""Independent exact auditing for the three-arm 19-point comparison.

API: audit(real_path, target_path, config) -> JSON-serializable dictionary.
Required config: output_directory (fresh, or an identical cached audit).
Optional: verifier_path, cnf_path, orientation_map_path, cycles_path,
c3_verifier_path, verifier_timeout_seconds, expected_sha256={path: hash}.

Primary success is GENERAL geometric validity, not target agreement, mapped
CNF satisfaction, or exact C3 symmetry. Optional C3 reconstruction is explicitly
a SECOND, projected witness. All certificate work belongs outside native search
budgets. Freeze this module, the two verifier executables, maps and CNFs; no
search/pipeline orientation or geometry implementation is imported here.
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

ROOT = Path(__file__).resolve().parents[1]
N = 19
TRIPLES = math.comb(N, 3)
HEXAGONS = math.comb(N, 6)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(path)


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def sign(value):
    return (value > 0)-(value < 0)


def read_points(path, n=N):
    """Exact decimal/rational tokens; never pass coordinates through float."""
    rows = [line.split() for line in Path(path).read_text().splitlines() if line.strip()]
    if len(rows) != n or any(len(r) != 3 or r[0] != str(i+1) for i, r in enumerate(rows)):
        raise ValueError(f'Expected exactly {n} indexed i x y rows, in label order')
    try:
        rational = [(Fraction(r[1]), Fraction(r[2])) for r in rows]
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('Coordinates must be finite exact decimal/rational tokens') from error
    scale = math.lcm(*(v.denominator for p in rational for v in p))
    points = [(int(x*scale), int(y*scale)) for x, y in rational]
    x0, y0 = points[0]
    points = [(x-x0, y-y0) for x, y in points]
    divisor = math.gcd(*(abs(v) for p in points for v in p)) or 1
    return [(x//divisor, y//divisor) for x, y in points]


def read_target(path, n=N):
    """Return canonical sorted triples/signs; reject duplicate constraints."""
    records, seen = [], set()
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        m = re.fullmatch(r'([ABC])_\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', line.strip())
        if not m:
            raise ValueError('Malformed orientation constraint: '+line)
        triple = tuple(map(int, m.groups()[1:]))
        if len(set(triple)) != 3 or min(triple) < 1 or max(triple) > n:
            raise ValueError('Orientation index out of range or repeated')
        inversions = sum(triple[i] > triple[j] for i in range(3) for j in range(i+1, 3))
        desired = {'A': 1, 'B': -1, 'C': 0}[m[1]] * (-1 if inversions % 2 else 1)
        triple = tuple(sorted(triple))
        if triple in seen:
            raise ValueError('Duplicate orientation triple')
        seen.add(triple); records.append((triple, desired))
    if not records:
        raise ValueError('Empty orientation target')
    return records


def colex_rank(triple):
    a, b, c = triple
    return a+(b-1)*(b-2)//2+(c-1)*(c-2)*(c-3)//6


def orientation_model(points):
    model = [0]*math.comb(len(points), 3)
    for triple in itertools.combinations(range(1, len(points)+1), 3):
        rank = colex_rank(triple)
        value = sign(cross(*(points[i-1] for i in triple)))
        if not value:
            return None
        model[rank-1] = rank*value
    return model


def project_model(model, mapping_path, n=N):
    if model is None:
        return None, {'mapping_consistent': False, 'reason': 'not_general_position'}
    if mapping_path is None:
        return model, {'mapping_consistent': True, 'compressed_mapping': False}
    data = json.loads(Path(mapping_path).read_text())
    if data['n'] != n:
        raise ValueError('Mapping point count mismatch')
    expected = set(itertools.combinations(range(1, n+1), 3))
    seen, assignment, conflicts = set(), {}, []
    for row in data['entries']:
        triple, literal = tuple(row['triple']), row['literal']
        if triple not in expected or triple in seen or type(literal) is not int or literal == 0:
            raise ValueError('Invalid or duplicate mapping entry')
        seen.add(triple)
        value = sign(model[colex_rank(triple)-1])*sign(literal)
        variable = abs(literal)
        if variable in assignment and assignment[variable] != value:
            conflicts.append({'variable': variable, 'triple': list(triple)})
        assignment[variable] = value
    if seen != expected or len(assignment) != data.get('primary_variables', len(assignment)):
        raise ValueError('Incomplete orientation mapping')
    if conflicts:
        return None, {'mapping_consistent': False, 'reason': 'orbit_sign_conflict', 'conflicts': conflicts}
    return [v*assignment[v] for v in sorted(assignment)], {'mapping_consistent': True, 'compressed_mapping': True}


def cnf_check(model, cnf_path, mapping_path, directory, stem):
    projected, report = project_model(model, mapping_path)
    if projected is None:
        return dict(report, status='MAPPING_INCONSISTENT', satisfiable=False)
    if cnf_path is None:
        return dict(report, status='NOT_REQUESTED', satisfiable=None)
    # Imported only for successful geometries; failures require stdlib + verifier.
    from pysat.formula import CNF
    from pysat.solvers import Cadical195
    start = time.monotonic()
    formula = CNF(from_file=str(cnf_path))
    # PySAT's nv can be smaller than a DIMACS header with unused variables.
    # Such variables may still be legitimate orientation assumptions.
    with Path(cnf_path).open() as stream:
        header = next((line.split() for line in stream if line.split()[:1] == ['p']), None)
    if header is None or len(header) != 4 or header[:2] != ['p', 'cnf']:
        raise ValueError('Missing or malformed original CNF header')
    declared_variables, declared_clauses = map(int, header[2:])
    if declared_variables < formula.nv or declared_clauses != len(formula.clauses):
        raise ValueError('Original CNF header does not match parsed clauses')
    if any(abs(v) > declared_variables for v in projected):
        raise ValueError('Orientation variable exceeds the CNF header')
    with Cadical195(bootstrap_with=formula.clauses) as solver:
        satisfiable = solver.solve(assumptions=projected)
        report.update(status='SAT' if satisfiable else 'UNSAT', satisfiable=bool(satisfiable),
                      variables=declared_variables, clauses=len(formula.clauses), projected_variables=len(projected))
        if satisfiable:
            returned = {abs(lit): lit for lit in solver.get_model()}
            full = [returned.get(v, v) for v in range(1, declared_variables+1)]
            truth = set(full)
            bad = sum(not any(lit in truth for lit in clause) for clause in formula.clauses)
            missing = sum(lit not in truth for lit in projected)
            if bad or missing:
                raise RuntimeError('Independent full-CNF/model scan failed')
            path = directory/(stem+'.cnf.model')
            path.write_text('v '+' '.join(map(str, full))+' 0\n')
            report.update(violated_clauses=bad, wrong_orientation_assumptions=missing,
                          full_model=str(path), full_model_sha256=sha(path))
    report['seconds'] = time.monotonic()-start
    return report


def run_verifier(command, timeout):
    process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if process.returncode not in (0, 1):
        raise RuntimeError('Exact verifier failed: '+process.stderr[-2000:])
    result = json.loads(process.stdout)
    histogram = result['interior_histogram']
    if (result['n'] != N or result['six_subsets_checked'] != HEXAGONS
            or len(histogram) != N-5 or any(type(v) is not int or v < 0 for v in histogram)
            or sum(histogram) > HEXAGONS):
        raise RuntimeError('Invalid/incomplete verifier result')
    valid = not result['collinear_triples'] and not result['duplicate_pairs'] and not histogram[0] and not histogram[3]
    if bool(result['valid']) != valid or (process.returncode == 0) != valid:
        raise RuntimeError('Inconsistent verifier validity or exit status')
    return result


def audit(real_path, target_path, config):
    if config.get('n', N) != N:
        raise ValueError('This benchmark auditor is exclusively for 19 points')
    started = time.monotonic()
    real, target = Path(real_path).resolve(), Path(target_path).resolve()
    output = Path(config['output_directory']).resolve()
    verifier = Path(config.get('verifier_path', ROOT/'improvements/symmetry19/verify_hexagons')).resolve()
    c3_verifier = Path(config.get('c3_verifier_path', ROOT/'improvements/benchmarks/verify_c3')).resolve()
    optional = {key: Path(config[key]).resolve() if config.get(key) else None
                for key in ('cnf_path', 'orientation_map_path', 'cycles_path')}
    dependencies = [Path(__file__).resolve(), verifier]+[p for p in optional.values() if p]
    if optional['cycles_path']:
        dependencies.append(c3_verifier)
    dependency_hashes = {str(p): sha(p) for p in dependencies}
    for path, expected in config.get('expected_sha256', {}).items():
        if sha(path) != expected:
            raise ValueError('Frozen dependency/input hash changed: '+str(path))
    signature = {'real_sha256': sha(real), 'target_sha256': sha(target),
                 'dependencies': dependency_hashes, 'n': N, 'primary_requires_C3': False,
                 'path_roles': {key: str(p) if p else None for key, p in optional.items()}}
    certificate = output/'certificate.json'
    if certificate.exists():
        previous = json.loads(certificate.read_text())
        if previous['input_signature'] != signature:
            raise ValueError('Refusing to overwrite a certificate for different inputs/dependencies')
        for item in previous['artifacts'].values():
            if sha(item['path']) != item['sha256']:
                raise ValueError('Cached certificate artifact changed')
        return previous
    points, constraints = read_points(real), read_target(target)
    if output.exists():
        marker = output/'input_signature.json'
        if not marker.exists() or json.loads(marker.read_text()) != signature:
            raise ValueError('Refusing to overwrite an unrelated output directory')
    else:
        output.mkdir(parents=True)
    atomic_json(output/'input_signature.json', signature)
    snapshot = output/'points.real'; snapshot.write_bytes(real.read_bytes())
    saved_target = output/'target.or'; saved_target.write_bytes(target.read_bytes())
    pts = output/'points.pts'; pts.write_text(str(N)+'\n'+''.join(f'{x} {y}\n' for x, y in points))
    timeout = config.get('verifier_timeout_seconds', 120)
    geometry = run_verifier([str(verifier), str(pts)], timeout)
    collinear = sum(cross(*triple) == 0 for triple in itertools.combinations(points, 3))
    duplicates = sum(a == b for a, b in itertools.combinations(points, 2))
    if (geometry['collinear_triples'], geometry['duplicate_pairs']) != (collinear, duplicates):
        raise RuntimeError('Independent Python/C++ general-position checks disagree')
    violations = sum(sign(cross(*(points[i-1] for i in triple))) != desired for triple, desired in constraints)
    histogram = geometry['interior_histogram']
    report = {'input_signature': signature, 'source': str(real), 'n': N,
              'valid_geometry': geometry['valid'], 'accepted': geometry['valid'],
              'primary_requires_C3': False, 'geometry': geometry,
              'orientation_violations': violations, 'constraint_count': len(constraints),
              'general_position': not collinear and not duplicates,
              'forbidden_hexagons': histogram[0]+histogram[3],
              'empty_hexagons': histogram[0], 'hexagons_with_three_inside': histogram[3],
              'integer_points': str(pts), 'integer_coordinates': [[str(x), str(y)] for x, y in points],
              'numeric_cnf': {'status': 'NOT_CHECKED_GEOMETRY_INVALID', 'satisfiable': None}}
    if geometry['valid']:
        report['numeric_cnf'] = cnf_check(orientation_model(points), optional['cnf_path'],
                                           optional['orientation_map_path'], output, 'numeric')
    report['exact_C3_projection'] = {'requested': False, 'primary_outcome_unchanged': True}
    if optional['cycles_path']:
        symbolic = output/'projected_c3.qsqrt3'
        projected = run_verifier([str(c3_verifier), '--input', str(pts), '--cycles', str(optional['cycles_path']),
                                  '--output', str(symbolic)], timeout)
        c3 = {'requested': True, 'primary_outcome_unchanged': True,
              'note': 'Exact rotations reconstructed from orbit representatives: a separate witness, not exact symmetry of the input decimals.',
              'geometry': projected, 'valid_geometry': projected['valid'], 'points': str(symbolic),
              'signs_preserved': projected['orientation_changes_from_rounded_input'] == 0,
              'numeric_cnf': {'status': 'NOT_CHECKED_GEOMETRY_INVALID', 'satisfiable': None}}
        if projected['valid']:
            projected_model = [0]*TRIPLES
            for triple, value in read_target(str(symbolic)+'.or'):
                rank = colex_rank(triple); projected_model[rank-1] = rank*value
            if len(read_target(str(symbolic)+'.or')) != TRIPLES or not all(projected_model):
                raise RuntimeError('Projected exact witness has incomplete orientations')
            c3['numeric_cnf'] = cnf_check(projected_model, optional['cnf_path'], optional['orientation_map_path'], output, 'projected_c3')
        report['exact_C3_projection'] = c3
    report['artifacts'] = {p.name: {'path': str(p), 'sha256': sha(p)} for p in output.iterdir()
                           if p.is_file() and p.name not in ('certificate.json', 'input_signature.json')}
    report.update(certificate=str(certificate), audit_wall_seconds=time.monotonic()-started)
    atomic_json(certificate, report)
    return report


def summarize_checkpoints(records):
    """Chronological checkpoints: final is primary; any saved is secondary."""
    good = [r for r in records if r['valid_geometry']]
    gp = [r['forbidden_hexagons'] for r in records if r['general_position']]
    final = bool(records and records[-1]['valid_geometry'])
    return {'saved_checkpoints': len(records), 'valid_geometry': final,
            'final_valid_geometry': final, 'any_saved_valid_geometry': bool(good),
            'valid_checkpoints': len(good), 'minimum_forbidden_hexagons_in_GP': min(gp) if gp else None,
            'first_valid_certificate': good[0]['certificate'] if good else None,
            'exact_C3_projection_successes': sum(r['exact_C3_projection'].get('valid_geometry', False) for r in records),
            'audit_wall_seconds': sum(r['audit_wall_seconds'] for r in records)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--real', required=True); p.add_argument('--target', required=True)
    p.add_argument('--config', required=True)
    args = p.parse_args()
    result = audit(args.real, args.target, json.loads(Path(args.config).read_text()))
    print(json.dumps(result, indent=2))
    return 0 if result['valid_geometry'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
