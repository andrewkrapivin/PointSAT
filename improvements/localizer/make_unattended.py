#!/usr/bin/env python3
"""Generate reproducible independent single-core jobs for improvements/batch.py."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def relative(path):return str(path.relative_to(ROOT))
def choose(paths):
    rows=[]
    for path in paths:
        if not path.exists():continue
        r=subprocess.run([str(ROOT/'improvements/symmetry19/verify_hexagons'),str(path)],
                         text=True,capture_output=True,timeout=20)
        if r.returncode not in (0,1):raise RuntimeError(r.stderr)
        data=json.loads(r.stdout)
        if data['collinear_triples'] or data['duplicate_pairs']:continue
        rows.append((data['interior_histogram'][0]+data['interior_histogram'][3],str(path),path,data))
    if not rows:raise ValueError('No general-position geometry seed')
    return min(rows),rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=HERE/'unattended14')
    p.add_argument('--jobs',type=int,default=128)
    p.add_argument('--native-targets',type=Path,help='Explicit BFP-screened 19-point target whitelist (JSON list)')
    p.add_argument('--native-every',type=int,default=8)
    a=p.parse_args();base=a.output.resolve();base.mkdir(parents=True,exist_ok=True)
    if a.native_every<2:raise ValueError('Native sampling interval must be at least two')
    targets=json.loads(a.native_targets.read_text()) if a.native_targets else []
    excluded=ROOT/'improvements/symmetry19/variants/model002-relaxed.or'
    excluded_hash=sha(excluded)
    for target in targets:
        if target.get('bfp_screened') is not True or target.get('n',19)!=19:
            raise ValueError('Native targets must explicitly be BFP-screened 19-point instances')
        if sha(ROOT/target['orientation'])==excluded_hash:
            raise ValueError('model002-relaxed is proved nonrealizable; refusing to queue it')
    inputs=base/'inputs';inputs.mkdir(exist_ok=True)
    snapshots={}
    for mode in ('free','rot'):
        candidates=list((HERE/'results/resume0526').glob(f'geometry-{mode}-s*.pts'))
        candidates+=list((HERE/'results/resume0526').glob(f'geometry-v2-{mode}-s*.pts'))
        (score,_,source,audit),ranked=choose(candidates)
        destination=inputs/f'{mode}.pts';shutil.copy2(source,destination)
        snapshots[mode]={'source':relative(source),'snapshot':relative(destination),
                         'sha256':sha(destination),'score':score,'audit':audit}
        eligible=[row for row in ranked if row[0]<=score+2]
        for suffix,bin_index in (('-empty',0),('-three',3)):
            other=min(eligible,key=lambda row:(row[3]['interior_histogram'][bin_index],row[0],row[1]))
            other_score,_,other_source,other_audit=other
            other_destination=inputs/f'{mode}{suffix}.pts';shutil.copy2(other_source,other_destination)
            snapshots[mode+suffix]={'source':relative(other_source),'snapshot':relative(other_destination),
                'sha256':sha(other_destination),'score':other_score,'audit':other_audit}
    geometry=HERE/'geometry19_v2';localizer=HERE/'localizer_v6'
    configs=[
        (1,1,-8,100000,1000000,2),
        (3,1,-12,1000000,2000000,4),
        (1,3,-10,500000,1000000,4),
        (1,1,-12,0,3000000,1),
        (2,1,-10,500000,1000000,3),
        (1,2,-12,100000,500000,2)]
    jobs=[]
    for i in range(a.jobs):
        family='localizer' if targets and i%a.native_every==a.native_every-1 else 'geometry'
        mode='free' if i%2==0 else 'rot'
        cycle=i//2
        if family=='localizer':
            target=targets[(i//a.native_every)%len(targets)]
            mode='rot' if target.get('symmetry',False) else 'free'
        label=f'{i:03d}-{family}-{mode}-s{21000+i}'
        folder=base/label;prefix=folder/'points'
        if family=='geometry':
            h,t,exponent,restart,anneal,temp=configs[cycle%len(configs)]
            pointfile=prefix.with_suffix('.pts')
            seed_variant=mode+('', '-empty', '-three')[cycle%3]
            command=[relative(geometry),'--input',snapshots[seed_variant]['snapshot'],
                     '--output',relative(pointfile),'--seconds','900','--seed',str(21000+i),
                     '--temperature',str(temp*(3 if mode=='rot' else 1)),
                     '--hole-weight',str(h),'--three-weight',str(t),
                     '--min-exponent',str(exponent),'--restart-every',str(restart),
                     '--cycle-iterations',str(anneal),'--checkpoint-seconds','60']
            if mode=='rot':command+=['--symmetry']
            audit=['python3','improvements/localizer/audit_outputs.py',
                   '--geometry',relative(pointfile),'--output',relative(folder/'audit.json')]
            if mode=='rot':audit+=['--lattice']
        else:
            orientation=ROOT/target['orientation']
            command=[relative(localizer),relative(orientation),'-T','900','-s',str(21000+i),
                     '-o',relative(prefix.with_suffix('.real')),'--archive-prefix',relative(prefix)]
            # Three prespecified, exploratory configurations; no line option is
            # enabled by default or claimed as a general benchmark improvement.
            treatment=cycle%3
            if treatment==0:
                command+=['-i','24','--min-radius','0.000001','--pair-every','10','--line-every','10']
            elif treatment==1:
                command+=['-i','18','--min-radius','0.0001','--pair-every','3']
            if target.get('warm_start') and cycle%4!=3:command+=['-w',target['warm_start']]
            if mode=='rot':
                command+=['-c','improvements/symmetry19/decoded/center19-adjacent.cycles',
                          '-f','improvements/symmetry19/decoded/center19-adjacent.fixed']
            audit=['python3','improvements/localizer/audit_outputs.py',
                   '--localizer-prefix',relative(prefix),'--output',relative(folder/'audit.json')]
        jobs.append({'label':label,'command':command,'max_seconds':905,'workers':1,
                     'output':relative(folder),'audit_command':audit})
    manifest=base/'jobs.json';manifest.write_text(json.dumps(jobs,indent=2)+'\n')
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'deadline_utc':'2026-09-05T14:00:00+00:00',
              'max_workers':2,'native_budget_seconds':900,'watchdog_seconds':905,'jobs':len(jobs),
              'allocation':'all direct geometry unless an explicit BFP-screened native target whitelist is supplied',
              'native_targets':targets,'excluded_nonrealizable_orientation_sha256':excluded_hash,
              'snapshots':snapshots,'binaries':{relative(b):sha(b) for b in (geometry,localizer)},
              'manifest_sha256':sha(manifest)}
    (base/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'manifest':relative(manifest),'jobs':len(jobs),'seeds':snapshots},indent=2))
if __name__=='__main__':main()
