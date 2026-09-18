#!/usr/bin/env python3
"""Frozen original/fixed-target/feedback comparison on diverse 19-point targets.

Native budgets are equal; SAT/preparation/audit overhead is measured separately.
Only two single-core slots are used, including verification and preprocessing.
"""
import argparse
import ast
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import resource
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
STOP = threading.Event()
LOCK = threading.Lock()
ARMS = ('original', 'improved_fixed', 'improved_feedback')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def register(args):
    if args.targets < 1 or not args.budgets or any(not 0 < budget <= 3600 for budget in args.budgets) or len(set(args.budgets)) != len(args.budgets):
        raise ValueError('Need positive target count and distinct native budgets in (0,3600]')
    inputs = module(ROOT/'benchmarks/compare19_inputs.py', 'compare19_inputs')
    models = list(inputs.load_models(Path(args.corpus)))
    if len(models) < args.targets:
        raise ValueError(f'Expected at least {args.targets} frozen targets; found {len(models)}')
    models = models[:args.targets]
    if any(not row.get('validation', {}).get('valid') for row in models):
        raise ValueError('Every target needs a checked original-CNF extension')
    canonical = [row.get('canonicalization', {}) for row in models]
    if any(not item.get('supported') for item in canonical) or len({item.get('canonical_signs') for item in canonical}) != len(models):
        raise ValueError('Targets must be independently established distinct order types')
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out/'frozen'
    frozen.mkdir()
    corpus_path = Path(args.corpus).resolve()
    corpus_manifest = (corpus_path if corpus_path.is_dir() else corpus_path.parent)/'manifest.json'
    if corpus_manifest.is_file():
        shutil.copy2(corpus_manifest, frozen/'corpus-manifest.json')
    paths = {
        'original': ROOT/'improvements/localizer/localizer_baseline',
        'improved': ROOT/'improvements/localizer/localizer_v4',
        'verifier': ROOT/'improvements/symmetry19/verify_hexagons',
        'c3_verifier': ROOT/'improvements/benchmarks/verify_c3',
        'mapping': ROOT/'improvements/symmetry19/variants/mapping.json',
        'cycles': ROOT/'improvements/symmetry19/decoded/center19-adjacent.cycles',
        'fixed': ROOT/'improvements/symmetry19/decoded/center19-adjacent.fixed',
    }
    for name, path in paths.items():
        target = frozen/(name+path.suffix if name in ('mapping', 'cycles', 'fixed') else name)
        shutil.copy2(path, target)
        paths[name] = target
    for source, target in (
        (Path(__file__), 'compare19.py'),
        (ROOT/'benchmarks/compare19_audit.py', 'compare19_audit.py'),
        (ROOT/'flippable2.py', 'flippable2.py'),
        (ROOT/'sat_orient_conversion.py', 'sat_orient_conversion.py'),
        (ROOT/'improvements/pipeline/orientation_map.py', 'orientation_map.py')):
        shutil.copy2(source, frozen/target)
    source = (ROOT/'improvements/pipeline/runner.py').read_text()
    functions = [ast.get_source_segment(source, node) for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name in ('orientation_margins', 'core_guided_feedback')]
    assert len(functions) == 2
    (frozen/'feedback.py').write_text('import time, math, hashlib\nfrom sat_orient_conversion import integer_points\n\n'+'\n\n'.join(functions)+'\n')
    rng = random.Random(args.seed)
    cases = []
    for index, row in enumerate(models):
        arms = list(ARMS)
        rng.shuffle(arms)
        experiments = [{'arm': arm, 'budget': budget} for arm in arms for budget in args.budgets]
        rng.shuffle(experiments)
        cases.append({'id': index, 'corpus_id': row['id'], 'primary_model': row['primary_model'],
                      'expanded_orientation_sha256': row['expanded_orientation_sha256'],
                      'seed': args.seed+index, 'experiments': experiments,
                      'generation': row.get('generation'), 'validation': row.get('validation'),
                      'canonical_sha256': row.get('canonicalization', {}).get('canonical_sha256')})
    rng.shuffle(cases)
    config = {
        'registered_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'root': str(ROOT), 'python': str(ROOT/'direct/vendor/venv/bin/python'),
        'corpus': str(Path(args.corpus).resolve()), 'cases': cases,
        'cnf': str(ROOT/'convex_hexagon_inside_19_3sym.cnf'),
        'cnf_sha256': sha(ROOT/'convex_hexagon_inside_19_3sym.cnf'),
        'paths': {key: str(value) for key, value in paths.items()},
        'frozen_sha256': {p.name: sha(p) for p in frozen.iterdir()},
        'budgets': args.budgets, 'prepare_seconds': 120, 'trial_overhead_cap': 90, 'audit_seconds': 120,
        'native_save_grace': .75, 'feedback_seconds': 10, 'workers_max': 2,
        'arms': list(ARMS), 'initial_flippability': True,
        'primary_endpoint': 'Exact valid geometry in final checkpoint only; target agreement and exact C3 certification are separate.',
        'secondary_endpoint': 'Any saved checkpoint has exact valid geometry.',
        'symmetry_scope': 'All arms enforce identical rotational cycles and the fixed center. Failure is not unrestricted nonrealizability.',
        'budget_scope': '10/30/60 seconds native allowance per arm from fresh starts; corpus/preparation/SAT feedback/auditing separately timed. Not equal whole-trial cost.',
        'attribution': 'Original versus improved_fixed measures the native package including line moves. Improved_feedback additionally changes target, splits the budget, and warm-restarts: a compound strategy, not a pure SAT-feedback ablation.',
        'selection': 'Frozen SAT-only corpus; see copied corpus manifest and per-case generation provenance for fresh/reused and cut-filtered strata. No coordinate seeds or realization-outcome selection. Preparation, feedback and acceptance use the original CNF without additional cuts.',
        'selected_distinct_order_types': len(models),
    }
    atomic(out/'registration.json', config)
    print(json.dumps({'registration': str(out/'registration.json'), 'targets': len(cases),
                      'trials': len(cases)*3*len(args.budgets), 'maximum_native_core_hours': len(cases)*3*sum(args.budgets)/3600}))


