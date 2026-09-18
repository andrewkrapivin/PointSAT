#!/usr/bin/env python3
"""One single-core prospective SAT draw followed by frozen paired native runs.

Run only through the bounded batch supervisor. No sample is replaced on SAT
failure. Clause shuffling changes neither variable identities nor signs.
"""
import argparse
import json
import os
from pathlib import Path
import random
import resource
import signal
import subprocess
import threading
import time
import matched
from matched import ROOT,digest
from independent_audit import audit_file,check_cnf,model_from_orientations

STOP=threading.Event()
ACTIVE=None

def stop(*_):
    STOP.set()
    if ACTIVE is not None and ACTIVE.poll() is None:
        try:os.killpg(ACTIVE.pid,signal.SIGTERM)
        except ProcessLookupError:pass

def bounded(command,output,seconds,stdin=None):
    global ACTIVE
    before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic()
    with output.with_suffix('.stdout').open('w')as stdout,output.with_suffix('.stderr').open('w')as stderr:
        ACTIVE=subprocess.Popen(command,stdin=stdin,stdout=stdout,stderr=stderr,start_new_session=True,cwd=ROOT)
        timed_out=False
        while ACTIVE.poll()is None:
            if STOP.is_set()or time.monotonic()-start>=seconds:
                timed_out=not STOP.is_set()
                try:os.killpg(ACTIVE.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:ACTIVE.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(ACTIVE.pid,signal.SIGKILL);ACTIVE.wait()
                break
            time.sleep(.1)
        code=ACTIVE.returncode;ACTIVE=None
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'command':command,'returncode':code,'timed_out':timed_out,'interrupted':STOP.is_set(),
            'wall_seconds':time.monotonic()-start,
            'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True);parser.add_argument('--index',required=True,type=int)
    args=parser.parse_args();registration=json.loads(Path(args.registration).read_text());job=registration['cases'][args.index]
    for sig in(signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
    matched._STOP=STOP
    out=ROOT/job['output'];out.mkdir(parents=True,exist_ok=True)
    completed=out/'case_result.json'
    if completed.exists():return
    summary={'registration_sha256':digest(args.registration),'case':job,'native_runs':[]}
    def save():completed.write_text(json.dumps(summary,indent=2)+'\n')
    for binary,expected in registration['binary_sha256'].items():
        if digest(ROOT/binary)!=expected:raise ValueError('Frozen native binary changed: '+binary)
    cnf=ROOT/job['cnf']
    if digest(cnf)!=job['cnf_sha256']:raise ValueError('Original CNF changed')
    with cnf.open('rb')as source:
        shuffle=bounded([str(ROOT/'direct/vendor/scranfilize/scranfilize'),'-P','-f','0','-v','0','-s',str(job['sat_seed'])],out/'shuffle',60,source)
    summary['shuffle']=shuffle
    if shuffle['returncode']!=0 or STOP.is_set():save();return
    sat=bounded([str(ROOT/'direct/vendor/kissat/build/kissat'),'--quiet',f'--seed={job["sat_seed"]}',str(out/'shuffle.stdout')],out/'sat',job['sat_seconds'])
    summary['sat']=sat
    if sat['returncode']!=10 or STOP.is_set():save();return
    n=job['n'];count=n*(n-1)*(n-2)//6
    literals=[int(v)for line in(out/'sat.stdout').read_text().splitlines()if line.startswith('v ')for v in line[2:].split()if int(v)]
    signs={abs(v):v>0 for v in literals if abs(v)<=count}
    if set(signs)!=set(range(1,count+1)):raise ValueError('SAT output has incomplete orientation model')
    rows=[]
    for k in range(3,n+1):
        for j in range(2,k):
            for i in range(1,j):
                rank=i+(j-1)*(j-2)//2+(k-1)*(k-2)*(k-3)//6
                rows.append(('A'if signs[rank]else'B')+f'_({i}, {j}, {k})\n')
    orient=out/'target.or';orient.write_text(''.join(rows))
    case={**job,'orientation':str(orient.relative_to(ROOT)),'sha256':digest(orient),'split':'overnight_prospective','known_seeded':False}
    summary['orientation_sha256']=case['sha256']
    summary['independent_original_cnf']=check_cnf(model_from_orientations(orient,n),n,cnf,None,out,'target')
    if not summary['independent_original_cnf']['satisfiable']:raise ValueError('SAT projection failed independent original-CNF audit')
    treatments=list(registration['treatments'])
    if job['problem']=='caps26':treatments+=registration['caps_treatments']
    # Order is randomized prospectively, identical pairing inputs remain fixed.
    runs=[(t,seed)for seed in registration['native_seeds']for t in treatments]
    random.Random(job['sat_seed']+99191).shuffle(runs)
    for treatment,seed in runs:
        if STOP.is_set():break
        target=out/treatment['label'];target.mkdir(exist_ok=True)
        record=matched.run_one((case,str(ROOT/treatment['binary']),treatment['label'],seed,
                               registration['native_seconds'],str(target),treatment['flags']))
        if record is None:break
        summary['native_runs'].append(record)
        if record.get('geometry',{}).get('valid'):
            real=target/(case['id']+f'-s{seed}')/'points.real'
            try:
                certificate=audit_file(real,n,job['problem'],target/(case['id']+f'-s{seed}')/'independent',cnf=cnf,orient=orient)
                record['independent_certificate']=certificate
            except Exception as error:record['independent_certificate_error']=repr(error)
        save()
    summary['interrupted']=STOP.is_set();summary['completed_all_native_runs']=len(summary['native_runs'])==len(runs)
    save()

if __name__=='__main__':main()
