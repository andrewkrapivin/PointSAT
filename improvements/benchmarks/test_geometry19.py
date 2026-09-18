#!/usr/bin/env python3
"""Independent differential test for native actual-geometry19 objective."""
import argparse
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
from matched import ROOT,HERE,cross,digest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--binary',default=str(ROOT/'improvements/localizer/geometry19'))
    parser.add_argument('--output',default=str(HERE/'geometry19_independent_tests.json'))
    args=parser.parse_args()
    rng=random.Random(549019);fixtures=[]
    for n in range(6,20):
        for _ in range(14):
            while True:
                p=[(rng.randrange(-1000,1001),rng.randrange(-1000,1001))for _ in range(n)]
                if all(cross(*t)!=0 for t in itertools.combinations(p,3)):break
            fixtures.append(p)
    fixtures.extend([[(i,i*i)for i in range(19)],[(i,-i*i)for i in range(19)],
                     [(10**11*x+5*10**14,10**11*y-5*10**14)for x,y in fixtures[-1]]])
    source=ROOT/'direct/seeds/paper23.pts';tokens=list(map(int,source.read_text().split()))
    fixtures.append(list(zip(tokens[1::2],tokens[2::2]))[:19])
    native=Path(args.binary).resolve();reference=ROOT/'improvements/symmetry19/verify_hexagons'
    records=[]
    with tempfile.TemporaryDirectory(dir=HERE)as tmp:
        path=Path(tmp)/'points.pts'
        for index,p in enumerate(fixtures):
            path.write_text(str(len(p))+'\n'+''.join(f'{x} {y}\n'for x,y in p))
            fast=subprocess.run([str(native),'--input',str(path),'--check'],text=True,capture_output=True)
            slow=subprocess.run([str(reference),str(path)],text=True,capture_output=True)
            assert fast.returncode in(0,1)and slow.returncode in(0,1),(fast.stderr,slow.stderr)
            a,b=json.loads(fast.stdout),json.loads(slow.stdout)
            expected=(b['interior_histogram'][0],b['interior_histogram'][3] if len(b['interior_histogram'])>3 else 0,b['collinear_triples'])
            got=(a['holes0'],a['holes3'],a['collinear_triples'])
            assert got==expected,(index,p,a,b)
            records.append({'n':len(p),'holes0':got[0],'holes3':got[1]})
    result={'status':'passed','general_position_cases':len(fixtures),'random_cases':196,'adversarial_cases':4,
            'native_sha256':digest(native),'reference_sha256':digest(reference),'cases':records}
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='cases'}))
if __name__=='__main__':main()