def native(config, arm, target, output, seed, seconds, warm=None):
    paths = config['paths']
    command = [paths['original' if arm == 'original' else 'improved'], str(target),
               '-t', '1', '-i', '10', '-r', '30000', '-s', str(seed),
               '-f', paths['fixed'], '-c', paths['cycles'], '-o', str(output)]
    if arm != 'original':
        command += ['-T', str(seconds), '--line-every', '10', '--min-radius', '0.000001', '-q']
        if warm is not None:
            command += ['-w', str(warm)]
    if any(len(part.encode()) >= 250 for part in (str(output), paths['fixed'], paths['cycles'])):
        raise ValueError('Upstream Localizer path exceeds its fixed filename buffer')
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    interrupted = killed = False
    with output.with_suffix('.stdout').open('w') as stdout, output.with_suffix('.stderr').open('w') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            code = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            interrupted = True
            process.send_signal(signal.SIGINT)
            try:
                code = process.wait(timeout=config['native_save_grace'])
            except subprocess.TimeoutExpired:
                killed = True
                process.kill()
                code = process.wait()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'command': command, 'native_budget_seconds': seconds,
            'native_wall_seconds': time.monotonic()-start,
            'native_cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
            'budget_signal': interrupted, 'forced_kill': killed, 'returncode': code,
            'file': output.name, 'output_saved': output.is_file(), 'seed': seed, 'warm_start': warm is not None}


