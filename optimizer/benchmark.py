#!/usr/bin/env python3
"""Prospective equal-budget comparison; no historical file is overwritten."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
CASES={'paper23':'direct/seeds/paper23.pts'}
for case in ('archive23-sample7','archive23-sample2','sat-guided23-case33','feedback23-sample3','control-margin23-sample6'):
    CASES[case]='improvements/benchmarks/successes/'+case+'/normalized.pts'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def audit(path):
    r=subprocess.run([str(ROOT/'direct/verify'),'--input',str(path)],capture_output=True,text=True,timeout=20)
    if r.returncode:raise RuntimeError(r.stderr+r.stdout)
    return json.loads(r.stdout)
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--seconds',type=float,default=120);p.add_argument('--workers',type=int,default=3);p.add_argument('--new-binary',type=Path,default=ROOT/'optimizer/compact')
    a=p.parse_args()
    if a.output.exists():raise ValueError('Refusing to overwrite an existing benchmark directory')
    if not 1<=a.workers<=3:raise ValueError('At most three workers')
    a.output.mkdir(parents=True);fixtures=a.output/'fixtures';fixtures.mkdir()
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'seconds_per_run':a.seconds,'workers':a.workers,'seed':1,'cases':{},'binaries':{}}
    for case,source in CASES.items():
        dst=fixtures/(case+'.pts');shutil.copy2(ROOT/source,dst)
        metadata['cases'][case]={'source':source,'sha256':sha(dst),'input_audit':audit(dst)}
    binaries={'old':ROOT/'direct/compact','new':a.new_binary.resolve()}
    for label,binary in binaries.items():metadata['binaries'][label]={'path':str(binary),'sha256':sha(binary)}
    (a.output/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    tasks=[(case,label) for case in CASES for label in binaries]
    def run(task):
        case,label=task;folder=a.output/(case+'-'+label);folder.mkdir();out=folder/'points.pts'
        command=[str(binaries[label]),'--input',str(fixtures/(case+'.pts')),'--output',str(out),'--seconds',str(a.seconds),'--seed','1']
        measured=['/usr/bin/time','-f','%U %S %e','-o',str(folder/'cpu.txt'),*command]
        begin=time.monotonic()
        with (folder/'stdout.jsonl').open('w') as stdout,(folder/'stderr.txt').open('w') as stderr:
            result=subprocess.run(measured,stdout=stdout,stderr=stderr,timeout=a.seconds+30)
        data={'case':case,'label':label,'command':command,'returncode':result.returncode,'wall_seconds':time.monotonic()-begin}
        if result.returncode==0:
            data['audit']=audit(out);cpu=(folder/'cpu.txt').read_text().split();data.update(cpu_user_seconds=float(cpu[0]),cpu_system_seconds=float(cpu[1]))
            data['output_sha256']=sha(out)
            data['initial_area']=metadata['cases'][case]['input_audit']['bbox_area']
            data['final_area']=data['audit']['bbox_area']
        else:data['error']=(folder/'stderr.txt').read_text()
        (folder/'result.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data),flush=True);return data
    with ThreadPoolExecutor(max_workers=a.workers) as pool:results=list(pool.map(run,tasks))
    (a.output/'summary.json').write_text(json.dumps({'manifest':metadata,'results':results},indent=2)+'\n')
if __name__=='__main__':main()
