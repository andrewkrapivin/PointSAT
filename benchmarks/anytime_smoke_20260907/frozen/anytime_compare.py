#!/usr/bin/env python3
"""Frozen total-wall anytime comparison; registration never launches search.

One120-second trajectory yields verified-return observations at30/60/120s.
Initialization, flippability, native search, feedback and online exact checking
all share that clock. Post-hoc audits are separately timed and cannot create a
primary success. At most two single-core workers; STOP pauses without replacing
earlier complete records. `run` is the only command that launches searches.
"""
import argparse
import ast
from collections import Counter
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
ARMS19 = ['original', 'v4_fixed', 'v4_retry', 'v4_feedback']
ARMS_PAPER = ['original', 'v6_plain', 'v6_line', 'v6_pair', 'v6_retry', 'v6_feedback']
STOP, LOCK = threading.Event(), threading.Lock()
SCHEMA = '''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS trials(id INTEGER PRIMARY KEY,case_id TEXT,arm TEXT,complete INTEGER,record TEXT);
CREATE TABLE IF NOT EXISTS artifacts(trial_id INTEGER,name TEXT,sha256 TEXT,data BLOB,PRIMARY KEY(trial_id,name));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,timestamp TEXT,event TEXT,record TEXT);
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def atomic(path, value):
    path = Path(path); tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n'); tmp.replace(path)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); sys.modules[name] = result
    spec.loader.exec_module(result); return result


def checked_registration(path):
    path = Path(path).resolve(); config = json.loads(path.read_text())
    for filename, digest in config['frozen_sha256'].items():
        if sha(path.parent/'frozen'/filename) != digest:
            raise ValueError('Frozen source/binary changed: '+filename)
    return config


def register(args):
    nineteen_path = Path(args.nineteen_registration).resolve()
    paper_path = Path(args.paper_registration).resolve()
    nineteen, paper = checked_registration(nineteen_path), checked_registration(paper_path)
    if len(nineteen['cases']) != 20 or Counter(c['family'] for c in paper['cases']) != {
            'mixed23': 20, 'holes29': 20, 'gons32': 20, 'caps26': 20}:
        raise ValueError('This registration requires the fixed20 targets in each of five families')
    out = Path(args.output).resolve(); report = Path(args.report_output).resolve()
    if out.exists() or report.exists() or out == report or out.is_relative_to(report):
        raise ValueError('Registration and report must be NEW, separate output directories')
    source_files = [Path(__file__), ROOT/'benchmarks/anytime_worker.py', ROOT/'benchmarks/anytime_geometry.py',
        ROOT/'benchmarks/compare19_audit.py', ROOT/'benchmarks/compare_families.py',
        ROOT/'sat_orient_conversion.py', ROOT/'flippable2.py', ROOT/'improvements/pipeline/orientation_map.py']
    reporter = ROOT/'benchmarks/anytime_report.py'
    if not reporter.is_file():
        raise ValueError('Final anytime reporter must be ready before registration')
    source_files += [reporter, ROOT/'benchmarks/anytime_pdf.py']
    for source in source_files:
        if not source.is_file():
            raise ValueError('Required source not ready: '+str(source))
    legacy_commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    legacy = subprocess.check_output(['git','show',legacy_commit+':flippable2.py'],cwd=ROOT)
    legacy_blob = subprocess.check_output(['git','rev-parse',legacy_commit+':flippable2.py'],cwd=ROOT,text=True).strip()
    adapter_type = module(ROOT/'improvements/pipeline/orientation_map.py', 'anytime_registration_map').OrientationMap
    conversion = module(ROOT/'sat_orient_conversion.py', 'anytime_registration_conversion')
    adapter = adapter_type(nineteen['paths']['mapping'], 19)
    rng = random.Random(args.seed); cases19 = []; cases_paper = []
    for old in nineteen['cases']:
        case = {'id': 'symmetry19-'+str(old['id']), 'source_case_id': old['id'], 'family': 'symmetry19',
            'n': 19, 'gon': 0, 'hole': 0, 'cap': 0, 'seed': old['seed'], 'primary_model': old['primary_model'],
            'canonical_sha256': old.get('canonical_sha256'), 'cnf': nineteen['cnf'], 'cnf_sha256': nineteen['cnf_sha256'],
            'initial_full_sha256': hashlib.sha256(adapter.orientations(old['primary_model']).encode()).hexdigest(),
            'condition_order': list(ARMS19)}
        case['source_corpus_id'] = old.get('corpus_id')
        case['source_case_metadata'] = {k:v for k,v in old.items() if k not in ('primary_model','experiments')}
        rng.shuffle(case['condition_order']); cases19.append(case)
    for old in paper['cases']:
        case = {key: old[key] for key in ('family','n','gon','hole','cap','seed','primary_model','cnf','cnf_sha256','canonical_sha256')}
        case.update(id=old['family']+'-'+str(old['id']), source_case_id=old['id'],
            initial_full_sha256=hashlib.sha256(conversion.get_orientations(old['primary_model'], old['n']).encode()).hexdigest(),
            condition_order=list(ARMS_PAPER))
        rng.shuffle(case['condition_order']); cases_paper.append(case)
    rng.shuffle(cases19); rng.shuffle(cases_paper)
    cases = cases19+cases_paper
    for family in {c['family'] for c in cases}:
        keys = [c['canonical_sha256'] for c in cases if c['family'] == family]
        if None in keys or len(set(keys)) != 20:
            raise ValueError('Expected20 distinct canonical types in '+family)
    out.mkdir(parents=True); frozen = out/'frozen'; frozen.mkdir()
    for source in source_files:
        shutil.copy2(source, frozen/source.name)
    (frozen/'legacy_flippable.py').write_bytes(legacy)
    corpus = Path(nineteen['corpus'])
    corpus_manifest = corpus/'manifest.json' if corpus.is_dir() else corpus
    if corpus_manifest.is_file():
        shutil.copy2(corpus_manifest, frozen/'nineteen-corpus-manifest.json')
    paths = {}
    binaries = {'original': ROOT/'improvements/localizer/localizer_baseline',
                'v4': ROOT/'improvements/localizer/localizer_v4', 'v6': ROOT/'improvements/localizer/localizer_v6',
                'verifier19': Path(nineteen['paths']['verifier']), 'verifier_paper': Path(paper['paths']['verifier']),
                'c3_verifier': Path(nineteen['paths']['c3_verifier'])}
    for name, source in binaries.items():
        target = frozen/name; shutil.copy2(source, target); paths[name] = str(target)
    for name in ('mapping', 'cycles', 'fixed'):
        source = Path(nineteen['paths'][name]); target = frozen/(name+source.suffix)
        shutil.copy2(source, target); paths[name] = str(target)
    runner = (ROOT/'improvements/pipeline/runner.py').read_text()
    functions = [ast.get_source_segment(runner, node) for node in ast.parse(runner).body
        if isinstance(node, ast.FunctionDef) and node.name in ('orientation_margins','core_guided_feedback')]
    if len(functions) != 2:
        raise ValueError('Expected both frozen feedback functions')
    (frozen/'feedback.py').write_text('import time,math,hashlib\nfrom sat_orient_conversion import integer_points\n\n'+'\n\n'.join(functions)+'\n')
    config = {'schema_version': 1, 'registered_utc': utc(), 'root': str(ROOT),
        'python': str(ROOT/'direct/vendor/venv/bin/python'), 'report_python': sys.executable,
        'cases': cases, 'paths': paths, 'family_arms': {family: ARMS19 if family == 'symmetry19' else ARMS_PAPER
                                                   for family in {c['family'] for c in cases}},
        'horizon_seconds': 120, 'milestones': [30,60,120], 'native_slice_seconds': 15,
        'verification_reserve_seconds': 3, 'save_grace_seconds': .5, 'feedback_seconds': 10,
        'posthoc_seconds': 20, 'report_seconds': 300, 'workers_max': 2, 'randomization_seed': args.seed,
        'frozen_sha256': {p.name: sha(p) for p in frozen.iterdir()},
        'source_registrations': [{'path': str(p), 'sha256': sha(p)} for p in (nineteen_path, paper_path)],
        'baseline_preparation_source': {'git_commit':legacy_commit,'git_blob':legacy_blob,
            'repository_path':'flippable2.py','frozen_file':'legacy_flippable.py','sha256':hashlib.sha256(legacy).hexdigest()},
        'report_output': str(report),
        'primary_endpoint': 'First exact verified returned geometry before the shared total-wall deadline. Online acceptance time, not native residual or post-hoc discovery.',
        'budget_scope': '120 total wall seconds including imports, initial flippability, native work, warm retries, SAT feedback and online exact checks;30/60/120 are milestones on ONE trajectory.',
        'posthoc_scope': 'Independent20-second bounded post-hoc diagnostics outside the primary clock; cannot credit an online success.',
        'selection': 'Same20 fixed canonical-distinct targets/family as the stopped native-budget diagnostic; reused data, not unseen targets. Nineteen-point source corpus mixes9fresh and11historical initial-SAT targets. No coordinate seeds.',
        'strategy_scope': 'Retry and feedback both use15-second native bursts and online checks; feedback adds the registered SAT treatment. Continuous variants check natural returns and the final stopped snapshot only.',
        'preparation_scope': 'Original uses the exact HEAD legacy check_flippable; all updated arms use the current FlippabilityChecker. Logical partial targets must agree, but actual preparation costs are charged separately inside each trajectory. Original-versus-updated is a package comparison, not a native-only ablation.',
        'baseline_scope': 'Common orientation adapter, logging, online exact acceptance and deadline wrapper across arms. This is not the literal whole original PointSAT driver; SAT generation is excluded.',
        'symmetry_scope': 'Identical cycles/fixed center for all19-point arms; unrestricted exact geometry is primary, exactC3/CNF are secondary.',
        'caps_scope': 'Same strict-x cap counting as prior exact checker; no extra repeated-x rejection or --ordered-x treatment.'}
    config['arms_for_family'] = config['family_arms']
    for key in ('machine_info','positive_control_result'):
        if getattr(args, key, None):
            config[key] = str(Path(getattr(args,key)).resolve()); config[key+'_sha256'] = sha(config[key])
    atomic(out/'registration.json', config)
    print(json.dumps({'registration': str(out/'registration.json'), 'trajectories': sum(len(c['condition_order']) for c in cases),
                      'maximum_primary_core_hours': sum(len(c['condition_order']) for c in cases)/30,
                      'searches_launched': 0}))


def requested_stop(registration):
    if (Path(registration).resolve().parent/'STOP').exists():
        STOP.set()
    return STOP.is_set()


def isolated(config, registration, case, arm, work, phase='worker'):
    """One owned process group, independently bounded with wait4 CPU totals."""
    registration = Path(registration).resolve(); work = Path(work)
    limit = config['horizon_seconds'] if phase == 'worker' else config.get('posthoc_seconds',20)
    command = [config['python'], str(registration.parent/'frozen/anytime_worker.py'), phase,
               '--registration', str(registration), '--case', str(case['id']), '--work', str(work)]
    if phase == 'worker':
        command += ['--arm', arm]
    sent = None; killed = False; timed_out = False; child = None
    with (work/(phase+'.stdout')).open('a') as stdout, (work/(phase+'.stderr')).open('a') as stderr:
        started = time.monotonic(); deadline = started+limit
        if phase == 'worker':
            command += ['--started', str(started)]
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True,
            env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1'))
        try:
            while True:
                waited, status, usage = os.wait4(child.pid, os.WNOHANG)
                if waited:
                    break
                now = time.monotonic(); external = requested_stop(registration)
                if (external or now >= deadline) and sent is None:
                    timed_out = now >= deadline and not external
                    try: os.killpg(child.pid, signal.SIGINT)
                    except ProcessLookupError: pass
                    sent = now
                if sent is not None and now-sent >= config.get('save_grace_seconds',.5):
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    killed = True; _, status, usage = os.wait4(child.pid, 0); break
                time.sleep(.02)
            child.returncode = os.waitstatus_to_exitcode(status)
        finally:
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            if child.returncode is None:
                _, status, usage = os.wait4(child.pid, 0); child.returncode = os.waitstatus_to_exitcode(status)
    result_path = work/('result.json' if phase == 'worker' else 'posthoc-result.json')
    record = json.loads(result_path.read_text()) if result_path.is_file() else {'status': 'NO_CHECKPOINT'}
    return {'worker_record': record, 'parent_wall_seconds': time.monotonic()-started,
            'parent_cpu_seconds': usage.ru_utime+usage.ru_stime, 'started_monotonic': started,
            'deadline_monotonic': deadline, 'returncode': child.returncode,
            'deadline_censored': timed_out or time.monotonic() >= deadline,
            'forced_kill': killed, 'external_stop': requested_stop(registration), 'command': command}


def first_verified(record, horizon):
    value = record.get('first_verified_seconds')
    if value is not None and (not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not 0 <= value <= horizon):
        raise ValueError('Invalid or out-of-deadline first_verified_seconds')
    accepted = [c['accepted_elapsed_seconds'] for c in record.get('certificates',[]) if c.get('accepted')]
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not 0 <= v <= horizon for v in accepted):
        raise ValueError('Invalid online certificate acceptance time')
    expected = min(accepted) if accepted else None
    if value != expected:
        raise ValueError('First verified time disagrees with online certificates')
    return value


def _run(args):
    registration = Path(args.registration).resolve(); config = checked_registration(registration); out = registration.parent
    if args.workers not in (1,2):
        raise ValueError('Only one or two worker slots permitted')
    available = sorted(os.sched_getaffinity(0))
    if len(available) < args.workers:
        raise ValueError('Not enough available CPU cores for requested workers')
    os.sched_setaffinity(0, available[:args.workers])
    for case in {c['cnf']:c for c in config['cases']}.values():
        if sha(case['cnf']) != case['cnf_sha256']:
            raise ValueError('Original CNF changed')
    for key in ('machine_info','positive_control_result'):
        if config.get(key) and sha(config[key]) != config[key+'_sha256']:
            raise ValueError('Report input changed: '+key)
    database = out/'results.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        completed = list(db.execute('SELECT case_id,arm FROM trials WHERE complete=1'))
        if len(completed) != len(set(completed)):
            raise ValueError('Duplicate completed condition; refusing to select one')
        done = set(completed)
        db.execute('INSERT INTO events(timestamp,event,record) VALUES(?,?,?)',
                   (utc(),'START',json.dumps({'workers':args.workers,'affinity':available[:args.workers]})))
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:STOP.set())
    def one(case):
        for arm in case['condition_order']:
            if requested_stop(registration): return
            if (case['id'],arm) in done: continue
            work = Path(tempfile.mkdtemp(prefix=f'.trial-{case["id"]}-{arm}-', dir=out))
            initial = {'status':'RUNNING','case_id':case['id'],'family':case['family'],'arm':arm,'seed':case['seed'],
                       'work_directory':str(work),'initial_full_sha256':case['initial_full_sha256']}
            with LOCK, sqlite3.connect(database) as db:
                identifier = db.execute('INSERT INTO trials(case_id,arm,complete,record) VALUES(?,?,0,?)',
                                        (case['id'],arm,json.dumps(initial))).lastrowid
            search = isolated(config,registration,case,arm,work)
            report = dict(search['worker_record']); online = first_verified(report,config['horizon_seconds'])
            report.update(initial, status='SOLVED' if online is not None else 'TIME_LIMIT' if search['deadline_censored'] else report.get('status','NO_CHECKPOINT'),
                first_verified_seconds=online, parent_wall_seconds=search['parent_wall_seconds'],
                parent_cpu_seconds=search['parent_cpu_seconds'], parent_process=search,
                started_monotonic=search['started_monotonic'],deadline_monotonic=search['deadline_monotonic'],
                observed_seconds=min(search['parent_wall_seconds'],config['horizon_seconds']),
                censor_seconds=min(search['parent_wall_seconds'],config['horizon_seconds']),
                deadline_censored=search['deadline_censored'], external_stop=search['external_stop'],
                cpu_accounting_lower_bound=search['forced_kill'] or search['returncode']<0,
                cpu_accounting_flag=search['forced_kill'] or search['returncode']<0)
            # This file is the preserved input to posthoc; the online record is
            # immutable with respect to any subsequently found valid geometry.
            atomic(work/'search-result.json',report)
            if not requested_stop(registration):
                post = isolated(config,registration,case,arm,work,phase='posthoc')
                report.update(posthoc=post['worker_record'].get('audits',[]),posthoc_status=post['worker_record'].get('status'),
                    posthoc_cpu_seconds=post['parent_cpu_seconds'],
                    posthoc_wall_seconds=post['parent_wall_seconds'],posthoc_process=post,
                    posthoc_cpu_accounting_lower_bound=post['forced_kill'] or post['returncode']<0,
                    external_stop=search['external_stop'] or post['external_stop'])
            else:
                report.update(posthoc=[],posthoc_status='SKIPPED_EXTERNAL_STOP',posthoc_cpu_seconds=0,posthoc_wall_seconds=0,external_stop=True)
            files = [(str(p.relative_to(work)),p.read_bytes()) for p in work.rglob('*') if p.is_file()]
            with LOCK, sqlite3.connect(database) as db:
                db.execute('UPDATE trials SET complete=?,record=? WHERE id=?',
                           (not report['external_stop'],json.dumps(report),identifier))
                db.executemany('INSERT INTO artifacts VALUES(?,?,?,?)',
                    [(identifier,name,hashlib.sha256(data).hexdigest(),zlib.compress(data,3)) for name,data in files])
            if online is not None:
                success = out/'successes'/f'trial-{identifier:05}-{case["id"]}-{arm}'
                success.parent.mkdir(exist_ok=True); shutil.copytree(work,success); atomic(success/'trial.json',report)
            shutil.rmtree(work)
            print(json.dumps({'case':case['id'],'arm':arm,'first_verified_seconds':online,'status':report['status']}),flush=True)
    failure = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(one,case) for case in config['cases']]
        for future in concurrent.futures.as_completed(futures):
            try: future.result()
            except Exception as error: failure = error; STOP.set()
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO events(timestamp,event,record) VALUES(?,?,?)',
                   (utc(),'STOP' if STOP.is_set() else 'FINISH',json.dumps({'error':repr(failure) if failure else None})))
    summary = summarize(registration)
    with sqlite3.connect(database) as db: db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    if failure: raise failure
    if summary['complete'] and not requested_stop(registration):
        integrity = verify(registration); atomic(out/'integrity.json',integrity)
        if integrity['status'] != 'PASSED': raise ValueError('Final integrity is not PASSED')
        report = Path(config['report_output'])
        if report.exists():
            raise ValueError('Final report exists; refusing overwrite: '+str(report))
        command = [config['report_python'],str(out/'frozen/anytime_report.py'),'--registration',str(registration),'--out',str(report)]
        for key in ('machine_info','positive_control_result'):
            if config.get(key): command += ['--'+key.replace('_','-'),config[key]]
        report_process = bounded_report(command,registration,config.get('report_seconds',300))
        atomic(out/'report-process.json',report_process)
        if report_process['external_stop']: return
        if report_process['returncode'] or report_process['deadline_censored']:
            raise RuntimeError('Final report did not finish successfully; preserved partial output and report.log')


def bounded_report(command, registration, seconds):
    """Postprocessing is outside study clocks but still owns bounded cleanup."""
    out = Path(registration).resolve().parent; start = time.monotonic(); sent = None; timed = False
    with (out/'report.log').open('a') as log:
        child = subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'))
        try:
            while True:
                waited,status,usage = os.wait4(child.pid,os.WNOHANG)
                if waited: break
                now = time.monotonic()
                if (requested_stop(registration) or now-start>=seconds) and sent is None:
                    timed = now-start>=seconds
                    try: os.killpg(child.pid,signal.SIGINT)
                    except ProcessLookupError: pass
                    sent = now
                if sent is not None and now-sent>=1:
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    _,status,usage = os.wait4(child.pid,0); break
                time.sleep(.05)
            child.returncode = os.waitstatus_to_exitcode(status)
        finally:
            try: os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            if child.returncode is None:
                _,status,usage = os.wait4(child.pid,0); child.returncode = os.waitstatus_to_exitcode(status)
    return {'command':command,'returncode':child.returncode,'wall_seconds':time.monotonic()-start,
            'cpu_seconds':usage.ru_utime+usage.ru_stime,'deadline_censored':timed,
            'external_stop':requested_stop(registration),'outside_primary_clock':True}


def run(args):
    lock = (Path(args.registration).resolve().parent/'run.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); return _run(args)
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN); lock.close()


def read_records(registration):
    registration = Path(registration).resolve(); config = json.loads(registration.read_text())
    database = registration.parent/'results.sqlite'
    if not database.exists(): return config, []
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        records = [(i,c,a,bool(complete),json.loads(r)) for i,c,a,complete,r in db.execute(
            'SELECT id,case_id,arm,complete,record FROM trials ORDER BY id')]
    return config,records


def summarize(registration):
    config,records = read_records(registration)
    rows = [r for _,_,_,complete,r in records if complete]
    keys = [(r['case_id'],r['arm']) for r in rows]
    if len(keys) != len(set(keys)): raise ValueError('Duplicate complete condition')
    registered = sum(len(c['condition_order']) for c in config['cases'])
    result = {'registered_trials':registered,'completed_trials':len(rows),'complete':len(rows)==registered,
        'attempted_trials':len(records),'incomplete_attempts':sum(not c for _,_,_,c,_ in records),
        'milestones':config['milestones'],'horizon_seconds':config['horizon_seconds'],'families':{},
        'parent_cpu_seconds_all_attempts':sum(r.get('parent_cpu_seconds',0) for _,_,_,_,r in records),
        'posthoc_cpu_seconds_all_attempts':sum(r.get('posthoc_cpu_seconds',0) for _,_,_,_,r in records)}
    for family, arms in config['family_arms'].items():
        groups = {}
        for arm in arms:
            selected = [r for r in rows if r['family']==family and r['arm']==arm]
            times = [first_verified(r,config['horizon_seconds']) for r in selected]
            groups[arm] = {'trials':len(selected),'verified':sum(t is not None for t in times),
                'milestones':{str(t):sum(v is not None and v<=t for v in times) for t in config['milestones']},
                'parent_cpu_seconds':sum(r.get('parent_cpu_seconds',0) for r in selected),
                'parent_wall_seconds':sum(r.get('parent_wall_seconds',0) for r in selected),
                'posthoc_cpu_seconds':sum(r.get('posthoc_cpu_seconds',0) for r in selected),
                'posthoc_wall_seconds':sum(r.get('posthoc_wall_seconds',0) for r in selected),
                'deadline_censored':sum(r.get('deadline_censored',False) for r in selected),
                'status_counts':dict(Counter(r.get('status') for r in selected))}
        result['families'][family] = {'registered_targets':sum(c['family']==family for c in config['cases']),'arms':groups}
    atomic(Path(registration).resolve().parent/'summary.json',result); return result


def verify(registration):
    config = checked_registration(registration); _,records = read_records(registration)
    expected = {(c['id'],a):c for c in config['cases'] for a in c['condition_order']}; done = set(); artifact_count = 0
    partial_targets = {}; accepted_count = 0
    with sqlite3.connect((Path(registration).resolve().parent/'results.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        for identifier,case_id,arm,complete,record in records:
            if (case_id,arm) not in expected: raise ValueError('Unregistered trial')
            case = expected[(case_id,arm)]
            if complete:
                if (case_id,arm) in done: raise ValueError('Duplicate complete condition')
                done.add((case_id,arm))
                if record['seed'] != case['seed'] or record['initial_full_sha256'] != case['initial_full_sha256']:
                    raise ValueError('Case/seed/full target mismatch')
                first_verified(record,config['horizon_seconds'])
            artifacts = {}; contents = {}
            for name,digest,data in db.execute('SELECT name,sha256,data FROM artifacts WHERE trial_id=?',(identifier,)):
                if Path(name).is_absolute() or '..' in Path(name).parts: raise ValueError('Unsafe artifact path')
                unpacked = zlib.decompress(data)
                if hashlib.sha256(unpacked).hexdigest() != digest: raise ValueError('Artifact hash mismatch')
                artifacts[name] = digest; contents[name] = unpacked; artifact_count += 1
            if 'full.or' in artifacts and artifacts['full.or'] != case['initial_full_sha256']:
                raise ValueError('Preserved full target differs from registered input')
            partial = record.get('initial_target_sha256')
            if partial is not None:
                if artifacts.get('initial.or') != partial:
                    raise ValueError('Preserved initial target differs from recorded input')
                if complete and case_id in partial_targets and partial_targets[case_id] != partial:
                    raise ValueError('Initial flippability target differs across arms')
                if complete: partial_targets[case_id] = partial
            for certificate in record.get('certificates',[]):
                if not certificate.get('accepted'): continue
                artifact = certificate['certificate_artifact']
                if artifacts.get(artifact) != certificate['certificate_sha256']:
                    raise ValueError('Accepted online certificate not preserved/hash matched')
                proof = json.loads(contents[artifact]); accepted_count += 1
                if proof.get('family') != case['family'] or proof.get('n') != case['n'] or proof.get('valid_geometry') is not True:
                    raise ValueError('Accepted proof has wrong family/geometry validity')
                if proof.get('general_position') is not True or proof.get('duplicate_pairs') != 0 or proof.get('collinear_triples') != 0 or proof.get('convex_caps') != 0:
                    raise ValueError('Accepted proof violates GP or cap gates')
                geo = proof.get('geometry',{})
                if geo != certificate.get('geometry') or geo.get('valid') is not True:
                    raise ValueError('Preserved proof differs from online geometry reading')
                if case['family'] == 'symmetry19':
                    histogram = geo.get('interior_histogram',[])
                    if len(histogram) != 14 or histogram[0] or histogram[3] or geo.get('six_subsets_checked') != math.comb(19,6):
                        raise ValueError('Accepted19 proof lacks full forbidden-hexagon check')
                elif (geo.get('convex_gons') != 0 or geo.get('empty_holes') != 0 or
                      geo.get('gon_subsets_checked') != (math.comb(case['n'],case['gon']) if case['gon'] else 0) or
                      geo.get('hole_subsets_checked') != (math.comb(case['n'],case['hole']) if case['hole'] else 0)):
                    raise ValueError('Accepted polygon proof lacks full enumeration')
                absolute = certificate.get('accepted_timestamp_monotonic'); relative = certificate.get('accepted_elapsed_seconds')
                if (not isinstance(absolute,(int,float)) or not math.isfinite(absolute) or
                        not record['started_monotonic'] <= absolute <= record['deadline_monotonic'] or
                        abs((absolute-record['started_monotonic'])-relative) > 1e-6 or
                        not proof.get('certificate_validated_monotonic',math.inf) <= absolute):
                    raise ValueError('Accepted certificate timestamp violates total-wall deadline')
                parent = Path(artifact).parent
                for filename,key in [('points.pts','integer_points_sha256'),('snapshot.real','snapshot_sha256')]:
                    if artifacts.get(str(parent/filename)) != proof.get(key):
                        raise ValueError('Accepted proof witness/snapshot not preserved')
    return {'status':'PASSED' if done==set(expected) else 'PENDING','integrity_ok':True,
            'completed_trials':len(done),'registered_trials':len(expected),'artifacts_checked':artifact_count,
            'accepted_certificates_checked':accepted_count,'matched_partial_targets':len(partial_targets),
            'registration_sha256':sha(registration),'checked_utc':utc(),'SAT_calls':0,'geometry_reruns':0}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode',required=True)
    q = sub.add_parser('register')
    for name in ('nineteen-registration','paper-registration','output','report-output'):
        q.add_argument('--'+name,required=True)
    q.add_argument('--seed',type=int,default=709071); q.add_argument('--machine-info'); q.add_argument('--positive-control-result'); q.set_defaults(fn=register)
    q = sub.add_parser('run'); q.add_argument('--registration',required=True); q.add_argument('--workers',type=int,choices=(1,2),default=2); q.set_defaults(fn=run)
    q = sub.add_parser('summarize'); q.add_argument('--registration',required=True); q.set_defaults(fn=lambda a:print(json.dumps(summarize(a.registration))))
    q = sub.add_parser('verify'); q.add_argument('--registration',required=True); q.set_defaults(fn=lambda a:print(json.dumps(verify(a.registration))))
    args = parser.parse_args(); args.fn(args)


if __name__ == '__main__': main()
