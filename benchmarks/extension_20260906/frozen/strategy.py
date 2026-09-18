#!/usr/bin/env python3
"""Equal-total-budget warm retry versus SAT-feedback benchmark, SQLite output.

Only search/control overhead is inside the trial budget. Identical independent
post-hoc certificate work audits every saved checkpoint without feeding search.
"""
import argparse
import ast
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zlib

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
STOP=threading.Event()
LOCK=threading.Lock()

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(path)
def usage():
    a=resource.getrusage(resource.RUSAGE_SELF);b=resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime+a.ru_stime+b.ru_utime+b.ru_stime

def register(args):
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=out/'frozen';frozen.mkdir()
    for file in('flippable2.py','sat_orient_conversion.py'):shutil.copyfile(ROOT/file,frozen/file)
    source=(ROOT/'improvements/pipeline/runner.py').read_text();tree=ast.parse(source)
    functions=[ast.get_source_segment(source,node)for node in tree.body if isinstance(node,ast.FunctionDef)
               and node.name in('orientation_margins','core_guided_feedback')]
    assert len(functions)==2
    (frozen/'feedback.py').write_text('import time, math, hashlib\nfrom sat_orient_conversion import integer_points\n\n'+'\n\n'.join(functions)+'\n')
    shutil.copyfile(__file__,frozen/'strategy.py')
    # The frozen worker resolves ROOT from its registration, not its copy path.
    cases=[]
    old=ROOT/'improvements/benchmarks/overnight'
    for family in('mixed23','holes29','gons32','caps26'):
        seen=set();selected=[]
        for path in sorted((old/'runs').glob(family+'-*/case_result.json')):
            record=json.loads(path.read_text())
            if record.get('sat',{}).get('returncode')!=10:continue
            digest=record['orientation_sha256']
            if digest in seen:continue
            seen.add(digest);selected.append((path,record))
        for path,record in selected[:args.targets]:
            case=dict(record['case']);case.update(orientation=str((path.parent/'target.or').resolve()),orientation_sha256=record['orientation_sha256'])
            case['cnf']=str(ROOT/case['cnf']);cases.append(case)
    jobs=[{'case':c,'seed':seed,'arm':arm}for c in cases for seed in args.seeds for arm in('warm_retry','core_feedback')]
    random.Random(20260906).shuffle(jobs)
    binaries=[ROOT/'improvements/localizer/localizer_v6',ROOT/'direct/verify',ROOT/'direct/verify_big']
    config={'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'root':str(ROOT),'cases':cases,'jobs':jobs,
            'budget_seconds':args.seconds,'native_chunk_seconds':15,'feedback_seconds':5,
            'native_binary':str(binaries[0]),'binary_sha256':{str(p):sha(p)for p in binaries},
            'frozen_sha256':{p.name:sha(p)for p in frozen.iterdir()},'seeds':args.seeds,
            'caps_ordered_x':True,'initial_flippability':True,'feedback_flippability':True,
            'feedback_policy':'target_margin','sampling':'First lexicographically ordered unique SAT targets per family; reused prior corpus, not new unseen heldout data.',
            'budget_scope':'Process launch/import, CNF initialization, flippability, native search, feedback, and operational acceptance. Independent post-hoc audit is separately timed and never guides search.',
            'success_metric':'Any saved checkpoint independently satisfies the actual geometric property, regardless of target mismatch or label-only CNF symmetry breaking.',
            'new_strategy':False}
    atomic(out/'registration.json',config)
    print(json.dumps({'registration':str(out/'registration.json'),'trials':len(jobs),'targets':len(cases)}))

