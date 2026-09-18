#!/usr/bin/env python3
"""Prospective five-arm, native-budget scaling comparison on four paper families.

Registration/inventory never run a SAT or geometric search. `run` is explicit.
Final checkpoint is primary; any saved checkpoint is a secondary endpoint.
Feedback is a compound retarget + warm restart, not a pure SAT ablation.
Only one or two single-core slots, including preparation and exact auditing.
"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import itertools
import json
import math
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
FAMILIES = {'mixed23': (23,7,6,0), 'holes29': (29,0,6,0),
            'gons32': (32,7,0,0), 'caps26': (26,7,0,5)}
ARMS = ('original', 'v6_plain', 'v6_line10', 'v6_line10_pair10', 'v6_feedback')
STOP, LOCK = threading.Event(), threading.Lock()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, data):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n'); tmp.replace(path)


def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name, path)
    result=importlib.util.module_from_spec(spec); sys.modules[name]=result
    spec.loader.exec_module(result); return result


def canonical_target(path, n, auditor):
    records=auditor.read_target(path, n)
    if len(records)!=math.comb(n,3) or any(sign==0 for _,sign in records):
        raise ValueError('Expected a complete uniform primary orientation model: '+str(path))
    model=[0]*len(records)
    for triple,sign in records:
        rank=auditor.colex_rank(triple); model[rank-1]=rank*sign
    digest=hashlib.sha256(bytes([n])+bytes(lit>0 for lit in model)).hexdigest()
    return model,digest


def inventory(root=ROOT):
    auditor=load_module(root/'benchmarks/compare19_audit.py', 'families_inventory_audit')
    canonicalizer=load_module(root/'benchmarks/compare19_types.py', 'families_inventory_types')
    groups={family: [] for family in FAMILIES}; excluded=[]
    # Fixed source priority: whole overnight corpus first, then the earlier
    # registered fresh corpus. We never inspect native-search outcomes.
    candidates=[]
    for path in sorted((root/'improvements/benchmarks/overnight/runs').glob('*/case_result.json')):
        data=json.loads(path.read_text()); case=data['case']
        if case['problem'] not in FAMILIES: continue
        if data.get('sat',{}).get('returncode')!=10:
            excluded.append({'id':case['id'],'reason':'source_SAT_not_successful'}); continue
        candidates.append((case, path.parent/'target.or', data['orientation_sha256'], str(path)))
    fallback=root/'improvements/benchmarks/all_fresh_v3_manifest.json'
    for row in json.loads(fallback.read_text())['cases']:
        case=dict(row); case['cnf']=row.get('cnf', row.get('generation_result',{}).get('cnf'))
        candidates.append((case,root/row['orientation'],row['sha256'],str(fallback)))
    seen={family:set() for family in FAMILIES}
    for row,path,digest,source in candidates:
        family=row['problem']; n,gon,hole,cap=FAMILIES[family]
        if sha(path)!=digest: raise ValueError('Source orientation hash changed: '+str(path))
        model,full_primary=canonical_target(path,n,auditor)
        if full_primary in seen[family]:
            excluded.append({'id':row['id'],'reason':'duplicate_full_primary_model','full_primary_sha256':full_primary}); continue
        seen[family].add(full_primary)
        canonical=canonicalizer.canonicalize(path.read_text())
        cnf=(root/row['cnf']).resolve()
        groups[family].append({'source_id':row['id'],'family':family,'n':n,'gon':gon,'hole':hole,'cap':cap,
            'orientation':str(path.resolve()),'orientation_sha256':digest,'full_primary_sha256':full_primary,
            'canonical_sha256':canonical['canonical_sha256'],'canonical_signs':canonical['canonical_signs'],
            'canonical_supported':canonical['supported'],
            'cnf':str(cnf),'cnf_sha256':sha(cnf),'primary_model':model,'source_record':source})
    return groups,excluded


def register(args):
    if args.targets<1 or not args.budgets or any(not math.isfinite(b) or b<=0 for b in args.budgets) or len(set(args.budgets))!=len(args.budgets):
        raise ValueError('Positive target count and distinct finite positive native budgets required')
    groups,excluded=inventory()
    shortages={f:len(g) for f,g in groups.items() if len(g)<args.targets}
    if shortages: raise ValueError(f'Insufficient pre-existing unique targets: {shortages}; no automatic SAT generation')
    out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=False)
    frozen=out/'frozen'; frozen.mkdir()
    paths={}
    for key,path in {'original':ROOT/'improvements/localizer/localizer_baseline',
                     'improved':ROOT/'improvements/localizer/localizer_v6',
                     'verifier':ROOT/'direct/verify_big'}.items():
        destination=frozen/key; shutil.copy2(path,destination); paths[key]=str(destination)
    for path in (Path(__file__),ROOT/'benchmarks/compare19_audit.py',ROOT/'benchmarks/compare19_types.py',ROOT/'flippable2.py',ROOT/'sat_orient_conversion.py'):
        shutil.copy2(path,frozen/path.name)
    # Reuse the already registered target-margin policy without modifying it.
    shutil.copy2(ROOT/'benchmarks/pilot_20260906/frozen/feedback.py',frozen/'feedback.py')
    rng=random.Random(args.seed); cases=[]
    for family in FAMILIES:
        for row in groups[family][:args.targets]:
            case=dict(row); case['id']=len(cases); case['seed']=args.seed+case['id']
            conditions=[{'arm':arm,'budget':budget} for budget in args.budgets for arm in ARMS]
            rng.shuffle(conditions); case['condition_order']=conditions; cases.append(case)
    rng.shuffle(cases)
    config={'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'root':str(ROOT),
        'python':str(ROOT/'direct/vendor/venv/bin/python'),'cases':cases,'paths':paths,
        'frozen_sha256':{p.name:sha(p) for p in frozen.iterdir()},'arms':list(ARMS),'budgets':args.budgets,
        'targets_per_family':args.targets,'seed':args.seed,'prepare_seconds':120,'trial_overhead_cap':120,
        'native_save_grace':.75,'feedback_seconds':10,'audit_seconds':180,'workers_max':2,'initial_flippability':True,
        'caps_ordered_x':False,'source_available':{f:len(g) for f,g in groups.items()},'excluded_source_records':excluded,
        'primary_endpoint':'Exact actual geometry of FINAL native checkpoint only; general position and the actual 5-cap condition mandatory.',
        'secondary_endpoint':'Any saved checkpoint has exact valid geometry.',
        'budget_scope':'Each allowance is native wall time, with fresh starts at every budget. Initial preparation, SAT feedback, flippability and auditing are separately measured. Not equal whole-trial cost.',
        'seed_scope':'Same case seed for every arm and fresh budget. Feedback warm restart uses the same case seed, and no state carries between budget levels.',
        'attribution':'Original versus v6_plain is a native-package comparison, not a cache-only ablation. Line/pair treatments add only those optional flags. Feedback additionally splits the allowance and warm-restarts: a compound strategy, not pure SAT feedback.',
        'caps_scope':'--ordered-x is OFF in ALL five arms, including v6. This comparison omits that later cap-specific capability; exact geometric cap checking is nevertheless mandatory.',
        'selection':'First unique complete primary models in fixed source order, independent of native outcomes. Reused corpus, not unseen data. SAT generation is outside this realization-only comparison.',
        'no_search_launched_by_registration':True}
    config['selected_order_type_counts']={family:len({c['canonical_signs'] for c in cases
        if c['family']==family and c['canonical_supported']}) for family in FAMILIES}
    config['unsupported_canonical_models']={family:sum(not c['canonical_supported'] for c in cases
        if c['family']==family) for family in FAMILIES}
    if any(config['unsupported_canonical_models'].values()) or any(
            count!=args.targets for count in config['selected_order_type_counts'].values()):
        raise ValueError('Selected targets are not independently established distinct order types; registration not written')
    atomic(out/'registration.json',config)
    print(json.dumps({'registration':str(out/'registration.json'),'cases':len(cases),
        'trials':len(cases)*len(ARMS)*len(args.budgets),
        'maximum_native_core_hours':len(cases)*len(ARMS)*sum(args.budgets)/3600}))


def native_command(config,arm,target,output,seed,seconds,warm=None):
    command=[config['paths']['original' if arm=='original' else 'improved'],str(target),
        '-t','1','-i','10','-r','30000','-s',str(seed),'-f','','-c','','-o',str(output)]
    if arm!='original':
        command+=['-T',str(seconds),'-q']
        if arm in ('v6_line10','v6_line10_pair10'): command+=['--line-every','10']
        if arm=='v6_line10_pair10': command+=['--pair-every','10']
        if warm is not None: command+=['-w',str(warm)]
    if len(str(output).encode())>=250: raise ValueError('Output path exceeds upstream fixed filename buffer')
    return command


def native(config,arm,target,output,seed,seconds,warm=None):
    command=native_command(config,arm,target,output,seed,seconds,warm)
    before=resource.getrusage(resource.RUSAGE_CHILDREN); started=time.monotonic()
    interrupted=killed=False
    with output.with_suffix('.stdout').open('w') as stdout,output.with_suffix('.stderr').open('w') as stderr:
        child=subprocess.Popen(command,stdout=stdout,stderr=stderr)
        try: code=child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            interrupted=True; child.send_signal(signal.SIGINT)
            try: code=child.wait(timeout=config['native_save_grace'])
            except subprocess.TimeoutExpired: killed=True; child.kill(); code=child.wait()
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'file':output.name,'command':command,'native_budget_seconds':seconds,
        'native_wall_seconds':time.monotonic()-started,
        'native_cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
        'budget_signal':interrupted,'forced_kill':killed,'returncode':code,'output_saved':output.is_file(),
        'seed':seed,'warm_start':warm is not None}


def worker(args):
    config=json.loads(Path(args.registration).read_text()); frozen=Path(args.registration).parent/'frozen'
    sys.path.insert(0,str(frozen))
    case=next(c for c in config['cases'] if c['id']==args.case); work=Path(args.work)
    report={'status':'STARTED','stages':[],'feedback':[]}; started=time.monotonic()
    def save():
        report['worker_wall_seconds']=time.monotonic()-started; atomic(work/'result.json',report)
    try:
        if args.arm=='audit':
            auditor=load_module(frozen/'compare19_audit.py','families_audit_worker')
            request=json.loads((work/'request.json').read_text()); report['audits']=[]
            report['status']='AUDITING'; save()
            for stage in request['stages']:
                path=Path(request['native_directory'])/stage['file']
                if path.is_file():
                    try:
                        item=audit_family(path,request['full_target'],case,work/path.stem,config,auditor)
                        item['checkpoint']=stage['file']; report['audits'].append(item)
                    except Exception as error:
                        report['audits'].append({'checkpoint':stage['file'],'valid_geometry':False,'audit_error':repr(error)})
                    save()
            report['status']='AUDITED'; save(); return
        from flippable2 import FlippabilityChecker
        from sat_orient_conversion import get_orientations,inspect_realization
        from feedback import core_guided_feedback,orientation_margins
        if args.arm=='prepare':
            begin=time.monotonic()
            with FlippabilityChecker(Path(case['cnf']).read_text()) as checker:
                flips,partial=checker.check('v '+' '.join(map(str,case['primary_model']))+' 0')
                report.update(status='PREPARED',partial_model=partial,flippables=sorted(flips),
                              flippability_seconds=time.monotonic()-begin,flippability_stats=checker.last_stats)
            save(); return
        arm,budget=args.arm.rsplit('@',1); budget=float(budget)
        if arm not in ARMS or budget not in config['budgets']: raise ValueError('Unregistered condition')
        if arm!='v6_feedback':
            output=work/'stage0.real'; report['final_checkpoint']=output.name
            report['stages'].append(native(config,arm,work/'initial.or',output,case['seed'],budget))
            report['status']='FINISHED' if output.is_file() else 'MISSING_OUTPUT'; save(); return
        first=work/'stage0.real'; second=work/'stage1.real'
        report['final_checkpoint']=second.name
        report['stages'].append(native(config,arm,work/'initial.or',first,case['seed'],budget/2)); save()
        target=work/'initial.or'
        if first.is_file():
            begin=time.monotonic()
            inspected=inspect_realization(target,first,case['n'])
            if inspected['sat_model'] is not None:
                with FlippabilityChecker(Path(case['cnf']).read_text()) as checker:
                    settings={'feedback_core_choice':'target_margin','feedback_max_solves':128,
                        'feedback_seconds':config['feedback_seconds'],'feedback_conflict_budget':2000,
                        'feedback_max_relaxed':128}
                    repaired,stats=core_guided_feedback(checker.solver,inspected['sat_model'],settings,
                        case['seed'],inspected['bad_vars'],orientation_margins(first,case['n']))
                    if repaired is not None:
                        flips,partial=checker.check('v '+' '.join(map(str,repaired))+' 0')
                        target=work/'repaired.or'; target.write_text(get_orientations(partial,case['n']))
                        stats['new_flippables']=len(flips)
                    stats['total_feedback_wall_seconds']=time.monotonic()-begin; report['feedback'].append(stats)
            else: report['feedback'].append({'status':'SKIPPED_NON_GP','total_feedback_wall_seconds':time.monotonic()-begin})
        else: report['feedback'].append({'status':'SKIPPED_MISSING_CHECKPOINT','total_feedback_wall_seconds':0})
        save()
        report['stages'].append(native(config,arm,target,second,case['seed'],budget/2,first if first.is_file() else None))
        report['status']='FINISHED' if second.is_file() else 'MISSING_OUTPUT'; save()
    except BaseException as error:
        report.update(status='ERROR',error=repr(error)); save(); raise


def isolated(config,registration,case,condition,work,limit):
    command=[config['python'],str(Path(registration).parent/'frozen/compare_families.py'),'worker',
             '--registration',str(registration),'--case',str(case['id']),'--arm',condition,'--work',str(work)]
    start=time.monotonic(); timed_out=False
    with (work/'worker.stdout').open('w') as stdout,(work/'worker.stderr').open('w') as stderr:
        child=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
        while True:
            pid,status,usage=os.wait4(child.pid,os.WNOHANG)
            if pid: break
            if STOP.is_set() or time.monotonic()-start>=limit:
                timed_out=not STOP.is_set()
                try: os.killpg(child.pid,signal.SIGINT)
                except ProcessLookupError: pass
                until=time.monotonic()+1
                while time.monotonic()<until:
                    pid,status,usage=os.wait4(child.pid,os.WNOHANG)
                    if pid: break
                    time.sleep(.02)
                if not pid:
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    _,status,usage=os.wait4(child.pid,0)
                break
            time.sleep(.03)
        child.returncode=os.waitstatus_to_exitcode(status)
        try: os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError: pass
    report=json.loads((work/'result.json').read_text()) if (work/'result.json').is_file() else {'status':'NO_CHECKPOINT','stages':[]}
    report.update(parent_wall_seconds=time.monotonic()-start,parent_cpu_seconds=usage.ru_utime+usage.ru_stime,
        returncode=child.returncode,overhead_watchdog=timed_out,externally_interrupted=STOP.is_set(),
        cpu_accounting_flag=child.returncode<0)
    return report


def audit_family(real,full_target,case,directory,config,auditor):
    directory.mkdir(parents=True)
    points=auditor.read_points(real,case['n']); target=auditor.read_target(full_target,case['n'])
    pts=directory/'points.pts'; pts.write_text(str(len(points))+'\n'+''.join(f'{x} {y}\n' for x,y in points))
    command=[config['paths']['verifier'],'--input',str(pts),'--gon',str(case['gon']),'--hole',str(case['hole'])]
    start=time.monotonic(); process=subprocess.run(command,text=True,capture_output=True,timeout=120)
    if process.returncode not in (0,1): raise RuntimeError('Exact polygon verifier failed: '+process.stderr)
    geometry=json.loads(process.stdout)
    if geometry['n']!=case['n'] or geometry['gon_subsets_checked']!=(math.comb(case['n'],case['gon']) if case['gon'] else 0) or geometry['hole_subsets_checked']!=(math.comb(case['n'],case['hole']) if case['hole'] else 0):
        raise RuntimeError('Incomplete polygon enumeration')
    collinear=sum(auditor.cross(*t)==0 for t in itertools.combinations(points,3))
    duplicates=sum(a==b for a,b in itertools.combinations(points,2))
    if geometry['collinear_triples']!=collinear: raise RuntimeError('GP checker disagreement')
    caps=0
    if case['cap']:
        ordered=sorted(points); k=case['cap']
        caps=sum(all(p[i][0]<p[i+1][0] for i in range(k-1)) and
                 all(auditor.cross(p[i],p[i+1],p[i+2])<0 for i in range(k-2))
                 for p in itertools.combinations(ordered,k))
    geometry.update(convex_caps=caps,duplicate_pairs=duplicates)
    valid=not(collinear or duplicates or geometry['convex_gons'] or geometry['empty_holes'] or caps)
    geometry['valid']=valid
    report={'valid_geometry':valid,'geometry':geometry,'general_position':not(collinear or duplicates),
        'orientation_violations':sum(auditor.sign(auditor.cross(*(points[i-1] for i in triple)))!=s for triple,s in target),
        'constraint_count':len(target),'forbidden_polygons':geometry['convex_gons']+geometry['empty_holes']+caps,
        'integer_points':str(pts),'integer_points_sha256':sha(pts),'real_sha256':sha(real),
        'source_full_target_sha256':sha(full_target),'numeric_cnf':{'status':'NOT_CHECKED_GEOMETRY_INVALID','satisfiable':None}}
    if valid:
        # CNF is secondary: label-only radial normalization handles the first
        # three paper formulas' symmetry breaking without changing geometry.
        from sat_orient_conversion import radial_relabel
        source=real
        if case['family']!='caps26':
            source=directory/'radial.real'; radial_relabel(real,source,case['n'])
        model=auditor.orientation_model(auditor.read_points(source,case['n']))
        report['numeric_cnf']=auditor.cnf_check(model,case['cnf'],None,directory,'geometry')
    report['audit_wall_seconds']=time.monotonic()-start
    atomic(directory/'certificate.json',report); return report


SCHEMA='''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS preparation(case_id INTEGER PRIMARY KEY, record TEXT);
CREATE TABLE IF NOT EXISTS trials(id INTEGER PRIMARY KEY,case_id INTEGER,arm TEXT,budget REAL,complete INTEGER,record TEXT);
CREATE TABLE IF NOT EXISTS artifacts(trial_id INTEGER,name TEXT,sha256 TEXT,data BLOB,PRIMARY KEY(trial_id,name));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,timestamp TEXT,event TEXT,record TEXT);
'''


def unfinished_cases(cases, done, max_cases=None):
    """Scheduling only: skip completed cases before applying a batch limit."""
    if max_cases is not None and max_cases<1:
        raise ValueError('--max-cases must be a positive integer')
    pending=[case for case in cases if any(
        (case['id'],c['arm'],c['budget']) not in done for c in case['condition_order'])]
    return pending if max_cases is None else pending[:max_cases]


def _run(args):
    registration=Path(args.registration).resolve(); config=json.loads(registration.read_text()); out=registration.parent
    if args.workers not in (1,2): raise ValueError('Only one or two slots permitted')
    for file,digest in config['frozen_sha256'].items():
        if sha(out/'frozen'/file)!=digest: raise ValueError('Frozen file changed: '+file)
    for case in config['cases']:
        if sha(case['cnf'])!=case['cnf_sha256'] or sha(case['orientation'])!=case['orientation_sha256']:
            raise ValueError('Registered source changed')
    allowed=sorted(os.sched_getaffinity(0)); os.sched_setaffinity(0,allowed[:args.workers])
    sys.path.insert(0,str(out/'frozen'))
    from sat_orient_conversion import get_orientations
    database=out/'results.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        done={(a,b,c) for a,b,c in db.execute('SELECT case_id,arm,budget FROM trials WHERE complete=1')}
        prepared={i:json.loads(r) for i,r in db.execute('SELECT case_id,record FROM preparation')}
        scheduled=unfinished_cases(config['cases'],done,args.max_cases)
        db.execute('INSERT INTO events(timestamp,event,record) VALUES(?,?,?)',
            (time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'START',json.dumps({'workers':args.workers,'affinity':allowed[:args.workers],
                'max_cases':args.max_cases,'scheduled_case_ids':[c['id'] for c in scheduled]})))
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,lambda *_:STOP.set())
    def one(case):
        if STOP.is_set() or all((case['id'],c['arm'],c['budget']) in done for c in case['condition_order']): return
        preparation=prepared.get(case['id'])
        if preparation is None:
            work=Path(tempfile.mkdtemp(prefix=f'.prepare-{case["id"]}-',dir=out))
            preparation=isolated(config,registration,case,'prepare',work,config['prepare_seconds'])
            if STOP.is_set(): return
            if preparation['status']!='PREPARED':
                if not preparation['overhead_watchdog']: raise RuntimeError('Preparation failed; retained '+str(work))
                preparation.update(partial_model=case['primary_model'],flippables=[],fallback='Full target after bounded preparation timeout')
            with LOCK,sqlite3.connect(database) as db:
                db.execute('INSERT INTO preparation VALUES(?,?)',(case['id'],json.dumps(preparation)))
            shutil.rmtree(work)
        initial=get_orientations(preparation['partial_model'],case['n'])
        full=get_orientations(case['primary_model'],case['n'])
        for condition in case['condition_order']:
            arm,budget=condition['arm'],condition['budget']
            if STOP.is_set(): return
            if (case['id'],arm,budget) in done: continue
            work=Path(tempfile.mkdtemp(prefix=f'.trial-{case["id"]}-{arm}-{budget:g}-',dir=out))
            (work/'initial.or').write_text(initial); (work/'full.or').write_text(full)
            # Persist the recoverable work location BEFORE starting a process.
            initial_record={'status':'RUNNING','case_id':case['id'],'family':case['family'],
                            'arm':arm,'budget':budget,'work_directory':str(work)}
            with LOCK,sqlite3.connect(database) as db:
                cursor=db.execute('INSERT INTO trials(case_id,arm,budget,complete,record) VALUES(?,?,?,?,?)',
                                  (case['id'],arm,budget,0,json.dumps(initial_record)))
                identifier=cursor.lastrowid
            report=isolated(config,registration,case,f'{arm}@{budget}',work,budget+config['trial_overhead_cap'])
            audit_work=work/'audit-worker'; audit_work.mkdir()
            atomic(audit_work/'request.json',{'stages':report.get('stages',[]),
                'native_directory':str(work),'full_target':str(work/'full.or')})
            audit_report=isolated(config,registration,case,'audit',audit_work,config['audit_seconds'])
            audits=audit_report.get('audits',[])
            if audit_report.get('status')!='AUDITED':
                audits.append({'checkpoint':None,'valid_geometry':False,'audit_error':'Audit worker failed or was interrupted',
                               'audit_status':audit_report.get('status')})
            final=next((r for r in audits if r['checkpoint']==report.get('final_checkpoint')), {})
            report.update(case_id=case['id'],source_id=case['source_id'],canonical_sha256=case['canonical_sha256'],
                full_primary_sha256=case['full_primary_sha256'],
                family=case['family'],arm=arm,budget=budget,seed=case['seed'],
                initial_target_sha256=hashlib.sha256(initial.encode()).hexdigest(),
                primary_valid_geometry=bool(final.get('valid_geometry')),
                any_saved_valid_geometry=any(r.get('valid_geometry') for r in audits),
                audits=audits,posthoc_wall_seconds=audit_report['parent_wall_seconds'],
                audit_cpu_seconds=audit_report['parent_cpu_seconds'],audit_watchdog=audit_report['overhead_watchdog'],
                audit_status=audit_report.get('status'),audit_process=audit_report,
                externally_interrupted=report['externally_interrupted'] or audit_report['externally_interrupted'])
            files=[(str(p.relative_to(work)),p.read_bytes()) for p in work.rglob('*') if p.is_file()]
            with LOCK,sqlite3.connect(database) as db:
                db.execute('UPDATE trials SET complete=?,record=? WHERE id=?',
                    (not report['externally_interrupted'],json.dumps(report),identifier))
                db.executemany('INSERT INTO artifacts VALUES(?,?,?,?)',
                    [(identifier,name,hashlib.sha256(data).hexdigest(),zlib.compress(data,3)) for name,data in files])
            if report['any_saved_valid_geometry']:
                destination=out/'successes'/f'trial-{identifier:05}-{arm}'
                destination.parent.mkdir(exist_ok=True); shutil.copytree(work,destination)
                atomic(destination/'trial.json',report)
            shutil.rmtree(work)
            print(json.dumps({'case':case['id'],'family':case['family'],'arm':arm,'budget':budget,
                'valid_final':report['primary_valid_geometry'],'valid_any':report['any_saved_valid_geometry'],
                'status':report['status']}),flush=True)
    failure=None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(one,case) for case in scheduled]
        for future in concurrent.futures.as_completed(futures):
            try: future.result()
            except Exception as error: failure=error; STOP.set()
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO events(timestamp,event,record) VALUES(?,?,?)',
            (time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'STOP' if STOP.is_set() else 'FINISH',
             json.dumps({'error':repr(failure) if failure else None})))
    summarize(registration)
    with sqlite3.connect(database) as db: db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    if failure: raise failure


def run(args):
    lock=(Path(args.registration).resolve().parent/'run.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _run(args)
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN); lock.close()


def summarize(registration):
    registration=Path(registration); config=json.loads(registration.read_text())
    with sqlite3.connect(registration.parent/'results.sqlite') as db:
        rows=[json.loads(r) for (r,) in db.execute('SELECT record FROM trials WHERE complete=1 ORDER BY id')]
        preparations=[json.loads(r) for (r,) in db.execute('SELECT record FROM preparation')]
        attempted=db.execute('SELECT COUNT(*) FROM trials').fetchone()[0]
        incomplete=db.execute('SELECT COUNT(*) FROM trials WHERE complete=0').fetchone()[0]
    latest={(r['case_id'],r['arm'],r['budget']):r for r in rows}; totals={}
    for family in FAMILIES:
        totals[family]={}
        for budget in config['budgets']:
            arms={}
            for arm in ARMS:
                selected=[r for r in latest.values() if r['family']==family and r['arm']==arm and r['budget']==budget]
                final=[next((a for a in r['audits'] if a.get('checkpoint')==r.get('final_checkpoint')), {}) for r in selected]
                gp_counts=[a['forbidden_polygons'] for a in final if a.get('general_position')]
                gp_orientations=[a['orientation_violations'] for a in final if a.get('general_position')]
                arms[arm]={'trials':len(selected),'valid_final':sum(r['primary_valid_geometry'] for r in selected),
                    'valid_any_checkpoint':sum(r['any_saved_valid_geometry'] for r in selected),
                    'native_cpu_seconds':sum(s['native_cpu_seconds'] for r in selected for s in r.get('stages',[])),
                    'native_wall_seconds':sum(s['native_wall_seconds'] for r in selected for s in r.get('stages',[])),
                    'worker_observed_cpu_seconds':sum(r['parent_cpu_seconds'] for r in selected),
                    'worker_wall_seconds':sum(r['parent_wall_seconds'] for r in selected),
                    'feedback_wall_seconds':sum(f['total_feedback_wall_seconds'] for r in selected for f in r.get('feedback',[])),
                    'audit_wall_seconds':sum(r['posthoc_wall_seconds'] for r in selected),
                    'audit_cpu_seconds':sum(r['audit_cpu_seconds'] for r in selected),
                    'general_position_final':sum(a.get('general_position',False) for a in final),
                    'median_forbidden_count_in_GP':statistics.median(gp_counts) if gp_counts else None,
                    'median_orientation_violations_in_GP':statistics.median(gp_orientations) if gp_orientations else None,
                    'watchdog_trials':sum(r['overhead_watchdog'] for r in selected),
                    'audit_watchdog_trials':sum(r['audit_watchdog'] for r in selected),
                    'native_forced_kill_stages':sum(s['forced_kill'] for r in selected for s in r.get('stages',[])),
                    'native_nonzero_exit_stages':sum(s['returncode']!=0 for r in selected for s in r.get('stages',[])),
                    'native_missing_output_stages':sum(not s['output_saved'] for r in selected for s in r.get('stages',[])),
                    'status_counts':{status:sum(r['status']==status for r in selected) for status in sorted({r['status'] for r in selected})},
                    'error_trials':sum(r['status'] in ('ERROR','NO_CHECKPOINT','MISSING_OUTPUT') for r in selected),
                    'audit_errors':sum('audit_error' in a for r in selected for a in r['audits'])}
            pairs={}
            for first,second in [('original','v6_plain'),('v6_plain','v6_line10'),('v6_plain','v6_line10_pair10'),('v6_plain','v6_feedback')]:
                counts={'pairs':0,'first_only':0,'second_only':0,'both':0,'neither':0}
                for case in config['cases']:
                    if case['family']!=family: continue
                    a,b=latest.get((case['id'],first,budget)),latest.get((case['id'],second,budget))
                    if a is None or b is None: continue
                    if a['initial_target_sha256']!=b['initial_target_sha256'] or a['seed']!=b['seed']:
                        raise RuntimeError('Unmatched target/seed in paired result')
                    counts['pairs']+=1; x,y=a['primary_valid_geometry'],b['primary_valid_geometry']
                    counts['both' if x and y else 'first_only' if x else 'second_only' if y else 'neither']+=1
                pairs[first+'__'+second]=counts
            totals[family][str(budget)]={'arms':arms,'pairs':pairs}
    registered=len(config['cases'])*len(ARMS)*len(config['budgets'])
    result={'registered_trials':registered,'completed_trials':len(latest),'complete':len(latest)==registered,
        'families':{family:{'budgets':value} for family,value in totals.items()},'budgets':config['budgets'],
        'attempted_trials':attempted,'incomplete_attempts':incomplete,
        'preparation_cpu_seconds':sum(r['parent_cpu_seconds'] for r in preparations),
        'preparation_wall_seconds':sum(r['parent_wall_seconds'] for r in preparations),
        'primary':'final checkpoint','secondary':'any saved checkpoint',
        'attribution':config['attribution'],'caps_scope':config['caps_scope'],'selection':config['selection']}
    atomic(registration.parent/'summary.json',result)
    print(json.dumps({'summary':str(registration.parent/'summary.json'),'complete':result['complete'],
                      'completed':len(latest),'registered':registered})); return result


def self_test():
    cases=[{'id':i,'condition_order':[{'arm':'original','budget':10},{'arm':'v6_plain','budget':10}]} for i in range(4)]
    done={(0,'original',10),(0,'v6_plain',10),(1,'original',10)}
    assert [c['id'] for c in unfinished_cases(cases,done,1)]==[1]
    assert [c['id'] for c in unfinished_cases(cases,done,2)]==[1,2]
    assert [c['id'] for c in unfinished_cases(cases,done)]==[1,2,3]
    assert unfinished_cases(cases,{(i,a,10) for i in range(4) for a in ('original','v6_plain')},1)==[]
    for invalid in (0,-1):
        try: unfinished_cases(cases,done,invalid)
        except ValueError: pass
        else: raise AssertionError('Invalid case limit accepted')
    for invalid in (0,-1,float('nan'),float('inf')):
        try: register(argparse.Namespace(targets=20,budgets=[invalid]))
        except ValueError: pass
        else: raise AssertionError('Invalid budget accepted')
    auditor=load_module(ROOT/'benchmarks/compare19_audit.py','families_test_auditor')
    with tempfile.TemporaryDirectory(prefix='pointsat-family-test-') as tmp:
        folder=Path(tmp); a=folder/'a.or'; b=folder/'b.or'
        a.write_text('A_(1,2,3)\n'); b.write_text('B_(2,1,3)\n')
        assert canonical_target(a,3,auditor)==canonical_target(b,3,auditor)
        # Independent exact fixtures exercise every geometric acceptance gate.
        # These invoke only exhaustive validators, never an optimizer or SAT.
        for family,(n,gon,hole,cap) in FAMILIES.items():
            real=folder/(family+'.real')
            direction=-1 if cap else 1
            real.write_text(''.join(f'{i+1} {i} {direction*i*i}\n' for i in range(n)))
            case={'family':family,'n':n,'gon':gon,'hole':hole,'cap':cap}
            result=audit_family(real,a,case,folder/(family+'-audit'),
                                {'paths':{'verifier':str(ROOT/'direct/verify_big')}},auditor)
            assert result['general_position'] and not result['valid_geometry']
            if gon: assert result['geometry']['convex_gons']==math.comb(n,gon)
            if hole: assert result['geometry']['empty_holes']==math.comb(n,hole)
            if cap: assert result['geometry']['convex_caps']==math.comb(n,cap)
    config={'paths':{'original':'upstream','improved':'v6'}}
    for arm in ARMS:
        command=native_command(config,arm,'target.or','points.real',123,30)
        assert '--ordered-x' not in command and command[command.index('-s')+1]=='123'
        assert ('--line-every' in command)==(arm in ('v6_line10','v6_line10_pair10'))
        assert ('--pair-every' in command)==(arm=='v6_line10_pair10')
    groups,_=inventory()
    assert all(len(g)>=20 for g in groups.values())
    assert all(len({c['full_primary_sha256'] for c in g})==len(g) for g in groups.values())
    assert all(all(c['canonical_supported'] for c in g) and
               len({c['canonical_signs'] for c in g})==len(g) for g in groups.values())
    print(json.dumps({'self_test':'passed','available':{f:len(g) for f,g in groups.items()},'native_searches_started':0}))


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='mode',required=True)
    q=sub.add_parser('register'); q.add_argument('--output',required=True); q.add_argument('--targets',type=int,default=20)
    q.add_argument('--budgets',nargs='+',type=float,default=[10,30,60]); q.add_argument('--seed',type=int,default=490907)
    q.set_defaults(fn=register)
    q=sub.add_parser('run'); q.add_argument('--registration',required=True); q.add_argument('--workers',type=int,choices=(1,2),default=2)
    q.add_argument('--max-cases',type=int,help='Process at most this many unfinished cases, then exit cleanly; resume uses the same registration.')
    q.set_defaults(fn=run)
    q=sub.add_parser('worker'); q.add_argument('--registration',required=True); q.add_argument('--case',type=int,required=True)
    q.add_argument('--arm',required=True); q.add_argument('--work',required=True); q.set_defaults(fn=worker)
    q=sub.add_parser('summarize'); q.add_argument('--registration',required=True); q.set_defaults(fn=lambda a:summarize(a.registration))
    q=sub.add_parser('inventory'); q.set_defaults(fn=lambda a:print(json.dumps({f:len(g) for f,g in inventory()[0].items()})))
    q=sub.add_parser('self-test'); q.set_defaults(fn=lambda a:self_test())
    args=p.parse_args(); args.fn(args)


if __name__=='__main__': main()
