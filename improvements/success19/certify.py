#!/usr/bin/env python3
"""Compact and independently verify the discovered exact Euclidean C3 witness.

Pure Python integer-pair Q(sqrt3) checker; no search or prior verifier imported.
"""
import argparse
from functools import cmp_to_key
from itertools import combinations,permutations
import json
from pathlib import Path
import shutil
import subprocess
import hashlib

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
def add(x,y):return x[0]+y[0],x[1]+y[1]
def neg(x):return -x[0],-x[1]
def sub(x,y):return add(x,neg(y))
def mul(x,y):return x[0]*y[0]+3*x[1]*y[1],x[0]*y[1]+x[1]*y[0]
def scale(x,k):return x[0]*k,x[1]*k
def sign(x):
    a,b=x
    if not a:return (b>0)-(b<0)
    if not b:return (a>0)-(a<0)
    if(a>0)==(b>0):return (a>0)-(a<0)
    delta=a*a-3*b*b
    return ((a>0)-(a<0))*((delta>0)-(delta<0))
def determinant(a,b,c):return sub(mul(sub(b[0],a[0]),sub(c[1],a[1])),mul(sub(b[1],a[1]),sub(c[0],a[0])))
def read(path):
    rows=[list(map(int,row.split()))for row in path.read_text().splitlines()]
    assert rows[0]==[19]and len(rows)==20 and all(len(r)==4 for r in rows[1:])
    return [((r[0],r[1]),(r[2],r[3]))for r in rows[1:]]
def reconstruct(leaders):
    points=[]
    for a,b in leaders:
        points.extend([((2*a,0),(2*b,0)),((-a,-b),(-b,a)),((-a,b),(-b,-a))])
    return points+[((0,0),(0,0))]
def signs(points):return [sign(determinant(*(points[i]for i in t)))for t in combinations(range(19),3)]
def verify(points):
    # Check actual group action, not merely an orbit-label declaration.
    for i in range(0,18,3):
        for j in range(3):
            x,y=points[i+j];u,v=points[i+(j+1)%3]
            assert scale(u,2)==sub(neg(x),mul((0,1),y))
            assert scale(v,2)==sub(mul((0,1),x),y)
    assert points[18]==((0,0),(0,0))
    orientation={}
    for t in combinations(range(19),3):
        d=sign(determinant(*(points[i]for i in t)));assert d,'not general position'
        for p in permutations(t):
            inversions=sum(p[i]>p[j]for i in range(3)for j in range(i+1,3))
            orientation[p]=d*(-1 if inversions%2 else 1)
    def compare(i,j):return sign(sub(points[i][0],points[j][0]))or sign(sub(points[i][1],points[j][1]))
    ordered=sorted(range(19),key=cmp_to_key(compare));ranks={v:i for i,v in enumerate(ordered)}
    histogram=[0]*14;polygons=[];checked=0
    for selected in combinations(range(19),6):
        checked+=1;v=sorted(selected,key=ranks.get);lower=[];upper=[]
        for q in v:
            while len(lower)>=2 and orientation[lower[-2],lower[-1],q]<=0:lower.pop()
            lower.append(q)
        for q in reversed(v):
            while len(upper)>=2 and orientation[upper[-2],upper[-1],q]<=0:upper.pop()
            upper.append(q)
        hull=lower[:-1]+upper[:-1]
        if len(hull)!=6:continue
        inside=[q for q in range(19)if q not in selected and all(orientation[hull[e],hull[(e+1)%6],q]>0 for e in range(6))]
        histogram[len(inside)]+=1;polygons.append({'vertices':[i+1 for i in hull],'interior':[i+1 for i in inside]})
    assert not histogram[0]and not histogram[3]
    return {'valid':True,'exact_Euclidean_C3':True,'general_position':True,'triples_checked':969,
            'six_subsets_checked':checked,'interior_histogram':histogram,'convex_hexagons':polygons,
            'arithmetic':'independent Python arbitrary integers in Q(sqrt3)'}