def worker(args):
    config = json.loads(Path(args.registration).read_text())
    frozen = Path(args.registration).parent/'frozen'
    sys.path.insert(0, str(frozen))
    from orientation_map import OrientationMap
    adapter = OrientationMap(config['paths']['mapping'], 19)
    case = next(case for case in config['cases'] if case['id'] == args.case)
    config['native_seconds'] = args.budget
    folder = Path(args.work)
    start = time.monotonic()
    report = {'case_id': case['id'], 'arm': args.arm, 'stages': [], 'feedback': [], 'status': 'STARTED'}
    def save():
        report['worker_wall_seconds'] = time.monotonic()-start
        atomic(folder/'result.json', report)
    save()
    try:
        if args.arm == 'prepare':
            from flippable2 import FlippabilityChecker
            with FlippabilityChecker(Path(config['cnf']).read_text()) as checker:
                flips, partial = checker.check('v '+' '.join(map(str, case['primary_model']))+' 0')
                report.update(status='PREPARED', flippables=sorted(flips), partial_model=partial,
                              flippability_stats=checker.last_stats)
            save()
            return
        if args.arm == 'audit':
            auditor = module(frozen/'compare19_audit.py', 'compare19_audit')
            for path in sorted(folder.glob('stage*.real')):
                try:
                    item = auditor.audit(path, folder/'full.or', {
                        'output_directory': str(folder/(path.stem+'-audit')),
                        'verifier_path': config['paths']['verifier'], 'cnf_path': config['cnf'],
                        'orientation_map_path': config['paths']['mapping'],
                        'cycles_path': config['paths']['cycles'], 'c3_verifier_path': config['paths']['c3_verifier']})
                    item['checkpoint'] = path.name
                    report.setdefault('audits', []).append(item)
                except Exception as exc:
                    report.setdefault('audits', []).append({'checkpoint': path.name, 'valid_geometry': False, 'audit_error': repr(exc)})
                save()
            report['status'] = 'AUDITED'
            save()
            return
        original = folder/'initial.or'
        report['final_checkpoint'] = 'stage1.real' if args.arm == 'improved_feedback' else 'stage0.real'
        save()
        if args.arm != 'improved_feedback':
            report['stages'].append(native(config, args.arm, original, folder/'stage0.real', case['seed'], config['native_seconds']))
            report['final_checkpoint'] = 'stage0.real'
        else:
            from flippable2 import FlippabilityChecker
            from sat_orient_conversion import inspect_realization
            from feedback import orientation_margins, core_guided_feedback
            first = folder/'stage0.real'
            first_budget = config['native_seconds']/2
            report['stages'].append(native(config, args.arm, original, first, case['seed'], first_budget))
            report['final_checkpoint'] = 'stage1.real'
            save()
            if not first.is_file():
                raise RuntimeError('First native stage did not save coordinates')
            inspection = inspect_realization(original, first, 19)
            next_target = original
            step = {'status': 'NO_CONSISTENT_PROJECTION'}
            feedback_start = time.monotonic()
            if inspection['sat_model'] is not None:
                actual, conflicts = adapter.project(inspection['sat_model'])
                step['mapping_conflicts'] = len(conflicts)
                if actual is not None:
                    with FlippabilityChecker(Path(config['cnf']).read_text()) as checker:
                        settings = {'feedback_core_choice': 'target_margin', 'feedback_max_solves': 128,
                                    'feedback_max_relaxed': 128, 'feedback_seconds': config['feedback_seconds'],
                                    'feedback_conflict_budget': 2000}
                        preferred = sorted({adapter.rank_to_variable[v] for v in inspection['bad_vars']})
                        revised, step = core_guided_feedback(checker.solver, actual, settings, case['seed']+1,
                                                            preferred, orientation_margins(first, 19, adapter))
                        if revised is not None:
                            step['repaired_primary_model'] = revised
                            # This checker contains only the original CNF, no corpus distance blocks.
                            flips, partial = checker.check('v '+' '.join(map(str, revised))+' 0')
                            step['flippables'] = sorted(flips)
                            step['flippability_stats'] = checker.last_stats
                            next_target = folder/'repaired.or'
                            next_target.write_text(adapter.orientations(partial))
            step['total_overhead_seconds'] = time.monotonic()-feedback_start
            report['feedback'].append(step)
            save()
            second = folder/'stage1.real'
            report['stages'].append(native(config, args.arm, next_target, second, case['seed']+1,
                                           config['native_seconds']-first_budget, first))
            report['final_checkpoint'] = second.name
        report['status'] = 'FINISHED' if all(stage['output_saved'] for stage in report['stages']) else 'MISSING_OUTPUT'
        save()
    except (KeyboardInterrupt, SystemExit):
        report.update(status='INTERRUPTED')
        save()
        raise
    except Exception as exc:
        report.update(status='ERROR', error=f'{type(exc).__name__}: {exc}')
        save()
        raise


