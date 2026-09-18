"""Native realization portfolio; every final geometry is independently checked."""
import argparse
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sat_orient_conversion import integer_points, inspect_realization


def run(case):
    folder=Path(case['output']);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'result.json').exists():raise FileExistsError(folder)
    binary=str(Path(case['binary']).resolve())
    command=[binary,case['orientations'],'-t','1','-s',str(case['seed']),'-T',str(case['seconds']),'-q','-o',str(folder/'points.real')]
    if case['symmetry']:
        command+=['-c','improvements/symmetry19/decoded/center19-adjacent.cycles','-f','improvements/symmetry19/decoded/center19-adjacent.fixed']
    if case.get('warm_start'):command+=['-w',case['warm_start']]
    if case.get('line_every'):command+=['--line-every',str(case['line_every'])]
    if case.get('pair_every'):command+=['--pair-every',str(case['pair_every'])]
    if case.get('min_radius'):command+=['--min-radius',str(case['min_radius'])]
    if case.get('sub_iterations'):command+=['-i',str(case['sub_iterations'])]
    digest=hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    started=time.perf_counter()
    with (folder/'stdout.txt').open('w') as stdout,(folder/'stderr.txt').open('w') as stderr:
        result=subprocess.run(['/usr/bin/time','-f','%e %U %S %M','-o',str(folder/'resource.time'),*command],stdout=stdout,stderr=stderr,timeout=case['seconds']+15,check=False)
    record=dict(case,command=command,binary_sha256=digest,returncode=result.returncode,wall_seconds=time.perf_counter()-started)
    if (folder/'points.real').exists():
        points=integer_points(folder/'points.real')
        ox,oy=points[0];points=[(x-ox,y-oy) for x,y in points]
        divisor=math.gcd(*(abs(v) for p in points for v in p)) or 1
        (folder/'points.pts').write_text(str(len(points))+'\n'+''.join(f'{x//divisor} {y//divisor}\n' for x,y in points))
        inspected=inspect_realization(case['orientations'],folder/'points.real',19)
        record['orientation_violations']=len(inspected['bad_vars'])
        audit=subprocess.run(['improvements/symmetry19/verify_hexagons',str(folder/'points.pts')],text=True,capture_output=True,check=False)
        record['verification']=json.loads(audit.stdout)
        record['verification_exit']=audit.returncode
    (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--binary',default='improvements/localizer/localizer_v2')
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--output',default='improvements/symmetry19/search')
    parser.add_argument('--manifest')
    args=parser.parse_args()
    if args.manifest:
        cases=json.loads(Path(args.manifest).read_text())
    else:
        cases=[{'binary':args.binary,'orientations':str(path),'symmetry':symmetric,'seed':19101+i,
                'seconds':args.seconds,'output':f'{args.output}/{path.stem}-'+('symmetric' if symmetric else 'free')}
               for i,path in enumerate(sorted(Path('improvements/symmetry19/variants').glob('*-relaxed.or')))
               for symmetric in (False,True)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for record in executor.map(run,cases):
            print(json.dumps(record),flush=True)
