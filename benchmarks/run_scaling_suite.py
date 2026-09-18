#!/usr/bin/env python3
"""Sequential two-core study supervisor; explicit invocation starts the queue.

SIGINT/SIGTERM is forwarded only to the owned child coordinator. Its existing
worker cleanup is allowed to finish; no following stage starts after a signal.
Rerunning after interruption resumes completed benchmark trials, not a native
trajectory. Existing audit/report outputs are never overwritten.
Creating STATE_DIRECTORY/STOP requests the same graceful pause across PID
namespaces. Remove that marker explicitly before resuming the queue.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path); temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def start_ticks(pid):
    try:
        value = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if value[0] == 'Z' else value[19]
    except (OSError, IndexError):
        return None


def process_identity(pid):
    return {'pid': pid, 'start_ticks': start_ticks(pid)}


def alive(identity):
    return bool(identity and identity.get('start_ticks') and
                start_ticks(identity['pid']) == identity['start_ticks'])


def build_plan(args):
    nineteen = Path(args.nineteen_registration).resolve()
    paper = Path(args.paper_registration).resolve()
    report = Path(args.report_output).resolve(); audit = Path(args.audit_output).resolve()
    state = Path(args.state_directory).resolve()
    if state == report or state.is_relative_to(report) or audit.is_relative_to(report):
        raise ValueError('Report output must be a separate NEW directory, not an ancestor of state/audit')
    if audit in (state/'state.json', state/'pid.json', state/'suite.log', state/'suite.lock'):
        raise ValueError('Audit output conflicts with supervisor state files')
    identity = {'nineteen_registration': str(nineteen), 'paper_registration': str(paper),
                'report_output': str(report), 'audit_output': str(audit)}
    steps = []; files = [Path(__file__).resolve(), nineteen, paper]
    for name, registration, script in [('nineteen', nineteen, 'compare19.py'),
                                        ('paper', paper, 'compare_families.py')]:
        config = json.loads(registration.read_text())
        harness = registration.parent/'frozen'/script
        if sha(harness) != config['frozen_sha256'][script]:
            raise ValueError('Frozen harness hash mismatch: '+str(harness))
        files.append(harness)
        steps.append({'name': name, 'kind': 'benchmark',
            'command': [config['python'], str(harness), 'run', '--registration', str(registration), '--workers', '2'],
            'summary': str(registration.parent/'summary.json'),
            'expected_trials': len(config['cases'])*len(config['arms'])*len(config['budgets'])})
    auditor = ROOT/'benchmarks/scaling_audit.py'; reporter = ROOT/'benchmarks/scaling_report.py'
    files += [auditor, reporter, ROOT/'benchmarks/scaling_effects.py', ROOT/'benchmarks/scaling_pdf.py']
    steps += [{'name': 'audit', 'kind': 'audit', 'output': str(audit),
               'command': [sys.executable, str(auditor), '--registration', str(nineteen), str(paper), '--output', str(audit)]},
              {'name': 'report', 'kind': 'report', 'output': str(report),
               'command': [sys.executable, str(reporter), '--nineteen-registration', str(nineteen),
                           '--paper-registration', str(paper), '--out', str(report)]}]
    for option in ('machine_info', 'positive_control_result'):
        if getattr(args, option, None):
            extra = Path(getattr(args, option)).resolve()
            identity[option] = str(extra); files.append(extra)
            steps[-1]['command'] += ['--'+option.replace('_', '-'), str(extra)]
    for step in steps:
        step['command_sha256'] = hashlib.sha256(json.dumps(step['command'], separators=(',', ':')).encode()).hexdigest()
    fingerprints = {str(path): sha(path) for path in files}
    return identity, steps, fingerprints, state


def validate_stage(step):
    if step['kind'] == 'benchmark':
        path = Path(step['summary']); result = json.loads(path.read_text())
        if result.get('complete') is not True or result.get('registered_trials') != step['expected_trials'] or result.get('completed_trials') != step['expected_trials']:
            raise ValueError('Benchmark returned without a complete, correctly counted summary: '+str(path))
        return {str(path): sha(path)}
    if step['kind'] == 'audit':
        path = Path(step['output']); result = json.loads(path.read_text())
        if result.get('status') != 'PASSED' or result.get('integrity_ok') is not True:
            raise ValueError('Integrity audit is not PASSED; report will not start: '+str(path))
        return {str(path): sha(path)}
    folder = Path(step['output']); report = folder/'report.json'
    result = json.loads(report.read_text())
    if result.get('draft') is not False or len(result.get('studies', [])) != 2 or not all(s.get('complete') is True for s in result['studies']):
        raise ValueError('Final report is incomplete or marked draft')
    return {str(path): sha(path) for path in sorted(folder.rglob('*')) if path.is_file()}


def execute(identity, steps, fingerprints, state_directory, stop=None, affinity=None):
    """Testable queue engine; `stop` is an Event carrying optional .signum."""
    stop = stop if stop is not None else threading.Event()
    directory = Path(state_directory); directory.mkdir(parents=True, exist_ok=True)
    lock = (directory/'suite.lock').open('a')
    child = None; state = None; claimed = False
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory/'state.json'
        if path.exists():
            state = json.loads(path.read_text())
            if state['configuration'] != identity or state['source_sha256'] != fingerprints or state['plan'] != steps:
                raise ValueError('State configuration/source hashes changed; use a NEW state directory')
            if alive(state.get('active_process')):
                raise ValueError('Previous owned coordinator is still alive; wait for it to finish before resuming')
        else:
            state = {'schema_version': 1, 'created_utc': utc(), 'configuration': identity,
                     'source_sha256': fingerprints, 'plan': steps, 'history': []}
        # Fail BEFORE launching any benchmark if postprocessing cannot be safe.
        for key in ('report_output', 'audit_output'):
            if Path(identity[key]).exists():
                raise ValueError('Output already exists: '+identity[key]+'. Nothing launched; choose NEW outputs and state directory.')
        for source, digest in fingerprints.items():
            if sha(source) != digest:
                raise ValueError('Registered suite source changed: '+source)
        owner = process_identity(os.getpid())
        state.update(status='RUNNING', supervisor=owner, active_process=None, updated_utc=utc(), affinity=affinity)
        claimed = True
        def save():
            state['updated_utc'] = utc(); atomic(path, state)
            atomic(directory/'pid.json', {'supervisor': owner if state['status'] in ('RUNNING', 'STOPPING') else None,
                'active_process': state.get('active_process'), 'status': state['status'], 'updated_utc': state['updated_utc']})
        with (directory/'suite.log').open('a', buffering=1) as log:
            def event(event_name, **fields):
                log.write(json.dumps({'utc': utc(), 'event': event_name, **fields})+'\n'); log.flush()
            def observe_stop():
                if (directory/'STOP').exists():
                    if not stop.is_set():
                        stop.signum = signal.SIGTERM
                    stop.set(); state['stop_reason'] = 'STOP marker; remove it explicitly before resume'
                return stop.is_set()
            save(); event('SUITE_START', supervisor=owner, affinity=affinity)
            for step in steps:
                if observe_stop():
                    state['status'] = 'INTERRUPTED'; save(); return 130
                for source, digest in fingerprints.items():
                    if sha(source) != digest:
                        raise ValueError('Suite source changed before stage '+step['name']+': '+source)
                if step['kind'] in ('audit', 'report'):
                    target = Path(step['output'])
                    if target.exists():
                        raise ValueError('Refusing to overwrite newly existing output: '+str(target))
                    target.parent.mkdir(parents=True, exist_ok=True)
                attempt = {'name': step['name'], 'started_utc': utc(), 'command': step['command'],
                           'command_sha256': step.get('command_sha256'), 'status': 'STARTING'}
                state['history'].append(attempt); save(); begin = time.monotonic()
                env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
                child = subprocess.Popen(step['command'], stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True, env=env)
                state['active_process'] = process_identity(child.pid)
                attempt.update(status='RUNNING', process=state['active_process']); save()
                event('STAGE_START', name=step['name'], process=state['active_process'], command=step['command'])
                forwarded = False
                while child.poll() is None:
                    if observe_stop() and not forwarded:
                        # Deliberately NOT killpg: only this owned coordinator
                        # receives the request, and it cleans up its workers.
                        requested = getattr(stop, 'signum', signal.SIGTERM)
                        try:
                            child.send_signal(requested)
                        except ProcessLookupError:
                            pass
                        forwarded = True; state['status'] = 'STOPPING'; save()
                        event('STOP_FORWARDED', signal=requested, process=state['active_process'])
                    time.sleep(.1)
                code = child.returncode; child = None
                state['active_process'] = None
                attempt.update(returncode=code, finished_utc=utc(), wall_seconds=time.monotonic()-begin)
                if stop.is_set():
                    attempt['status'] = 'INTERRUPTED'; state['status'] = 'INTERRUPTED'; save()
                    event('SUITE_INTERRUPTED', name=step['name'], returncode=code); return 130
                if code:
                    attempt['status'] = 'FAILED'; state['status'] = 'FAILED'; save()
                    event('STAGE_FAILED', name=step['name'], returncode=code); return 1
                attempt['output_sha256'] = validate_stage(step)
                attempt['status'] = 'COMPLETE'; save()
                event('STAGE_COMPLETE', name=step['name'], wall_seconds=attempt['wall_seconds'])
            state['status'] = 'COMPLETE'; save(); event('SUITE_COMPLETE'); return 0
    except BaseException as error:
        # Unexpected supervisor failures must still ask the owned coordinator
        # to checkpoint and finish cleanup before releasing the suite lock.
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM); child.wait()
        if state is not None and claimed:
            if state['history'] and state['history'][-1]['status'] in ('STARTING', 'RUNNING'):
                state['history'][-1].update(status='FAILED', error=f'{type(error).__name__}: {error}', finished_utc=utc())
            state.update(status='FAILED', active_process=None, error=f'{type(error).__name__}: {error}', updated_utc=utc())
            atomic(directory/'state.json', state)
            atomic(directory/'pid.json', {'supervisor': None, 'active_process': None, 'status': 'FAILED'})
        raise
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN); lock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('nineteen-registration', 'paper-registration', 'report-output', 'audit-output', 'state-directory'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--machine-info')
    parser.add_argument('--positive-control-result')
    args = parser.parse_args(argv)
    stop = threading.Event()
    def interrupt(signum, _frame):
        stop.signum = signum; stop.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupt)
    try:
        identity, steps, fingerprints, directory = build_plan(args)
        allowed = sorted(os.sched_getaffinity(0))
        if len(allowed) < 2:
            raise ValueError('Two available CPU cores required; refusing a differently resourced study')
        os.sched_setaffinity(0, allowed[:2])
        code = execute(identity, steps, fingerprints, directory, stop, allowed[:2])
        print(json.dumps({'state_directory': str(directory), 'returncode': code})); return code
    except (OSError, ValueError, KeyError) as error:
        print('Scaling suite stopped: '+str(error), file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
