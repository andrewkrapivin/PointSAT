#!/usr/bin/env python3
"""Freeze generated SAT cases and separately labeled known-realizable controls."""
import argparse
import itertools
import json
from pathlib import Path
import shutil
import time
from matched import ROOT,HERE,digest,constraints,cross

TARGETS={'mixed23':(23,7,6,0),'holes29':(29,0,6,0),
         'gons32':(32,7,0,0),'caps26':(26,7,0,5)}

def fresh():
    source=ROOT/'improvements/pipeline/fresh_corpus'
    frozen=json.loads((source/'frozen_manifest.json').read_text())
    dest=HERE/'corpus/fresh'
    dest.mkdir(parents=True,exist_ok=False)
    cases=[];missing=[]
    for job in frozen['jobs']:
        n,g,h,c=TARGETS[job['problem']]
        prefix=ROOT/job['prefix']; orient=prefix.with_suffix('.or')
        metadata=prefix.with_suffix('.json')
        info=json.loads(metadata.read_text()) if metadata.exists() else {'status':'not_finished'}
        if not orient.exists():
            missing.append({**job,'generation_result':info});continue
        output=dest/orient.name
        shutil.copyfile(orient,output)
        shutil.copyfile(metadata,dest/metadata.name)
        assert len(constraints(output))==n*(n-1)*(n-2)//6
        cases.append({'id':prefix.name,'problem':job['problem'],'split':job['split'],
                      'n':n,'gon':g,'hole':h,'cap':c,'orientation':str(output.relative_to(ROOT)),
                      'sha256':digest(output),'sat_seed':job['seed'],'known_seeded':False,
                      'source':job['prefix'],'generation_result':info})
    out={'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         'split_source':str((source/'frozen_manifest.json').relative_to(ROOT)),
         'split_source_sha256':digest(source/'frozen_manifest.json'),
         'cases':cases,'missing_cases':missing}
    target=HERE/'fresh_manifest.json';target.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({'manifest':str(target),'cases':len(cases),'missing':len(missing)}))

def controls():
    fixtures={'mixed23':'paper23','holes29':'overmars29','gons32':'es32','caps26':'es26cap5'}
    dest=HERE/'corpus/known_controls';dest.mkdir(parents=True,exist_ok=False)
    cases=[]
    for problem,stem in fixtures.items():
        source=ROOT/'direct/seeds'/(stem+'.pts')
        tokens=list(map(int,source.read_text().split()))
        points=list(zip(tokens[1::2],tokens[2::2]));n,g,h,c=TARGETS[problem]
        assert tokens[0]==n==len(points)
        orient=dest/(stem+'.or')
        orient.write_text(''.join(('A' if cross(points[i],points[j],points[k])>0 else 'B')+
                                 f'_({i+1}, {j+1}, {k+1})\n' for k in range(n) for j in range(k) for i in range(j)))
        cases.append({'id':'control-'+stem,'problem':problem,'split':'known_realizable_control',
                      'n':n,'gon':g,'hole':h,'cap':c,'orientation':str(orient.relative_to(ROOT)),
                      'sha256':digest(orient),'known_seeded':True,'source':str(source.relative_to(ROOT)),
                      'source_sha256':digest(source),
                      'note':'Known coordinate-derived order type, NEVER a new SAT discovery. Coordinates are not supplied to Localizer.'})
    target=HERE/'controls_manifest.json'
    target.write_text(json.dumps({'cases':cases},indent=2)+'\n')
    print(json.dumps({'manifest':str(target),'cases':len(cases)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['fresh','controls']);a=parser.parse_args()
    {'fresh':fresh,'controls':controls}[a.kind]()
