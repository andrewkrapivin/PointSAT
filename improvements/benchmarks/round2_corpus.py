#!/usr/bin/env python3
"""Prospective new heldout SAT cases for frozen pair/orbit candidate v5."""
import json
from pathlib import Path
import resource
import subprocess
import time
from matched import ROOT,HERE,digest

folder=HERE/'round2_corpus';folder.mkdir(parents=True,exist_ok=False)
spec=[('mixed23',23,7,6,0,'7gon-6hole-23-compact.cnf',31101),
      ('gons32',32,7,0,0,'7gon-32.cnf',31301),
      ('caps26',26,7,0,5,'7gon-no-5-cap-no-sb-26.cnf',31401),
      ('holes29',29,0,6,0,'6hole-29-compact.cnf',31201)]
jobs=[{'problem':problem,'n':n,'gon':gon,'hole':hole,'cap':cap,'cnf':cnf,'sat_seed':seed+i,
       'id':problem+'-seed'+str(seed+i),'split':'round2_heldout','wall_limit':600}
      for problem,n,gon,hole,cap,cnf,seed in spec for i in range(2)]
registered={'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'jobs':jobs,
            'native_candidate_sha256':digest(ROOT/'improvements/localizer/localizer_v5'),
            'prespecified_native_treatments':[[],['--line-every','10'],['--pair-every','10','--line-every','10']],
            'localizer_seeds':[1,17,101],'localizer_wall_seconds':15,
            'note':'All new SAT seeds; candidate and treatments frozen before models or convergence outcomes. Default Kissat,600s SAT cap; no known-coordinate seed.'}
(folder/'registered.json').write_text(json.dumps(registered,indent=2)+'\n')
cases=[];failed=[]
for job in jobs:
    prefix=folder/job['id'];cmd=[str(ROOT/'direct/vendor/kissat/build/kissat'),'--quiet',f'--seed={job["sat_seed"]}',str(ROOT/job['cnf'])]
    start=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN)
    with prefix.with_suffix('.stdout').open('w')as stdout,prefix.with_suffix('.stderr').open('w')as stderr:
        process=subprocess.Popen(cmd,stdout=stdout,stderr=stderr)
        try:code=process.wait(timeout=job['wall_limit']);timed_out=False
        except subprocess.TimeoutExpired:process.kill();code=process.wait();timed_out=True
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    metadata={**job,'returncode':code,'timed_out':timed_out,'wall_seconds':time.monotonic()-start,
              'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
              'command':cmd,'cnf_sha256':digest(ROOT/job['cnf'])}
    if code==10:
        n=job['n'];count=n*(n-1)*(n-2)//6
        literal=[int(s)for line in prefix.with_suffix('.stdout').read_text().splitlines()if line.startswith('v ')for s in line[2:].split()if int(s)]
        signs={abs(v):v>0 for v in literal if abs(v)<=count};assert set(signs)==set(range(1,count+1))
        lines=[]
        for k in range(3,n+1):
            for j in range(2,k):
                for i in range(1,j):
                    v=i+(j-1)*(j-2)//2+(k-1)*(k-2)*(k-3)//6
                    lines.append(('A'if signs[v]else'B')+f'_({i}, {j}, {k})\n')
        orient=prefix.with_suffix('.or');orient.write_text(''.join(lines))
        cases.append({**job,'orientation':str(orient.relative_to(ROOT)),'sha256':digest(orient),
                      'known_seeded':False,'generation_result':metadata})
    else:failed.append(metadata)
    prefix.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (folder/'manifest.json').write_text(json.dumps({'registration':registered,'cases':cases,'failed_cases':failed},indent=2)+'\n')
    print(json.dumps(metadata),flush=True)
print(json.dumps({'finished':True,'sat_cases':len(cases),'failed_cases':len(failed)}),flush=True)
