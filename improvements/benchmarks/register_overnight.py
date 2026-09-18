#!/usr/bin/env python3
"""Freeze an 80-draw interleaved four-problem queue before generating targets."""
import json
import time
from matched import ROOT,HERE,digest

folder=HERE/'overnight';folder.mkdir(exist_ok=False)
v5='improvements/localizer/localizer_v5';v6='improvements/localizer/localizer_v6'
spec=[('mixed23',23,7,6,0,'7gon-6hole-23-compact.cnf',42100,300),
      ('holes29',29,0,6,0,'6hole-29-compact.cnf',42200,1800),
      ('gons32',32,7,0,0,'7gon-32.cnf',42300,180),
      ('caps26',26,7,0,5,'7gon-no-5-cap-no-sb-26.cnf',42400,180)]
cases=[]
for draw in range(20):
    for problem,n,gon,hole,cap,cnf,base,seconds in spec:
        seed=base+draw;label=f'{problem}-s{seed}'
        cases.append({'id':label,'problem':problem,'n':n,'gon':gon,'hole':hole,'cap':cap,
                      'cnf':cnf,'cnf_sha256':digest(ROOT/cnf),'sat_seed':seed,'sat_seconds':seconds,
                      'output':str((folder/'runs'/label).relative_to(ROOT))})
registration={'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cases':cases,
              'binary_sha256':{p:digest(ROOT/p)for p in(v5,v6)},'native_seeds':[1,17,101],'native_seconds':45,
              'treatments':[{'label':'v5_default','binary':v5,'flags':[]},
                            {'label':'v5_line10','binary':v5,'flags':['--line-every','10']},
                            {'label':'v5_pair_line10','binary':v5,'flags':['--pair-every','10','--line-every','10']}],
              'caps_treatments':[{'label':'v6_default','binary':v6,'flags':[]},
                                 {'label':'v6_ordered_x','binary':v6,'flags':['--ordered-x']}],
              'protocol':'Interleaved four-problem draws, clause-only scranfilize, default Kissat. Keep all SAT failures. Pair identical full orientations and seeds; randomize treatment order per case. No coordinate seeds, no early success stopping. Cluster analysis by unique orientation SHA256, not SAT seed. All geometry successes independently audited; CNF-SB rejection does not erase geometry evidence.'}
path=folder/'registration.json';path.write_text(json.dumps(registration,indent=2)+'\n')
jobs=[]
for i,case in enumerate(cases):
    native_budget=675 if case['problem']=='caps26' else 405
    jobs.append({'label':'benchmark-'+case['id'],'workers':1,'max_seconds':case['sat_seconds']+native_budget+150,
                 'command':[str(ROOT/'direct/vendor/venv/bin/python'),str(HERE/'overnight_case.py'),'--registration',str(path),'--index',str(i)],
                 'output':str(ROOT/case['output'])})
(folder/'jobs.json').write_text(json.dumps(jobs,indent=2)+'\n')
print(json.dumps({'registration':str(path),'manifest':str(folder/'jobs.json'),'jobs':len(jobs)}))
