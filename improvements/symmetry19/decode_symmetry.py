"""Test explicit C3 orbit-numbering hypotheses against the abstract geometry.

For 19 points (six 3-cycles and one fixed point), the 969 triples form 327
orbits: (969 + 2*6)/3. The supplied CNF appears to reserve that many primary
variables. No hypothesis is accepted without a complete four-point audit.
"""
import argparse
import itertools
import json
from pathlib import Path
from analyze_model import audit


def parity(values):
    return -1 if sum(values[i]>values[j] for i in range(3) for j in range(i+1,3))%2 else 1


def expand(values, n, center, layout, offset=0):
    moving=[i for i in range(n) if i!=center]
    if layout=='adjacent':cycles=[moving[i:i+3] for i in range(0,n-1,3)]
    else:cycles=[[moving[i],moving[i+6],moving[i+12]] for i in range(6)]
    permutation=list(range(n))
    for cycle in cycles:
        for i,v in enumerate(cycle):permutation[v]=cycle[(i+1)%3]
    representatives={};signs={}
    for triple in itertools.combinations(range(n),3):
        orbit=[];current=triple
        for _ in range(3):
            orbit.append((tuple(sorted(current)),parity(current)))
            current=tuple(permutation[v] for v in current)
        representative,sign=min(orbit)
        if representative not in representatives:representatives[representative]=len(representatives)+1+offset
        signs[triple]=sign*values[representatives[representative]]
    return signs,cycles,len(representatives)


def four_bad(signs,n):
    def orient(i,j,k):return parity((i,j,k))*signs[tuple(sorted((i,j,k)))]
    bad=0
    for ids in itertools.combinations(range(n),4):
        edges=[(i,j) for i in ids for j in ids if i!=j and all(orient(i,j,k)>0 for k in ids if k!=i and k!=j)]
        if len(edges) not in (3,4) or len({i for i,j in edges})!=len(edges) or len({j for i,j in edges})!=len(edges):bad+=1
    return bad


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('model')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    values={abs(v):1 if v>0 else -1 for line in Path(args.model).read_text().splitlines()
            if line.startswith('v ') for v in map(int,line.split()[1:]) if v}
    results=[];out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    for center in range(19):
        for layout in ('adjacent','blocks'):
            signs,cycles,count=expand(values,19,center,layout)
            bad=four_bad(signs,19)
            record={'center':center+1,'layout':layout,'primary_variables':count,'bad_four_point_hulls':bad}
            if not bad:
                record.update(audit(signs,19))
                stem=out/f'center{center+1}-{layout}'
                stem.with_suffix('.or').write_text(''.join(f"{'A' if s>0 else 'B'}_{tuple(v+1 for v in triple)}\n" for triple,s in signs.items()))
                stem.with_suffix('.cycles').write_text(''.join(' '.join(str(v+1) for v in cycle)+'\n' for cycle in cycles))
                stem.with_suffix('.fixed').write_text(f'{center+1}:0,0\n')
            results.append(record)
            print(json.dumps(record),flush=True)
    (out/'hypotheses.json').write_text(json.dumps(results,indent=2)+'\n')