def isolated(config, registration, case, arm, work, limit, budget=0):
    command = [config['python'], str(Path(registration).parent/'frozen/compare19.py'), 'worker',
               '--registration', str(registration), '--case', str(case['id']), '--arm', arm, '--work', str(work), '--budget', str(budget)]
    begin = time.monotonic()
    timed_out = False
    with (work/(arm+'-worker.stdout')).open('w') as stdout, (work/(arm+'-worker.stderr')).open('w') as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            if STOP.is_set() or time.monotonic()-begin >= limit:
                timed_out = not STOP.is_set()
                try:
                    os.killpg(child.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic()+1
                while time.monotonic() < deadline:
                    pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                    if pid:
                        break
                    time.sleep(.02)
                if not pid:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status, usage = os.wait4(child.pid, 0)
                break
            time.sleep(.03)
        child.returncode = os.waitstatus_to_exitcode(status)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    report = json.loads((work/'result.json').read_text()) if (work/'result.json').is_file() else {'status': 'NO_CHECKPOINT'}
    report.update(parent_wall_seconds=time.monotonic()-begin, parent_cpu_seconds=usage.ru_utime+usage.ru_stime,
                  returncode=child.returncode, overhead_watchdog=timed_out, externally_interrupted=STOP.is_set(),
                  cpu_accounting_flag=child.returncode < 0)
    return report


SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS preparation(case_id INTEGER PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trials(id INTEGER PRIMARY KEY, case_id INTEGER, arm TEXT, budget REAL, complete INTEGER, record TEXT);
CREATE TABLE IF NOT EXISTS artifacts(trial_id INTEGER, name TEXT, sha256 TEXT, data BLOB, PRIMARY KEY(trial_id,name));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, timestamp TEXT, event TEXT, record TEXT);
'''


def run(args):
    registration = Path(args.registration).resolve()
    config = json.loads(registration.read_text())
    out = registration.parent
    if args.workers not in (1, 2):
        raise ValueError('This registered benchmark permits only one or two workers')
    for filename, digest in config['frozen_sha256'].items():
        assert sha(out/'frozen'/filename) == digest, filename
    assert sha(config['cnf']) == config['cnf_sha256']
    allowed = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, allowed[:args.workers])
    lockfile = (out/'run.lock').open('a')
    fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    database = out/'results.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        done = {(row[0], row[1], row[2]) for row in db.execute('SELECT case_id,arm,budget FROM trials WHERE complete=1')}
        prepared = {row[0]: json.loads(row[1]) for row in db.execute('SELECT case_id,record FROM preparation')}
        db.execute('INSERT INTO events(timestamp,event,record) VALUES(?,?,?)',
                   (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'START', json.dumps({'workers': args.workers, 'affinity': allowed[:args.workers]})))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    adapter_module = module(out/'frozen/orientation_map.py', 'compare19_orientation_map')
    adapter = adapter_module.OrientationMap(config['paths']['mapping'], 19)

    def one(case):
        if STOP.is_set() or all((case['id'], job['arm'], job['budget']) in done for job in case['experiments']):
            return
        preparation = prepared.get(case['id'])
        if preparation is None:
            work = Path(tempfile.mkdtemp(prefix=f'.prep-{case["id"]:03}-', dir=out))
            preparation = isolated(config, registration, case, 'prepare', work, config['prepare_seconds'])
            if STOP.is_set():
                return
            if preparation.get('status') != 'PREPARED':
                if not preparation.get('overhead_watchdog'):
                    STOP.set()
                    raise RuntimeError(f'Preparation error for target {case["id"]}; preserved {work}')
                preparation.update(partial_model=case['primary_model'], flippables=[],
                                   fallback='Full target retained after bounded flippability timeout')
            with LOCK, sqlite3.connect(database) as db:
                db.execute('INSERT INTO preparation VALUES (?,?)', (case['id'], json.dumps(preparation)))
            shutil.rmtree(work)
        initial_text = adapter.orientations(preparation['partial_model'])
        for job in case['experiments']:
            arm, budget = job['arm'], job['budget']
            if STOP.is_set():
                return
            if (case['id'], arm, budget) in done:
                continue
            work = Path(tempfile.mkdtemp(prefix=f'.trial-{case["id"]:03}-{arm}-{budget:g}s-', dir=out))
            (work/'initial.or').write_text(initial_text)
            (work/'full.or').write_text(adapter.orientations(case['primary_model']))
            with LOCK, sqlite3.connect(database) as db:
                cursor = db.execute('INSERT INTO trials(case_id,arm,budget,complete,record) VALUES(?,?,?,?,?)',
                                    (case['id'], arm, budget, False, json.dumps({'status': 'RUNNING', 'workspace': str(work)})))
                identifier = cursor.lastrowid
            report = isolated(config, registration, case, arm, work,
                              budget+config['trial_overhead_cap'], budget)
            atomic(work/'search-result.json', report)
            audit_start = time.monotonic()
            audit_report = isolated(config, registration, case, 'audit', work, config['audit_seconds'])
            checks = audit_report.get('audits', [])
            final = next((item for item in checks if item['checkpoint'] == report.get('final_checkpoint')), {})
            report.update(case_id=case['id'], arm=arm, seed=case['seed'], budget_seconds=budget,
                          input_sha256=hashlib.sha256(initial_text.encode()).hexdigest(),
                          primary_valid_geometry=bool(final.get('valid_geometry')),
                          any_saved_valid_geometry=any(item.get('valid_geometry') for item in checks),
                          audits=checks, audit_status=audit_report['status'], audit_watchdog=audit_report['overhead_watchdog'],
                          audit_cpu_seconds=audit_report['parent_cpu_seconds'], posthoc_wall_seconds=time.monotonic()-audit_start)
            complete = not report['externally_interrupted'] and not audit_report['externally_interrupted']
            # Every attempt remains in the database; only completed ones suppress resume.
            files = [(str(path.relative_to(work)), path.read_bytes()) for path in work.rglob('*') if path.is_file()]
            with LOCK, sqlite3.connect(database) as db:
                db.execute('UPDATE trials SET complete=?,record=? WHERE id=?', (complete, json.dumps(report), identifier))
                db.executemany('INSERT INTO artifacts VALUES(?,?,?,?)',
                               [(identifier, name, hashlib.sha256(data).hexdigest(), zlib.compress(data, 3)) for name, data in files])
            if report['primary_valid_geometry'] or report['any_saved_valid_geometry']:
                destination = out/'successes'/f'trial-{identifier:04}-{arm}'
                destination.parent.mkdir(exist_ok=True)
                shutil.copytree(work, destination)
                atomic(destination/'trial.json', report)
            shutil.rmtree(work)
            print(json.dumps({'case': case['id'], 'arm': arm, 'budget': budget, 'valid': report['primary_valid_geometry'],
                              'any_saved_valid': report['any_saved_valid_geometry'], 'status': report['status'],
                              'native_cpu': sum(stage['native_cpu_seconds'] for stage in report.get('stages', [])),
                              'wall': report['parent_wall_seconds']}), flush=True)
    failed = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(one, case) for case in config['cases']]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failed = exc
                STOP.set()
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO events(timestamp,event,record) VALUES(?,?,?)',
                   (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'STOP' if STOP.is_set() else 'FINISH',
                    json.dumps({'error': repr(failed) if failed else None})))
    summarize(registration)
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    lockfile.close()
    if failed:
        raise failed


def summarize(registration):
    registration = Path(registration).resolve()
    config = json.loads(registration.read_text())
    with sqlite3.connect(registration.parent/'results.sqlite') as db:
        records = [json.loads(row[0]) for row in db.execute('SELECT record FROM trials WHERE complete=1 ORDER BY id')]
        preparation = [json.loads(row[0]) for row in db.execute('SELECT record FROM preparation')]
    latest = {(row['case_id'], row['arm'], row['budget_seconds']): row for row in records}
    count = 3*len(config['cases'])*len(config['budgets'])
    result = {'registered_trials': count, 'completed_trials': len(latest),
              'complete': len(latest) == count, 'budgets': {},
              'preparation_cpu_seconds': sum(row['parent_cpu_seconds'] for row in preparation),
              'preparation_wall_seconds': sum(row['parent_wall_seconds'] for row in preparation)}
    for budget in config['budgets']:
      group = result['budgets'][str(budget)] = {'arms': {}, 'pairs': {}}
      for arm in ARMS:
        rows = [row for (_, name, b), row in latest.items() if name == arm and b == budget]
        finals = [next((item for item in row['audits'] if item['checkpoint'] == row.get('final_checkpoint')), {}) for row in rows]
        residuals = [item['forbidden_hexagons'] for item in finals if item.get('general_position')]
        target_residuals = [item['orientation_violations'] for item in finals
                            if item.get('general_position') and item.get('orientation_violations') is not None]
        group['arms'][arm] = {'trials': len(rows), 'valid_final': sum(row['primary_valid_geometry'] for row in rows),
            'valid_any_checkpoint': sum(row['any_saved_valid_geometry'] for row in rows),
            'native_cpu_seconds': sum(stage['native_cpu_seconds'] for row in rows for stage in row.get('stages', [])),
            'native_wall_seconds': sum(stage['native_wall_seconds'] for row in rows for stage in row.get('stages', [])),
            'worker_observed_cpu_seconds': sum(row['parent_cpu_seconds'] for row in rows),
            'worker_wall_seconds': sum(row['parent_wall_seconds'] for row in rows),
            'audit_wall_seconds': sum(row['posthoc_wall_seconds'] for row in rows),
            'audit_cpu_seconds': sum(row['audit_cpu_seconds'] for row in rows),
            'general_position_final': sum(bool(item.get('general_position')) for item in finals),
            'median_forbidden_hexagons_in_GP': statistics.median(residuals) if residuals else None,
            'mean_forbidden_hexagons_in_GP': statistics.mean(residuals) if residuals else None,
            'median_orientation_violations_in_GP': statistics.median(target_residuals) if target_residuals else None,
            'watchdog_trials': sum(row['overhead_watchdog'] for row in rows),
            'audit_watchdog_trials': sum(row.get('audit_watchdog', False) for row in rows),
            'forced_native_kills': sum(stage.get('forced_kill', False) for row in rows for stage in row.get('stages', [])),
            'native_nonzero_exit_stages': sum(stage.get('returncode') != 0 for row in rows for stage in row.get('stages', [])),
            'native_missing_output_stages': sum(not stage.get('output_saved', False) for row in rows for stage in row.get('stages', [])),
            'status_counts': {status: sum(row['status'] == status for row in rows) for status in sorted({row['status'] for row in rows})},
            'error_trials': sum(row.get('status') in ('ERROR', 'NO_CHECKPOINT', 'MISSING_OUTPUT') for row in rows),
            'audit_errors': sum('audit_error' in check for row in rows for check in row['audits'])}
      for first, second in (('original', 'improved_fixed'), ('original', 'improved_feedback'), ('improved_fixed', 'improved_feedback')):
        counts = {'pairs': 0, 'first_only': 0, 'second_only': 0, 'both': 0, 'neither': 0}
        for case in config['cases']:
            a, b = latest.get((case['id'], first, budget)), latest.get((case['id'], second, budget))
            if a is None or b is None:
                continue
            counts['pairs'] += 1
            x, y = a['primary_valid_geometry'], b['primary_valid_geometry']
            counts['both' if x and y else 'first_only' if x else 'second_only' if y else 'neither'] += 1
        group['pairs'][first+'__'+second] = counts
    atomic(registration.parent/'summary.json', result)
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('register')
    p.add_argument('--corpus', required=True); p.add_argument('--output', required=True)
    p.add_argument('--targets', type=int, default=20); p.add_argument('--budgets', type=float, nargs='+', default=[10, 30, 60])
    p.add_argument('--seed', type=int, default=190907); p.set_defaults(fn=register)
    p = sub.add_parser('run')
    p.add_argument('--registration', required=True); p.add_argument('--workers', type=int, choices=(1, 2), default=2); p.set_defaults(fn=run)
    p = sub.add_parser('summarize')
    p.add_argument('--registration', required=True); p.set_defaults(fn=lambda args: summarize(args.registration))
    p = sub.add_parser('worker')
    p.add_argument('--registration', required=True); p.add_argument('--case', type=int, required=True)
    p.add_argument('--arm', choices=ARMS+('prepare', 'audit'), required=True); p.add_argument('--work', required=True)
    p.add_argument('--budget', type=float, default=0); p.set_defaults(fn=worker)
    args = parser.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
