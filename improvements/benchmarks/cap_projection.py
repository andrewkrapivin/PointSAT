#!/usr/bin/env python3
"""Exhaust all affine x-projection orders of a FIXED integer point set.

No point moves. Boundaries are perpendicular to point-pair differences. Every
open interval between adjacent oriented rays has one constant strict x order;
their integer sum lies strictly inside that interval. The cap chain DP counts
all length-k increasing-x chains with consecutive clockwise turns.
"""
import argparse
import functools
import itertools
import json
import math
from pathlib import Path
import time

def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def count(order,turn,k):
    n=len(order);previous=[[0]*n for _ in range(n)]
    for j in range(n):
        for h in range(j+1,n):previous[j][h]=1
    for length in range(3,k+1):
        current=[[0]*n for _ in range(n)]
        for j in range(length-2,n-1):
            for h in range(j+1,n):
                current[j][h]=sum(previous[i][j] for i in range(length-3,j)
                                   if turn[order[i]][order[j]][order[h]])
        previous=current
    return sum(sum(row) for row in previous)

def scan(p,k=5):
    n=len(p)
    turns=[[[cross(p[i],p[j],p[h])<0 for h in range(n)]for j in range(n)]for i in range(n)]
    rays=set()
    for a,b in itertools.combinations(p,2):
        x,y=a[1]-b[1],b[0]-a[0]
        divisor=math.gcd(x,y)
        if not divisor:raise ValueError('Duplicate points')
        x//=divisor;y//=divisor;rays.add((x,y));rays.add((-x,-y))
    def half(v):return v[1]<0 or (v[1]==0 and v[0]<0)
    def compare(a,b):
        if half(a)!=half(b):return 1 if half(a) else -1
        d=a[0]*b[1]-a[1]*b[0]
        return -1 if d>0 else 1 if d<0 else 0
    rays=sorted(rays,key=functools.cmp_to_key(compare))
    best=None;scanned=0;hist={}
    for a,b in zip(rays,rays[1:]+rays[:1]):
        u=(a[0]+b[0],a[1]+b[1]);assert u!=(0,0)
        values=[u[0]*x+u[1]*y for x,y in p]
        order=sorted(range(n),key=lambda i:values[i])
        assert all(values[i]<values[j] for i,j in zip(order,order[1:]))
        caps=count(order,turns,k);scanned+=1;hist[caps]=hist.get(caps,0)+1
        if best is None or caps<best['caps']:
            best={'caps':caps,'direction':u,'new_to_old_1based':[i+1 for i in order]}
        if caps==0:break
    return {'n':n,'cap_size':k,'projection_intervals_total':len(rays),'intervals_scanned':scanned,
            'exhausted':scanned==len(rays),'best':best,'cap_count_histogram':hist}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--cap',type=int,default=5);a=parser.parse_args()
    words=list(map(int,Path(a.input).read_text().split()));n=words[0]
    assert len(words)==2*n+1 and 3<=a.cap<=n
    p=list(zip(words[1::2],words[2::2]));start=time.monotonic();report=scan(p,a.cap)
    report.update(seconds=time.monotonic()-start,source=a.input)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    if report['best']['caps']==0:
        x,y=report['best']['direction']
        q=[(x*p[i-1][0]+y*p[i-1][1],-y*p[i-1][0]+x*p[i-1][1])for i in report['best']['new_to_old_1based']]
        common=math.gcd(*(abs(v)for pair in q for v in pair)) or 1
        q=[(a//common,b//common)for a,b in q]
        pts=output.with_suffix('.pts');pts.write_text(str(n)+'\n'+''.join(f'{x} {y}\n'for x,y in q))
        report['witness']=str(pts)
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
