#!/usr/bin/env python3
"""Frozen-v2 cross-family validation/compaction, paired with the old engine."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pointsat.geometry import bounded_points,describe,pts_text,read_points,signs

CASES=[
 ('heldout23-job090','mixed23','improvements/pipeline/unattended_20260905/runs/job090-mixed23-target_margin/audit/sample6-job19/points.pts'),
 ('heldout23-job072','mixed23','improvements/pipeline/unattended_20260905/runs/job072-mixed23-target_margin/audit/sample2-job11/points.pts'),
 ('heldout29-trial11','holes29','benchmarks/success29/trial11/normalized.pts'),
 ('heldout29-trial19','holes29','benchmarks/success29/trial19/normalized.pts'),
 ('control32','gons32','direct/seeds/es32.pts'),
 ('control26','caps26','direct/seeds/es26cap5.pts')]
FLAGS={'mixed23':(7,6,0),'holes29':(0,6,0),'gons32':(7,0,0),'caps26':(7,0,5)}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def audit(path,family):
    g,h,c=FLAGS[family]
    result=subprocess.run([str(ROOT/'direct/verify'),'--input',str(path),'--gon',str(g),'--hole',str(h),'--cap',str(c)],capture_output=True,text=True,timeout=30)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    return json.loads(result.stdout)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--seconds',type=float,default=30);parser.add_argument('--ablation',action='store_true');a=parser.parse_args()
    if a.output.exists():raise ValueError('Refusing to replace an existing experiment directory')
    a.output.mkdir(parents=True);fixtures=a.output/'fixtures';fixtures.mkdir()
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'seconds':a.seconds,'workers':3,'seed':1,'new_preserves_layer_sizes':True,'same_mode_ablation':a.ablation,'cases':{},'binaries':{}}
    binaries={'v1':ROOT/'optimizer/compact_v1','v2':ROOT/'optimizer/compact_v2'} if a.ablation else {'old':ROOT/'direct/compact','new':ROOT/'optimizer/compact_v2'}
    assert sha(ROOT/'optimizer/compact_v2')=='b64a9a166d0761bdc1e15df79f9cb6fe741d22a5bd3d49c0af99224ae7221482'
    if a.ablation:assert sha(binaries['v1'])=='80faa99d357cb6f21e55d6da442b8cde8362b8e150f0211142cf9dbcf9de3205'
    for label,path in binaries.items():metadata['binaries'][label]={'path':str(path),'sha256':sha(path)}
    for case,family,source in CASES:
        original=read_points(ROOT/source);normalized=bounded_points(original,limit=10**9)
        assert signs(original)==signs(normalized)
        path=fixtures/(case+'.pts');path.write_text(pts_text(normalized))
        metadata['cases'][case]={'family':family,'source':source,'source_sha256':sha(ROOT/source),'input_sha256':sha(path),'all_original_signs_preserved':True,'input_audit':audit(path,family)}
    (a.output/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    def run(task):
        case,family,label=task;folder=a.output/(case+'-'+label);folder.mkdir();output=folder/'points.pts'
        command=[str(binaries[label]),'--input',str(fixtures/(case+'.pts')),'--output',str(output),'--seconds',str(a.seconds),'--seed','1']
        if label!='old':command+=['--family',family,'--preserve-layers']
        elif family=='caps26':command+=['--preserve-x-order']
        begin=time.monotonic()
        with (folder/'stdout.jsonl').open('w') as stdout,(folder/'stderr.txt').open('w') as stderr:
            r=subprocess.run(['/usr/bin/time','-f','%U %S %e','-o',str(folder/'cpu.txt'),*command],stdout=stdout,stderr=stderr,timeout=a.seconds+30)
        row={'case':case,'family':family,'label':label,'command':command,'returncode':r.returncode,'wall_seconds':time.monotonic()-begin}
        if r.returncode==0:
            row['audit']=audit(output,family);cpu=(folder/'cpu.txt').read_text().split();row['cpu_seconds']=float(cpu[0])+float(cpu[1]);row['output_sha256']=sha(output)
            start=read_points(fixtures/(case+'.pts'));end=read_points(output)
            row['orientation_changes']=sum(a!=b for a,b in zip(signs(start),signs(end)))
            assert describe(start)['hull_layers']==row['audit']['hull_layers']
            if label=='old':assert row['orientation_changes']==0
        else:row['error']=(folder/'stderr.txt').read_text()
        (folder/'result.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row),flush=True);return row
    tasks=[(case,family,label) for case,family,_ in CASES for label in binaries]
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,tasks))
    (a.output/'summary.json').write_text(json.dumps({'manifest':metadata,'results':results},indent=2)+'\n')
if __name__=='__main__':main()
