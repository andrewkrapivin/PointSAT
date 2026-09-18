#!/usr/bin/env python3
"""One prespecified cold-start calibration pair; excluded from prospective data."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import compare19
from benchmarks.compare19_types import parse_orientations
from improvements.pipeline.orientation_map import OrientationMap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu', type=int, default=1)
    args = parser.parse_args()
    if args.cpu not in os.sched_getaffinity(0):
        parser.error('Requested CPU is outside the inherited affinity')
    os.sched_setaffinity(0, {args.cpu})
    begin = time.monotonic()
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    deadline = begin+297  # Leave three seconds for process-group cleanup and the final record.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(sig, lambda *unused: compare19.STOP.set())
    signal.setitimer(signal.ITIMER_REAL, 297)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    frozen = output/'frozen'
    frozen.mkdir()
    source_paths = {
        'original': ROOT/'improvements/localizer/localizer_baseline',
        'improved': ROOT/'improvements/localizer/localizer_v4',
        'verifier': ROOT/'improvements/symmetry19/verify_hexagons',
        'c3_verifier': ROOT/'improvements/benchmarks/verify_c3',
        'mapping': ROOT/'improvements/symmetry19/variants/mapping.json',
        'cycles': ROOT/'improvements/symmetry19/decoded/center19-adjacent.cycles',
        'fixed': ROOT/'improvements/symmetry19/decoded/center19-adjacent.fixed',
    }
    paths = {}
    for key, path in source_paths.items():
        destination = frozen/key
        shutil.copy2(path, destination)
        paths[key] = str(destination)
    sources = [ROOT/'benchmarks/compare19.py', ROOT/'benchmarks/compare19_audit.py',
               ROOT/'benchmarks/compare19_types.py', ROOT/'flippable2.py',
               ROOT/'sat_orient_conversion.py', ROOT/'improvements/pipeline/orientation_map.py',
               Path(__file__).resolve()]
    for path in sources:
        shutil.copy2(path, frozen/path.name)
    known = ROOT/'improvements/success19/witness.or'
    text = known.read_text()
    n, signs = parse_orientations(text)
    if n != 19:
        raise ValueError('Expected the known 19-point orientation control')
    full_colex = [0]*969
    for (a, b, c), sign in signs.items():
        rank = a+(b-1)*(b-2)//2+(c-1)*(c-2)*(c-3)//6
        full_colex[rank-1] = rank*sign
    adapter = OrientationMap(paths['mapping'], 19)
    primary, conflicts = adapter.project(full_colex)
    if conflicts or primary is None or len(primary) != 327:
        raise ValueError('Known exact witness does not consistently project to 327 variables')
    if parse_orientations(adapter.orientations(primary))[1] != signs:
        raise ValueError('Signed-map roundtrip failed')
    (output/'known-full.or').write_text(text)
    cnf = ROOT/'convex_hexagon_inside_19_3sym.cnf'
    case = {'id': 0, 'seed': 190907, 'primary_model': primary}
    config = {'paths': paths, 'cases': [case], 'cnf': str(cnf), 'cnf_sha256': compare19.sha(cnf),
              'python': str(ROOT/'direct/vendor/venv/bin/python'), 'native_save_grace': .75,
              'native_seconds': 30, 'seed': 190907, 'cpu_affinity': [args.cpu],
              'control': 'Known realizable orientation only; no coordinates read or passed to native search.',
              'excluded_from_prospective_corpus': True,
              'known_orientation_source': str(known), 'known_orientation_sha256': compare19.sha(known),
              'original_source_paths': {key: str(path) for key, path in source_paths.items()},
              'frozen_sha256': {p.name: compare19.sha(p) for p in frozen.iterdir()},
              'python_version': sys.version,
              'native_budget_seconds_per_arm': 30, 'hard_total_cap_seconds': 300,
              'prespecified_arms': ['original', 'improved_fixed'],
              'prespecified_order': 'original then improved_fixed',
              'coordinate_seeds': False, 'feedback': False, 'archive': False,
              'interpretation': 'Single known-positive calibration; not a prospective success-rate estimate or tuning dataset.'}
    registration = output/'registration.json'
    compare19.atomic(registration, config)
    result = {'status': 'RUNNING', 'registration': str(registration),
              'excluded_from_prospective_corpus': True, 'arms': {}, 'phases': []}

    def persist():
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        result.update(total_wall_seconds=time.monotonic()-begin,
                      child_cpu_seconds=after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime)
        compare19.atomic(output/'result.json', result)

    def phase(arm, work, cap, budget=0):
        if compare19.STOP.is_set() or time.monotonic() >= deadline:
            raise TimeoutError('Positive-control total deadline or external stop')
        report = compare19.isolated(config, registration, case, arm, work,
                                    min(cap, deadline-time.monotonic()), budget)
        result['phases'].append({'arm': arm, 'workspace': str(work),
                                 'status': report['status'], 'wall_seconds': report['parent_wall_seconds'],
                                 'cpu_seconds': report['parent_cpu_seconds'],
                                 'watchdog': report['overhead_watchdog']})
        persist()
        return report

    persist()
    try:
        preparation = output/'preparation'
        preparation.mkdir()
        prepared = phase('prepare', preparation, 100)
        result['preparation'] = prepared
        if prepared['status'] != 'PREPARED':
            raise RuntimeError('Common original-CNF flippability preprocessing did not finish')
        initial = adapter.orientations(prepared['partial_model'])
        (output/'common-initial.or').write_text(initial)
        result['common_constraints'] = len(initial.splitlines())
        result['common_flippable_primary_variables'] = len(prepared['flippables'])
        for arm in config['prespecified_arms']:
            work = output/arm
            work.mkdir()
            (work/'initial.or').write_text(initial)
            (work/'full.or').write_text(text)
            search = phase(arm, work, 34, 30)
            compare19.atomic(work/'search-result.json', search)
            result['arms'][arm] = {'search': search}
            persist()
            audited = phase('audit', work, 60)
            checks = audited.get('audits', [])
            final = next((check for check in checks if check['checkpoint'] == 'stage0.real'), {})
            result['arms'][arm].update(audit=audited, valid_geometry=bool(final.get('valid_geometry')),
                                      forbidden_hexagons=final.get('forbidden_hexagons'),
                                      target_orientation_violations=final.get('orientation_violations'),
                                      exact_C3_projection_valid=final.get('exact_C3_projection', {}).get('valid_geometry'))
            persist()
            print(json.dumps({'arm': arm, 'valid_geometry': result['arms'][arm]['valid_geometry'],
                              'forbidden_hexagons': result['arms'][arm]['forbidden_hexagons'],
                              'target_orientation_violations': result['arms'][arm]['target_orientation_violations']}), flush=True)
        result['status'] = 'FINISHED'
    except BaseException as error:
        result.update(status='ERROR', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        persist()
    print(json.dumps({'status': result['status'], 'total_wall_seconds': result['total_wall_seconds'],
                      'child_cpu_seconds': result['child_cpu_seconds'], 'result': str(output/'result.json')}), flush=True)


if __name__ == '__main__':
    main()
