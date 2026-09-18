#!/usr/bin/env python3
"""Prospectively reserved additional 29-point SAT attempt with default Kissat."""
import json
from pathlib import Path
import resource
import subprocess
import time
from matched import ROOT,digest

out=ROOT/'improvements/benchmarks/late_holes29'
out.mkdir(parents=True,exist_ok=False)
job={'n':29,'problem':'holes29','split':'late_heldout','sat_seed':19501,
     'cnf':'6hole-29-compact.cnf','solver':'Kissat default (no --plain)',
     'seconds':900,'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
(out/'registered.json').write_text(json.dumps(job,indent=2)+'\n')
start=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN)
cmd=[str(ROOT/'direct/vendor/kissat/build/kissat'),'--quiet','--seed=19501',str(ROOT/job['cnf'])]
with (out/'solver.stdout').open('w') as stdout,(out/'solver.stderr').open('w') as stderr:
    proc=subprocess.Popen(cmd,stdout=stdout,stderr=stderr)
    try:code=proc.wait(timeout=900);timed_out=False
    except subprocess.TimeoutExpired:proc.kill();code=proc.wait();timed_out=True
after=resource.getrusage(resource.RUSAGE_CHILDREN)
job.update(returncode=code,timed_out=timed_out,wall_seconds=time.monotonic()-start,
           cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
           command=cmd,cnf_sha256=digest(ROOT/job['cnf']))
text=(out/'solver.stdout').read_text()
if code==10:
    literals=[int(x) for line in text.splitlines() if line.startswith('v ') for x in line[2:].split() if int(x)]
    selected=sorted((x for x in literals if abs(x)<=3654),key=abs)
    assert len(selected)==3654
    signs={abs(x):x>0 for x in selected}
    lines=[]
    for k in range(3,30):
        for j in range(2,k):
            for i in range(1,j):
                v=i+(j-1)*(j-2)//2+(k-1)*(k-2)*(k-3)//6
                lines.append(('A' if signs[v] else 'B')+f'_({i}, {j}, {k})\n')
    orient=out/'holes29-seed19501.or';orient.write_text(''.join(lines))
    case={'id':'holes29-seed19501','problem':'holes29','split':'late_heldout','n':29,'gon':0,'hole':6,'cap':0,
          'orientation':str(orient.relative_to(ROOT)),'sha256':digest(orient),'sat_seed':19501,
          'known_seeded':False,'generation_result':job}
    (out/'manifest.json').write_text(json.dumps({'cases':[case]},indent=2)+'\n')
(out/'result.json').write_text(json.dumps(job,indent=2)+'\n')
print(json.dumps(job),flush=True)