def worker(args):
    config=json.loads(Path(args.registration).read_text());root=Path(config['root']);frozen=Path(args.registration).parent/'frozen'
    sys.path.insert(0,str(frozen))
    from flippable2 import FlippabilityChecker
    from sat_orient_conversion import get_orientations,parse_constraints,orient,inspect_realization,radial_relabel,integer_points,count_caps
    from feedback import core_guided_feedback,orientation_margins
    job=config['jobs'][args.index];case=job['case'];folder=Path(args.work);start=args.started;deadline=start+config['budget_seconds']
    stopped=False
    def stop(*unused):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    def remaining():return max(0,deadline-time.monotonic())
    report={'job':job,'stages':[],'feedback':[],'timings':{},'status':'INITIALIZING','online_success':False}
    def checkpoint():
        report.update(elapsed=time.monotonic()-start,worker_cpu_seconds=usage());atomic(folder/'checkpoint.json',report)
    checkpoint();begin=time.monotonic()
    checker=FlippabilityChecker(Path(case['cnf']).read_text());report['timings']['cnf_initialize']=time.monotonic()-begin
    full=[orient(*triple)*s for s,triple in parse_constraints(case['orientation'])]
    full=sorted(full,key=abs);assert len(full)==case['n']*(case['n']-1)*(case['n']-2)//6
    begin=time.monotonic();flips,target=checker.check('v '+' '.join(map(str,full))+' 0')
    report['timings']['initial_flippability']=time.monotonic()-begin;report['initial_flippable_count']=len(flips)
    warm=None;actual=None;bad=[];stage=0;report['status']='SEARCHING';checkpoint()
    while remaining()>.08 and not stopped:
        if stage and job['arm']=='core_feedback'and actual is not None and remaining()>.2:
            begin=time.monotonic();margins=orientation_margins(warm,case['n'])
            settings={'feedback_core_choice':'target_margin','feedback_max_solves':64,'feedback_seconds':min(5,remaining()),
                      'feedback_conflict_budget':1000,'feedback_max_relaxed':64}
            repaired,stats=core_guided_feedback(checker.solver,actual,settings,job['seed']+stage,bad,margins)
            if repaired is not None and remaining()>.1:
                flips,new_target=checker.check('v '+' '.join(map(str,repaired))+' 0')
                target=new_target;stats['new_flippables']=len(flips)
            stats['total_feedback_wall_seconds']=time.monotonic()-begin
            report['feedback'].append(stats);checkpoint()
        if remaining()<=.08 or stopped:break
        orientation=folder/f'stage{stage}.or';orientation.write_text(get_orientations(target,case['n']))
        real=folder/f'stage{stage}.real';chunk=min(15,max(0,remaining()-.04));seed=job['seed']+stage
        command=[config['native_binary'],str(orientation),'-t','1','-i','10','-r','30000','-s',str(seed),'-f','','-c','',
                 '-T',str(chunk),'-o',str(real)]
        if warm is not None:command+=['-w',str(warm)]
        if case['problem']=='caps26':command+=['--ordered-x']
        begin=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN)
        with (folder/f'stage{stage}.stdout').open('w')as stdout,(folder/f'stage{stage}.stderr').open('w')as stderr:
            process=subprocess.Popen(command,stdout=stdout,stderr=stderr)
            try:code=process.wait(timeout=chunk+.5)
            except subprocess.TimeoutExpired:
                process.send_signal(signal.SIGINT)
                try:code=process.wait(timeout=.5)
                except subprocess.TimeoutExpired:process.kill();code=process.wait()
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        record={'stage':stage,'seed':seed,'native_budget_seconds':chunk,'native_wall_seconds':time.monotonic()-begin,
                'native_cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                'finished_elapsed':time.monotonic()-start,'returncode':code,'constraint_count':len(target),
                'target_sha256':sha(orientation),'warm_start':warm is not None}
        report['stages'].append(record);checkpoint()
        if not real.exists():break
        warm=real;actual=None;bad=[]
        if remaining()>.05 and not stopped:
            begin=time.monotonic()
            try:
                inspected=inspect_realization(orientation,real,case['n']);actual=inspected['sat_model'];bad=inspected['bad_vars']
                record['active_target_errors']=len(bad)
                # Same label-only canonicalization and exact cap gate in both arms.
                check_model=actual
                if case['problem']!='caps26'and actual is not None:
                    check_model=radial_relabel(real,folder/f'stage{stage}.radial.real',case['n'])['sat_model']
                if check_model is not None and remaining()>.03:
                    checker.solver.conf_budget(1000)
                    accepted=checker.solver.solve_limited(assumptions=check_model)
                    checker.solver.conf_budget(-1)
                    if accepted and case['problem']=='caps26':accepted=count_caps(real,5)==0
                    record['operational_cnf_acceptance']=accepted
                    if accepted:
                        # Online exact polygon acceptance uses the same independent
                        # executable as post-hoc audit and its time stays charged.
                        p=integer_points(real);pts=folder/f'stage{stage}.online.pts'
                        pts.write_text(str(len(p))+'\n'+''.join(f'{x} {y}\n'for x,y in p))
                        command=[str(root/'direct/verify_big'),'--input',str(pts),'--gon',str(case['gon']),'--hole',str(case['hole'])]
                        if remaining()>.03:
                            v=subprocess.run(command,text=True,capture_output=True,timeout=remaining())
                            geometry=json.loads(v.stdout);record['online_geometry']=geometry
                            if geometry['valid']:
                                report.update(online_success=True,status='SUCCESS');checkpoint();break
            except (ValueError,subprocess.SubprocessError)as error:record['inspection_error']=repr(error)
            record['operational_check_seconds']=time.monotonic()-begin;checkpoint()
        stage+=1
    if not report['online_success']:report['status']='INTERRUPTED'if stopped else'BUDGET_EXHAUSTED'
    checkpoint();checker.close()

def posthoc(folder,job,started_wall):
    # Existing independent exact audit is used only for scoring saved artifacts.
    sys.path.insert(0,str(ROOT/'improvements/benchmarks'))
    from matched import audit
    begin=time.monotonic();records=[]
    for real in sorted(folder.glob('stage*.real')):
        if '.radial.'in real.name:continue
        try:
            r=audit(real,job['case']['orientation'],job['case'])
            r['stage_file']=real.name;r['saved_elapsed_upper_bound']=real.stat().st_mtime-started_wall;records.append(r)
        except Exception as error:records.append({'stage_file':real.name,'audit_error':repr(error)})
    good=[r for r in records if r.get('geometry',{}).get('valid')]
    scores=[r['geometry'].get('convex_gons',0)+r['geometry'].get('empty_holes',0)+r['geometry'].get('convex_caps',0)
            for r in records if'geometry'in r and not r['geometry'].get('collinear_triples',0)]
    return {'saved_checkpoints':records,'valid_geometry':bool(good),'first_success_upper_bound_seconds':min([r['saved_elapsed_upper_bound']for r in good],default=None),
            'minimum_forbidden_count':min(scores,default=None),'audit_wall_seconds':time.monotonic()-begin}

