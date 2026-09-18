"""Realize a frozen lazy-SAT corpus; independently verify every geometry."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import sys
import subprocess
import time
import hashlib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'improvements/symmetry19'))
from search_variants import run
from audit_realizations import audit
sys.path.insert(0,str(ROOT))
from sat_orient_conversion import inspect_realization


def gradient_run(case):
    out=Path(case['output']);out.mkdir(parents=True,exist_ok=False)
    command=['improvements/lazy19/gradient',case['orientations'],case['warm_start'],str(out/'points.real'),
             str(case['seconds']),str(case['seed']),str(case['margin'])]
    start=time.monotonic()
    with (out/'stdout.txt').open('w') as stdout,(out/'stderr.txt').open('w') as stderr:
        result=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=case['seconds']+15)
    record=dict(case,binary=command[0],binary_sha256=hashlib.sha256(Path(command[0]).read_bytes()).hexdigest(),
                method='gradient',command=command,returncode=result.returncode,wall_seconds=time.monotonic()-start)
    if (out/'points.real').exists():
        record['verification']=audit(out/'points.real')
        record['orientation_violations']=len(inspect_realization(case['orientations'],out/'points.real',19)['bad_vars'])
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--warm',default='improvements/symmetry19/search/model002-relaxed-symmetric/points.real')
    p.add_argument('--binary',default='improvements/localizer/localizer_v5')
    p.add_argument('--seconds',type=float,default=20)
    p.add_argument('--workers',type=int,default=2)
    p.add_argument('--samples',type=int,default=32)
    p.add_argument('--method',choices=('localizer','gradient'),default='localizer')
    p.add_argument('--margin',type=float,default=1e-6)
    args=p.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    cases=[dict(binary=args.binary,orientations=str(path),symmetry=False,seed=19561+i,
                seconds=args.seconds,output=str(out/path.stem),warm_start=args.warm,
                line_every=10,pair_every=0,min_radius=1e-6,sub_iterations=24,margin=args.margin)
           for i,path in enumerate(sorted(Path(args.corpus).glob('model*.or'))[:args.samples])]
    (out/'manifest.json').write_text(json.dumps(cases,indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(gradient_run if args.method=='gradient' else run,cases):print(json.dumps(record),flush=True)

if __name__=='__main__':main()
