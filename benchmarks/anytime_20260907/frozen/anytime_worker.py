#!/usr/bin/env python3
"""One cold, total-wall-budget realization trajectory, or a secondary audit.

The parent supplies its monotonic process-launch timestamp. Imports, initial
flippability, localization, repeated repair, and online acceptance all consume
that same allowance. No state is shared between targets or treatment arms.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time


def atomic(path, value):
    path = Path(path); temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); sys.modules[name] = result
    spec.loader.exec_module(result); return result


def cpu():
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+children.ru_utime+children.ru_stime


def remaining(config, start):
    return max(0., start+config['horizon_seconds']-time.monotonic())


def credit_time(timestamp, start, horizon):
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        return None
    elapsed = timestamp-start
    return elapsed if 0 <= elapsed <= horizon else None


def native_command(config, case, arm, target, output, seed, seconds, warm=None):
    version = 'original' if arm == 'original' else 'v4' if arm.startswith('v4_') else 'v6'
    paths = config['paths']; symmetric = case['family'] == 'symmetry19'
    fixed, cycles = (paths['fixed'], paths['cycles']) if symmetric else ('', '')
    if any(len(str(p).encode()) >= 250 for p in (output, fixed, cycles)):
        raise ValueError('Path exceeds upstream fixed filename buffer')
    command = [paths[version], str(target), '-t', '1', '-i', '10', '-r', '30000',
               '-s', str(seed), '-f', str(fixed), '-c', str(cycles), '-o', str(output)]
    if version != 'original':
        command += ['-T', str(seconds), '-q']
        if version == 'v4':
            command += ['--line-every', '10', '--min-radius', '0.000001']
        elif arm in ('v6_line', 'v6_pair'):
            command += ['--line-every', '10']
            if arm == 'v6_pair':
                command += ['--pair-every', '10']
        if warm is not None:
            command += ['-w', str(warm)]
    return command


def native(config, case, arm, target, output, seed, seconds, warm=None):
    command = native_command(config, case, arm, target, output, seed, seconds, warm)
    output = Path(output); before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic(); interrupted = killed = False
    with output.with_suffix('.stdout').open('w') as stdout, output.with_suffix('.stderr').open('w') as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            try:
                code = child.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                interrupted = True; child.send_signal(signal.SIGINT)
                try:
                    code = child.wait(timeout=config['save_grace_seconds'])
                except subprocess.TimeoutExpired:
                    killed = True; child.kill(); code = child.wait()
        except BaseException:
            # Outer process-group signal may arrive during wait. Reap this
            # child before the worker exits; the coordinator has a hard backup.
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=config['save_grace_seconds'])
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()
            raise
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'file': output.name, 'command': command, 'requested_native_seconds': seconds,
            'native_wall_seconds': time.monotonic()-start,
            'native_cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
            'returncode': code, 'budget_signal': interrupted, 'forced_kill': killed,
            'output_saved': output.is_file(), 'seed': seed, 'warm_start': warm is not None}


def worker(args):
    start = args.started
    registration = Path(args.registration).resolve(); frozen = registration.parent/'frozen'
    config = json.loads(registration.read_text()); sys.path.insert(0, str(frozen))
    case = next(c for c in config['cases'] if c['id'] == args.case)
    if args.arm not in config['arms_for_family'][case['family']]:
        raise ValueError('Unregistered arm')
    work = Path(args.work); horizon = config['horizon_seconds']; deadline = start+horizon
    report = {'case_id': case['id'], 'family': case['family'], 'arm': args.arm, 'seed': case['seed'],
              'started_monotonic': start, 'deadline_monotonic': deadline, 'status': 'STARTED',
              'initial_full_sha256': case['initial_full_sha256'], 'initial_target_sha256': None,
              'first_verified_seconds': None, 'certificates': [], 'components': [], 'stages': [],
              'feedback': [], 'check_errors': [], 'phase': 'STARTUP', 'last_checkpoint': None}
    checker = None

    def save():
        report['observed_seconds'] = max(0., time.monotonic()-start)
        report['censor_seconds'] = min(horizon, report['observed_seconds'])
        atomic(work/'result.json', report)

    def phase(kind, operation):
        report['phase'] = kind; save()
        begin = time.monotonic(); before = cpu()
        try:
            return operation()
        finally:
            report['components'].append({'kind': kind, 'start_elapsed_seconds': begin-start,
                                         'wall_seconds': time.monotonic()-begin,
                                         'cpu_seconds': max(0., cpu()-before)})
            save()

    save()
    try:
        def prepare():
            nonlocal checker
            from flippable2 import FlippabilityChecker
            from sat_orient_conversion import get_orientations
            from orientation_map import OrientationMap
            adapter = OrientationMap(config['paths']['mapping'], case['n']) if case['family'] == 'symmetry19' else None
            def orientations(model):
                return adapter.orientations(model) if adapter else get_orientations(model, case['n'])
            full = orientations(case['primary_model'])
            if hashlib.sha256(full.encode()).hexdigest() != case['initial_full_sha256']:
                raise ValueError('Registered full orientation input changed')
            (work/'full.or').write_text(full)
            model = 'v '+' '.join(map(str, case['primary_model']))+' 0'
            formula = Path(case['cnf']).read_text()
            if args.arm == 'original':
                from legacy_flippable import check_flippable
                flips, partial = check_flippable(formula, model)
                stats = {'implementation': 'legacy_git_snapshot',
                         'flip_sat_calls': len(case['primary_model'])}
            else:
                checker = FlippabilityChecker(formula)
                flips, partial = checker.check(model)
                stats = dict(checker.last_stats, implementation='updated_reusable_checker')
            initial = orientations(partial); (work/'initial.or').write_text(initial)
            report.update(initial_target_sha256=hashlib.sha256(initial.encode()).hexdigest(),
                          initial_flippables=sorted(flips), initial_partial_model=partial,
                          initial_flippability_stats=stats)
            return adapter, orientations

        if remaining(config, start) <= 0:
            report['status'] = 'TIME_LIMIT'; save(); return
        adapter, orientations = phase('preparation', prepare)
        from anytime_geometry import audit
        from sat_orient_conversion import inspect_realization
        from feedback import core_guided_feedback, orientation_margins
        segmented = args.arm.endswith(('_retry', '_feedback'))
        feedback_enabled = args.arm.endswith('_feedback')
        target, warm, index = work/'initial.or', None, 0
        while remaining(config, start) > config['verification_reserve_seconds']:
            allowance = remaining(config, start)-config['verification_reserve_seconds']
            if segmented:
                allowance = min(allowance, config['native_slice_seconds'])
            if allowance <= 0:
                break
            seed = (case['seed']+index*1000003) & 0x7fffffff
            output = work/f'stage{index:04d}.real'
            report['current_checkpoint'] = output.name; save()
            stage = phase('native', lambda: native(config, case, args.arm, target, output, seed, allowance, warm))
            report['stages'].append(stage); save()
            if not output.is_file():
                if remaining(config, start) <= 0:
                    break
                raise RuntimeError('Native process returned without a coordinate snapshot')
            report['last_checkpoint'] = output.name; save()
            directory = work/f'check{index:04d}'
            verifier = config['paths']['verifier19' if case['family'] == 'symmetry19' else 'verifier_paper']
            certificate = phase('online_audit', lambda: audit(output, case['family'], {
                'output_directory': str(directory), 'verifier_path': verifier,
                'deadline_monotonic': deadline,
                'expected_verifier_sha256': config['frozen_sha256'][Path(verifier).name]}))
            certificate['checkpoint'] = output.name
            if certificate.get('certificate'):
                certificate['certificate_artifact'] = str(Path(certificate['certificate']).relative_to(work))
            elapsed = credit_time(certificate.get('accepted_timestamp_monotonic'), start, horizon)
            certificate['accepted_elapsed_seconds'] = elapsed if certificate.get('accepted') else None
            report['certificates'].append(certificate)
            if certificate.get('accepted'):
                if elapsed is None:
                    raise RuntimeError('Online checker credited a certificate outside its deadline')
                report.update(status='SOLVED', first_verified_seconds=elapsed,
                              accepted_checkpoint=output.name, accepted_certificate=certificate.get('certificate_artifact'))
                save(); return
            save()
            if certificate['status'] == 'CHECK_ERROR':
                report['check_errors'].append(certificate); save()
                raise RuntimeError('Online exact checker failed: '+str(certificate.get('error')))
            if remaining(config, start) <= config['verification_reserve_seconds']:
                break
            if feedback_enabled:
                def repair():
                    nonlocal target
                    inspected = inspect_realization(target, output, case['n'])
                    stats = {'status': 'NO_GP_PROJECTION'}
                    actual = inspected['sat_model']
                    if actual is not None:
                        conflicts = []
                        if adapter:
                            actual, conflicts = adapter.project(actual)
                        if actual is not None:
                            preferred = inspected['bad_vars']
                            if adapter:
                                preferred = sorted({adapter.rank_to_variable[v] for v in preferred})
                            settings = {'feedback_core_choice': 'target_margin', 'feedback_max_solves': 128,
                                        'feedback_max_relaxed': 128, 'feedback_conflict_budget': 2000,
                                        'feedback_seconds': min(config['feedback_seconds'], remaining(config, start))}
                            revised, stats = core_guided_feedback(checker.solver, actual, settings, seed,
                                preferred, orientation_margins(output, case['n'], adapter))
                            if revised is not None and remaining(config, start) > 0:
                                flips, partial = checker.check('v '+' '.join(map(str, revised))+' 0')
                                target = work/f'target{index+1:04d}.or'
                                target.write_text(orientations(partial))
                                stats.update(repaired_primary_model=revised, flippables=sorted(flips),
                                             flippability_stats=checker.last_stats,
                                             target_sha256=sha(target))
                        else:
                            stats = {'status': 'ORBIT_CONFLICT', 'mapping_conflicts': len(conflicts)}
                    report['feedback'].append(stats)
                phase('feedback', repair)
            # Continuous treatments never gain -w support or artificial
            # checkpoints: a premature invalid natural return starts cold.
            warm = output if segmented else None
            index += 1
        report['phase'] = 'FINAL_RESERVE'; save()
        while remaining(config, start) > 0:
            time.sleep(min(.05, remaining(config, start)))
        report['status'] = 'TIME_LIMIT'; save()
    except (KeyboardInterrupt, SystemExit):
        report['status'] = 'TIME_LIMIT' if time.monotonic() >= deadline else 'INTERRUPTED'
        save(); raise
    except Exception as error:
        report.update(status='ERROR', error=f'{type(error).__name__}: {error}'); save(); raise
    finally:
        if checker is not None:
            checker.close()


def posthoc(args):
    registration = Path(args.registration).resolve(); frozen = registration.parent/'frozen'
    config = json.loads(registration.read_text()); sys.path.insert(0, str(frozen))
    case = next(c for c in config['cases'] if c['id'] == args.case); work = Path(args.work)
    search = json.loads((work/'search-result.json').read_text())
    report = {'status': 'STARTED', 'audits': [], 'outside_online_deadline': True}
    atomic(work/'posthoc-result.json', report)
    auditor = module(frozen/'compare19_audit.py', 'independent_anytime_audit')
    family_auditor = module(frozen/'compare_families.py', 'independent_anytime_family')
    from sat_orient_conversion import get_orientations
    from orientation_map import OrientationMap
    full = work/'full.or'
    if not full.is_file():
        adapter = OrientationMap(config['paths']['mapping'], 19) if case['family'] == 'symmetry19' else None
        full.write_text(adapter.orientations(case['primary_model']) if adapter else get_orientations(case['primary_model'], case['n']))
    names = {search.get('accepted_checkpoint'), search.get('last_checkpoint'), search.get('current_checkpoint')}
    for name in sorted(n for n in names if n and (work/n).is_file()):
        try:
            directory = work/('posthoc-'+Path(name).stem)
            if case['family'] == 'symmetry19':
                item = auditor.audit(work/name, full, {
                    'output_directory': str(directory), 'verifier_path': config['paths']['verifier19'],
                    'cnf_path': case['cnf'], 'orientation_map_path': config['paths']['mapping'],
                    'cycles_path': config['paths']['cycles'], 'c3_verifier_path': config['paths']['c3_verifier']})
            else:
                item = family_auditor.audit_family(work/name, full, case, directory,
                    {'paths': {'verifier': config['paths']['verifier_paper']}}, auditor)
            report['audits'].append(dict(item, checkpoint=name, posthoc=True))
        except Exception as error:
            report['audits'].append({'checkpoint': name, 'posthoc': True, 'audit_error': repr(error)})
        atomic(work/'posthoc-result.json', report)
    report['status'] = 'AUDITED'; atomic(work/'posthoc-result.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('worker', 'posthoc'))
    parser.add_argument('--registration', required=True); parser.add_argument('--case', required=True)
    parser.add_argument('--work', required=True); parser.add_argument('--arm', default='')
    parser.add_argument('--started', type=float)
    args = parser.parse_args()
    if args.mode == 'worker' and args.started is None:
        parser.error('worker requires the parent monotonic --started timestamp')
    (worker if args.mode == 'worker' else posthoc)(args)


if __name__ == '__main__':
    main()
