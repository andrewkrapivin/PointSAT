#!/usr/bin/env python3
"""Exact geometry audit of a native job, including saved near-best candidates."""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
def indexed_to_integer(path):
    rows=[line.split() for line in path.read_text().splitlines() if line.strip()]
    if any(len(row)!=3 or int(row[0])!=i+1 for i,row in enumerate(rows)):
        raise ValueError('Invalid indexed coordinate file: '+str(path))
    points=[(Fraction(row[1]),Fraction(row[2])) for row in rows]
    scale=math.lcm(*(v.denominator for p in points for v in p))
    integer=[(int(x*scale),int(y*scale)) for x,y in points]
    ox,oy=integer[0]
    integer=[(x-ox,y-oy) for x,y in integer]
    divisor=math.gcd(*(abs(v) for p in integer for v in p)) or 1
    target=path.with_suffix('.exact.pts')
    target.write_text(str(len(integer))+'\n'+''.join(f'{x//divisor} {y//divisor}\n' for x,y in integer))
    return target

def audit(path,lattice=False):
    exact=indexed_to_integer(path) if path.suffix=='.real' else path
    command=[str(ROOT/'improvements/symmetry19/verify_hexagons'),str(exact)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=20)
    if result.returncode not in (0,1):
        raise RuntimeError('Exact verifier failed: '+result.stderr)
    record=json.loads(result.stdout)
    record.update(input=str(path),certificate=str(exact),
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    record['score']=record['interior_histogram'][0]+record['interior_histogram'][3]
    if lattice:
        command=[str(ROOT/'improvements/benchmarks/verify_c3'),'--input',str(exact),
                 '--cycles',str(ROOT/'improvements/symmetry19/decoded/center19-adjacent.cycles'),
                 '--lattice','--output',str(exact)+'.qsqrt3']
        result=subprocess.run(command,capture_output=True,text=True,timeout=20)
        if result.returncode not in (0,1):
            raise RuntimeError('Exact C3 verifier failed: '+result.stderr)
        record['exact_c3']=json.loads(result.stdout)
    return record

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--geometry',type=Path)
    parser.add_argument('--localizer-prefix',type=Path)
    parser.add_argument('--lattice',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    if bool(a.geometry)==bool(a.localizer_prefix):
        raise ValueError('Specify exactly one native output family')
    if a.geometry:
        files=[a.geometry,*sorted(a.geometry.parent.glob(a.geometry.name+'.pool-*.pts'))]
        current=Path(str(a.geometry)+'.current.pts')
        if current.exists():files.append(current)
    else:
        files=sorted(a.localizer_prefix.parent.glob(a.localizer_prefix.name+'*.real'))
    records=[];seen=set()
    for path in files:
        if not path.exists():continue
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:continue
        seen.add(digest)
        records.append(audit(path,a.lattice))
    if not records:raise ValueError('No native coordinates to audit')
    best=min(records,key=lambda r:(not r['valid'],r['score'],r['collinear_triples']))
    summary={'candidates_audited':len(records),'any_valid':any(r['valid'] for r in records),
             'best_score':best['score'],'best_certificate':best['certificate'],'records':records}
    temporary=a.output.with_suffix(a.output.suffix+'.tmp')
    temporary.write_text(json.dumps(summary,indent=2)+'\n');temporary.replace(a.output)
    print(json.dumps({'candidates_audited':len(records),'any_valid':summary['any_valid'],
                      'best_score':summary['best_score'],'best_certificate':summary['best_certificate']}))
if __name__=='__main__':main()