def run(args):
    registration=Path(args.registration).resolve();config=json.loads(registration.read_text());out=registration.parent
    for path,digest in config['binary_sha256'].items():assert sha(path)==digest
    for file,digest in config['frozen_sha256'].items():assert sha(out/'frozen'/file)==digest
    for case in config['cases']:assert sha(case['orientation'])==case['orientation_sha256']and sha(case['cnf'])==case['cnf_sha256']
    database=out/'results.sqlite';connection=sqlite3.connect(database)
    connection.executescript('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS trials (job_index INTEGER PRIMARY KEY, case_id TEXT, family TEXT, seed INTEGER, arm TEXT, result_json TEXT); CREATE TABLE IF NOT EXISTS artifacts (job_index INTEGER, name TEXT, sha256 TEXT, data_zlib BLOB, PRIMARY KEY(job_index,name));')
    completed={r[0]for r in connection.execute('SELECT job_index FROM trials')};connection.close()
    for sig in(signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    def one(index):
        if STOP.is_set()or index in completed:return
        job=config['jobs'][index]
        with tempfile.TemporaryDirectory(prefix=f'trial-{index}-',dir=out)as tmp:
            folder=Path(tmp);started=time.monotonic();wall=time.time();limit=config['budget_seconds']
            command=[str(ROOT/'direct/vendor/venv/bin/python'),str(out/'frozen/strategy.py'),'worker','--registration',str(registration),
                     '--index',str(index),'--work',str(folder),'--started',str(started)]
            with (folder/'worker.stdout').open('w')as stdout,(folder/'worker.stderr').open('w')as stderr:
                process=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
                forced=False;status=None;rusage=None
                while True:
                    pid,status,rusage=os.wait4(process.pid,os.WNOHANG)
                    if pid:break
                    if STOP.is_set()or time.monotonic()-started>=limit:
                        forced=True
                        try:os.killpg(process.pid,signal.SIGINT)
                        except ProcessLookupError:pass
                        until=time.monotonic()+1
                        while time.monotonic()<until:
                            pid,status,rusage=os.wait4(process.pid,os.WNOHANG)
                            if pid:break
                            time.sleep(.02)
                        if not pid:
                            try:os.killpg(process.pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                            _,status,rusage=os.wait4(process.pid,0)
                        break
                    time.sleep(.03)
                process.returncode=os.waitstatus_to_exitcode(status)
                # Ensure a native descendant cannot outlive an abruptly exited worker.
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            elapsed=time.monotonic()-started
            checkpoint=folder/'checkpoint.json'
            record=json.loads(checkpoint.read_text())if checkpoint.exists()else{'status':'NO_CHECKPOINT'}
            record.update(job_index=index,job=job,budget_seconds=limit,wall_seconds=elapsed,
                          parent_observed_cpu_seconds=rusage.ru_utime+rusage.ru_stime,
                          budget_watchdog_fired=forced,externally_interrupted=STOP.is_set(),returncode=process.returncode,
                          cpu_may_exclude_unreaped_descendants=process.returncode<0,
                          timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
            record['posthoc']=posthoc(folder,job,wall)
            artifacts=[]
            for path in folder.iterdir():
                if path.suffix in('.real','.or','.stdout','.stderr'):
                    data=path.read_bytes();artifacts.append((index,path.name,hashlib.sha256(data).hexdigest(),zlib.compress(data)))
            with LOCK,sqlite3.connect(database)as db:
                db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',(index,job['case']['id'],job['case']['problem'],job['seed'],job['arm'],json.dumps(record)))
                db.executemany('INSERT INTO artifacts VALUES (?,?,?,?)',artifacts)
            print(json.dumps({'index':index,'family':job['case']['problem'],'arm':job['arm'],'wall':elapsed,
                              'stages':len(record.get('stages',[])),'valid':record['posthoc']['valid_geometry'],'status':record['status']}),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)as pool:list(pool.map(one,range(len(config['jobs']))))

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('register');p.add_argument('--output',required=True);p.add_argument('--targets',type=int,default=4)
    p.add_argument('--seconds',type=float,default=60);p.add_argument('--seeds',nargs='+',type=int,default=[271,811]);p.set_defaults(fn=register)
    p=sub.add_parser('run');p.add_argument('--registration',required=True);p.add_argument('--workers',type=int,default=3);p.set_defaults(fn=run)
    p=sub.add_parser('worker');p.add_argument('--registration',required=True);p.add_argument('--index',type=int,required=True)
    p.add_argument('--work',required=True);p.add_argument('--started',type=float,required=True);p.set_defaults(fn=worker)
    args=parser.parse_args();args.fn(args)
if __name__=='__main__':main()
