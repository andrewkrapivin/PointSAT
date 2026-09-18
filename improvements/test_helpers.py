"""Differential tests and paired benchmarks for PointSAT's exact helpers."""
import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flippable2 import FlippabilityChecker
from sat_orient_conversion import (C3, det, get_orientations, get_sat_model,
                                  inspect_realization, invert_rank, orient,
                                  parse_constraints, parse_points, radial_relabel, count_caps)
from pysat.solvers import Cadical195


def reference_flips(clauses, model):
    answer = set()
    with Cadical195(bootstrap_with=clauses) as solver:
        for i, literal in enumerate(model):
            trial = list(model)
            trial[i] = -literal
            if solver.solve(assumptions=trial):
                answer.add(abs(literal))
    return answer


def tests():
    rng = random.Random(51029)
    checks = 0
    for n in range(3, 41):
        for variable in range(1, C3(n) + 1):
            assert orient(*invert_rank(variable, n)) == variable
            checks += 1
    for trial in range(250):
        n = rng.randrange(2, 14)
        planted = [i if rng.randrange(2) else -i for i in range(1, n+1)]
        clauses = []
        for _ in range(rng.randrange(1, 45)):
            clause = [rng.choice((-1, 1))*rng.randrange(1, n+1)
                      for _ in range(rng.randrange(1, 6))]
            if not any(lit in planted for lit in clause):
                clause.append(rng.choice(planted))
            clauses.append(clause)
        formula = f'p cnf {n} {len(clauses)}\n' + ''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
        with FlippabilityChecker(formula) as checker:
            for _ in range(3):
                projection = rng.sample(planted, rng.randrange(1, n+1))
                actual, nonflips = checker.check('v '+' '.join(map(str, projection))+' 0')
                expected = reference_flips(clauses, projection)
                assert actual == expected, (clauses, projection, expected, actual)
                assert nonflips == [lit for lit in projection if abs(lit) not in expected]
                checks += 1
    with tempfile.TemporaryDirectory(prefix='pointsat-helper-test-') as temp:
        points = Path(temp)/'points.real'
        constraints = Path(temp)/'orientations.or'
        for n in (3, 19, 23, 26, 29, 32):
            points.write_text(''.join(f'{i+1}\t{rng.randrange(-100000,100000)/1000:.3f} {rng.randrange(-100000,100000)/1000:.3f}\n' for i in range(n)))
            exact, _ = parse_points(points)
            model = get_sat_model(points, n)
            for i,j,k in itertools.combinations(range(n), 3):
                variable = orient(i+1,j+1,k+1)
                assert (model[variable-1] > 0) == (det(exact[i],exact[j],exact[k]) > 0)
                checks += 1
            constraints.write_text(get_orientations(model, n))
            assert inspect_realization(constraints, points, n)['valid']
            radial = Path(temp)/'radial.real'
            result = radial_relabel(points, radial, n)
            assert sorted(result['permutation']) == list(range(1,n+1))
            after, _ = parse_points(radial)
            assert after == [exact[i-1] for i in result['permutation']]
            assert all(result['sat_model'][orient(1,j,k)-1] > 0
                       for j in range(2,n+1) for k in range(j+1,n+1))
            if n <= 19:
                for cap in (3, 5):
                    expected = sum(all(s[i][0] < s[i+1][0] for i in range(cap-1)) and
                                   all(det(s[i],s[i+1],s[i+2]) < 0 for i in range(cap-2))
                                   for s in itertools.combinations(sorted(exact),cap))
                    assert count_caps(points, cap) == expected
        # Exact decimal identity differs from binary64 in this deliberately tiny gap.
        points.write_text('1 0 0\n2 1 1\n3 2 2.00000000000000000000000000000000000001\n')
        assert get_sat_model(points, 3) == [1]
        constraints.write_text('A_(1, 2, 3)\n')
        assert inspect_realization(constraints, points, 3)['valid']
        points.write_text('1 0 0\n2 1 1\n3 2 2\n')
        assert not inspect_realization(constraints, points, 3)['general_position']
        for bad in ('A_(__import__("os").getcwd())', 'C_(1,2,3)', 'A_(0,2,3)', 'A_(1,1,2)'):
            constraints.write_text(bad+'\n')
            try:
                parse_constraints(constraints)
            except ValueError:
                pass
            else:
                raise AssertionError(bad)
    print(json.dumps({'status':'passed', 'checks':checks, 'flippability_instances':750}))


def benchmark(output):
    import subprocess
    old_source = subprocess.run(['git','show','HEAD:flippable2.py'], cwd=ROOT,
                                check=True, text=True, capture_output=True).stdout
    old_namespace = {}
    exec(compile(old_source, 'baseline_flippable2.py', 'exec'), old_namespace)
    formula = (ROOT/'7gon-6hole-23-compact.cnf').read_text()
    records = [json.loads(line) for line in (ROOT/'direct/baseline/with_flippable/raw_results.jsonl').read_text().splitlines()]
    samples = [row for row in records if row['type']=='SAT' and row.get('satisfiable')][:5]
    results = []
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    checker = FlippabilityChecker(formula)
    setup = {'wall':time.perf_counter()-start_wall, 'cpu':time.process_time()-start_cpu}
    for row in samples:
        model = row['original_solution']
        start_wall, start_cpu = time.perf_counter(), time.process_time()
        expected = old_namespace['check_flippable'](formula, model)
        old = {'wall':time.perf_counter()-start_wall, 'cpu':time.process_time()-start_cpu}
        start_wall, start_cpu = time.perf_counter(), time.process_time()
        actual = checker.check(model)
        new = {'wall':time.perf_counter()-start_wall, 'cpu':time.process_time()-start_cpu}
        assert actual == expected
        result = {'id':row['id'], 'baseline':old, 'improved':new,
                  'flippables':len(actual[0]), 'stats':checker.last_stats}
        results.append(result)
        print(json.dumps(result), flush=True)
    checker.close()
    Path(output).write_text(json.dumps({'setup':setup, 'samples':results}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark')
    args = parser.parse_args()
    tests()
    if args.benchmark:
        benchmark(args.benchmark)
