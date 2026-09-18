#!/usr/bin/env python3
"""Fixed-trajectory native evaluator ablation: same improved search, two kernels."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import resource
import shutil
import statistics
import subprocess
import time
from matched import ROOT,digest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--binary',required=True)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--iterations',type=int,default=100000)
    parser.add_argument('--repeats',type=int,default=5)
    a=parser.parse_args()
    output=Path(a.output).resolve();output.mkdir(parents=True,exist_ok=False)
    binary=output/'localizer';shutil.copy2(a.binary,binary)
    cases=json.loads(Path(a.manifest).read_text())['cases']
    randomizer=random.Random(20260905)
    records=[]
    with (output/'results.jsonl').open('w',buffering=1) as stream:
        for case in cases:
            for repeat in range(a.repeats):
                modes=['reference','fast'];randomizer.shuffle(modes)
                pair={}
                for mode in modes:
                    prefix=output/f'{case["id"]}-r{repeat}-{mode}'
                    real=prefix.with_suffix('.real')
                    cmd=[str(binary),str(ROOT/case['orientation']),'-t','1','-i','10','-r','30000',
                         '-s','42','-f','','-c','','-q','-I',str(a.iterations),'-o',str(real)]
                    if mode=='reference': cmd+=['--reference-evaluation']
                    before=resource.getrusage(resource.RUSAGE_CHILDREN)
                    start=time.monotonic()
                    result=subprocess.run(cmd,text=True,capture_output=True,timeout=120)
                    wall=time.monotonic()-start;after=resource.getrusage(resource.RUSAGE_CHILDREN)
                    prefix.with_suffix('.stdout').write_text(result.stdout)
                    prefix.with_suffix('.stderr').write_text(result.stderr)
                    stats=[json.loads(s) for s in result.stdout.splitlines() if s.startswith('{')]
                    record={'case':case['id'],'problem':case['problem'],'repeat':repeat,'mode':mode,
                            'binary_sha256':digest(binary),'orientation_sha256':case['sha256'],
                            'wall_seconds':wall,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                            'returncode':result.returncode,'stats':stats,'command':cmd,
                            'coordinate_sha256':digest(real) if real.exists() else None}
                    stream.write(json.dumps(record)+'\n');records.append(record);pair[mode]=record
                equal=pair['fast']['coordinate_sha256']==pair['reference']['coordinate_sha256']
                path_keys=('iterations','proposals','accepted','improvements','restarts','final_violations','best_violations')
                equivalent=(equal and pair['fast']['returncode']==pair['reference']['returncode']==0
                            and all(pair['fast']['stats'][0][k]==pair['reference']['stats'][0][k] for k in path_keys))
                if not equivalent: raise RuntimeError('Fixed-work trajectory diverged: '+case['id'])
                print(json.dumps({'case':case['id'],'repeat':repeat,'coordinate_identical':equal,
                                  'cpu_speedup':pair['reference']['cpu_seconds']/pair['fast']['cpu_seconds']}),flush=True)
    summary={'note':'Same improved search trajectory with reference full evaluation versus optimized incremental evaluation. NOT original-versus-revised overall algorithm speedup.',
             'max_iterations':a.iterations,'repeats':a.repeats,'binary_sha256':digest(binary),'groups':{}}
    for problem in sorted({r['problem'] for r in records}):
        rows=[r for r in records if r['problem']==problem]
        ref=[r for r in rows if r['mode']=='reference'];fast=[r for r in rows if r['mode']=='fast']
        rs=statistics.median(r['cpu_seconds'] for r in ref);fs=statistics.median(r['cpu_seconds'] for r in fast)
        summary['groups'][problem]={'reference_median_cpu_seconds':rs,'fast_median_cpu_seconds':fs,
             'median_cpu_speedup':rs/fs,'coordinate_identical_pairs':len(ref),
             'reference_constraint_evaluations':ref[0]['stats'][0]['constraint_evaluations'],
             'fast_constraint_evaluations':fast[0]['stats'][0]['constraint_evaluations'],
             'proposals':fast[0]['stats'][0]['proposals'],
             'actual_iterations':fast[0]['stats'][0]['iterations'],
             'solved_before_iteration_cap':fast[0]['stats'][0]['best_violations']==0}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