def write_points(path,points):path.write_text('19\n'+''.join(' '.join(map(str,x+y))+'\n'for x,y in points))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);args=parser.parse_args();source=Path(args.source)
    original=read(source/'exact_c3.qsqrt3');reference=signs(original);assert all(reference)
    original_report=verify(original)
    leaders=[(original[i][0][0],original[i][1][0])for i in range(0,18,3)]
    extent=max(abs(v)for p in leaders for v in p)
    def rounded(grid):return [((2*x*grid+extent)//(2*extent),(2*y*grid+extent)//(2*extent))for x,y in leaders]
    chosen=None
    for grid in (10,30,100,300,1000,3000,10000,30000,100000,300000,1000000,3000000):
        candidate=rounded(grid)
        if signs(reconstruct(candidate))==reference:chosen=(grid,candidate);break
    assert chosen,'normalization failed'
    # Bounded one-dimensional scan; no claim of globally minimum coordinates.
    for grid in range(max(1,chosen[0]//3),chosen[0],max(1,chosen[0]//300)):
        candidate=rounded(grid)
        if signs(reconstruct(candidate))==reference:chosen=(grid,candidate);break
    grid,leaders=chosen;compact=reconstruct(leaders);report=verify(compact)
    write_points(OUT/'witness.qsqrt3',compact)
    (OUT/'representatives.txt').write_text(''.join(f'{a} {b}\n'for a,b in leaders))
    (OUT/'witness.or').write_text(''.join(('A'if sign(determinant(compact[i],compact[j],compact[k]))>0 else'B')+f'_({i+1}, {j+1}, {k+1})\n'
         for k in range(2,19)for j in range(1,k)for i in range(j)))
    # C++ reconstructs solely from orbit leaders. Nonleaders are placeholders;
    # their input-sign difference count is intentionally not a validation goal.
    seed=[(0,0)]*19
    for i,(a,b)in enumerate(leaders):seed[3*i]=(a,b)
    seedpath=OUT/'representative_input.pts';seedpath.write_text('19\n'+''.join(f'{x} {y}\n'for x,y in seed))
    check=subprocess.run([str(ROOT/'improvements/benchmarks/verify_c3'),'--input',str(seedpath),
                          '--cycles',str(ROOT/'improvements/symmetry19/decoded/center19-adjacent.cycles'),
                          '--orient',str(OUT/'witness.or'),'--output',str(OUT/'cpp_reconstructed.qsqrt3')],text=True,capture_output=True,check=True)
    cpp=json.loads(check.stdout);assert read(OUT/'cpp_reconstructed.qsqrt3')==compact
    assert cpp['valid']and cpp['orientation_violations']==0 and cpp['interior_histogram']==report['interior_histogram']
    snapshot=OUT/'original';snapshot.mkdir(exist_ok=True)
    for filename in('certificate.json','points.real','points.pts','exact_c3.qsqrt3','exact_c3.qsqrt3.or','exact_c3.cnf.model'):
        shutil.copyfile(source/filename,snapshot/filename)
    (OUT/'independent_python.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/'independent_cpp.json').write_text(json.dumps(cpp,indent=2)+'\n')
    certificate={'source':str(source),'normalization_grid':grid,'all_969_orientation_signs_preserved':True,
                 'representatives':leaders,'valid':True,'exact_Euclidean_C3':True,
                 'interior_histogram':report['interior_histogram'],'total_convex_hexagons':sum(report['interior_histogram']),
                 'witness_sha256':hashlib.sha256((OUT/'witness.qsqrt3').read_bytes()).hexdigest(),
                 'original_independent_python_check':{k:v for k,v in original_report.items()if k!='convex_hexagons'},
                 'cpp_check':cpp}
    (OUT/'certificate.json').write_text(json.dumps(certificate,indent=2)+'\n');print(json.dumps(certificate,indent=2))
if __name__=='__main__':main()
