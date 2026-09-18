#!/usr/bin/env python3
"""Export a winning SQLite checkpoint and independently recheck original CNF."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from improvements.benchmarks.independent_audit import audit_file
from improvements.benchmarks.matched import integer_points,cross

def main():
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--trial',required=True,type=int);p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect(a.database)as db:
        record=json.loads(db.execute('SELECT result_json FROM trials WHERE job_index=?',(a.trial,)).fetchone()[0])
        for name,digest,compressed in db.execute('SELECT name,sha256,data_zlib FROM artifacts WHERE job_index=?',(a.trial,)):
            data=zlib.decompress(compressed);assert hashlib.sha256(data).hexdigest()==digest
            if Path(name).name!=name:raise ValueError('bad artifact name')
            (out/name).write_bytes(data)
    (out/'trial.json').write_text(json.dumps(record,indent=2)+'\n')
    winner=next(r for r in record['posthoc']['saved_checkpoints']if r.get('geometry',{}).get('valid'))
    real=out/winner['stage_file'];radial=real.with_name(real.stem+'.radial.real')
    if radial.exists():real=radial
    case=record['job']['case'];certificate=audit_file(real,case['n'],case['problem'],out/'proof',cnf=case['cnf'])
    assert certificate['accepted']
    points=integer_points(real);triples=list(itertools.combinations(range(len(points)),3))
    def signs(p):return [((d>0)-(d<0))for i,j,k in triples for d in[cross(p[i],p[j],p[k])]]
    expected=signs(points);assert all(expected)
    ox=min(x for x,y in points);oy=min(y for x,y in points)
    span=max(max(x for x,y in points)-ox,max(y for x,y in points)-oy)
    for grid in(100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000,100000000,1000000000,10000000000):
        q=[(((x-ox)*2*grid+span)//(2*span),((y-oy)*2*grid+span)//(2*span))for x,y in points]
        if signs(q)==expected:break
    else:raise ValueError('No compact sign-preserving normalization found')
    normalized=out/'normalized.pts';normalized.write_text(str(len(q))+'\n'+''.join(f'{x} {y}\n'for x,y in q))
    command=[str(ROOT/'direct/verify'),'--input',str(normalized),'--gon',str(case['gon']),'--hole',str(case['hole']),'--cap',str(case['cap'])]
    check=subprocess.run(command,capture_output=True,text=True,check=True);geometry=json.loads(check.stdout)
    summary={'trial':a.trial,'job':record['job'],'normalization_grid':grid,'all_orientation_signs_preserved':True,
             'independent_normalized_geometry':geometry,'original_cnf_certificate':certificate,
             'search_wall_seconds':record['wall_seconds'],'saved_geometry_upper_bound_seconds':winner['saved_elapsed_upper_bound']}
    (out/'certificate.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'accepted':True,'family':case['problem'],'grid':grid,'box':[geometry['bbox_width'],geometry['bbox_height']],
                      'certificate':str(out/'certificate.json')}))
if __name__=='__main__':main()
