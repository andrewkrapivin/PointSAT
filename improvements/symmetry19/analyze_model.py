"""Decode a SAT model with explicitly selected triple numbering.

The combinatorial audit finds hull edges directly from the chirotope. This is
not a realizability proof. Independent geometric verification is still needed.
"""
import argparse
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sat_orient_conversion import invert_rank


def decode(path, n, numbering):
    values = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith('v '):
            for lit in map(int,line.split()[1:]):
                if lit:
                    values[abs(lit)] = 1 if lit>0 else -1
    triples = list(itertools.combinations(range(n),3))
    if numbering=='colex':
        triples = [tuple(i-1 for i in invert_rank(v,n)) for v in range(1,len(triples)+1)]
    if any(v not in values for v in range(1,len(triples)+1)):
        raise ValueError('SAT model missing orientation variables')
    return {triple:values[v] for v,triple in enumerate(triples,1)}


def audit(signs,n):
    def orientation(i,j,k):
        if len({i,j,k})<3:return 0
        parity=sum(a>b for a,b in ((i,j),(i,k),(j,k)))%2
        return (-1 if parity else 1)*signs[tuple(sorted((i,j,k)))]
    bad_hulls=0
    for ids in itertools.combinations(range(n),4):
        edges=[(i,j) for i in ids for j in ids if i!=j and all(orientation(i,j,k)>0 for k in ids if k!=i and k!=j)]
        if len(edges) not in (3,4) or len({i for i,j in edges})!=len(edges) or len({j for i,j in edges})!=len(edges):
            bad_hulls+=1
    histogram=[0]*(n-5)
    hexagons=0
    for ids in itertools.combinations(range(n),6):
        edges=[(i,j) for i in ids for j in ids if i!=j and all(orientation(i,j,k)>0 for k in ids if k!=i and k!=j)]
        if len(edges)!=6 or len({i for i,j in edges})!=6 or len({j for i,j in edges})!=6:
            continue
        interior=sum(all(orientation(i,j,k)>0 for i,j in edges) for k in range(n) if k not in ids)
        histogram[interior]+=1;hexagons+=1
    return {'n':n,'bad_four_point_hulls':bad_hulls,'abstract_convex_hexagons':hexagons,
            'interior_histogram':histogram,'combinatorial_target_met':bad_hulls==0 and histogram[0]==0 and histogram[3]==0}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('model')
    parser.add_argument('--n',type=int,default=19)
    parser.add_argument('--numbering',choices=('lex','colex'),default='lex')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    signs=decode(args.model,args.n,args.numbering)
    Path(args.output).write_text(''.join(f"{'A' if s>0 else 'B'}_{tuple(i+1 for i in t)}\n" for t,s in signs.items()))
    print(json.dumps(audit(signs,args.n)))
