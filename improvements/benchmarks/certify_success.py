#!/usr/bin/env python3
"""Preserve and independently certify SAT-guided geometric successes."""
import itertools
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from pysat.formula import CNF
from pysat.solvers import Cadical195
from matched import ROOT,cross,digest
from audit_sat import rank

parser=argparse.ArgumentParser()
parser.add_argument('--source',default='improvements/benchmarks/results/legacy23_v1/legacy23-with_flippable-33-s1')
parser.add_argument('--output',default='improvements/benchmarks/successes/sat-guided23-case33')
parser.add_argument('--provenance',default='Native v1 from random initialization, guided by legacy SAT-produced reduced orientation case33; Localizer seed1; 15s wall. No known coordinate seed supplied.')
args=parser.parse_args()
source=ROOT/args.source
out=ROOT/args.output
out.mkdir(parents=True,exist_ok=False)
for filename in ('points.real','points.pts','result.json','audit.json','stdout.log','stderr.log'):
    if (source/filename).exists():shutil.copyfile(source/filename,out/filename)
tokens=list(map(int,(out/'points.pts').read_text().split()))
p=list(zip(tokens[1::2],tokens[2::2]));assert tokens[0]==len(p)==23
triples=list(itertools.combinations(range(23),3))
signs=[(cross(p[a],p[b],p[c])>0)-(cross(p[a],p[b],p[c])<0) for a,b,c in triples]
assert all(signs)
ox=min(x for x,y in p);oy=min(y for x,y in p)
span=max(max(x for x,y in p)-ox,max(y for x,y in p)-oy)
used_grid=None
for grid in (100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000,100000000,1000000000,10000000000):
    q=[(((x-ox)*grid*2+span)//(2*span),((y-oy)*grid*2+span)//(2*span)) for x,y in p]
    got=[(cross(q[a],q[b],q[c])>0)-(cross(q[a],q[b],q[c])<0) for a,b,c in triples]
    if got==signs:used_grid=grid;break
assert used_grid
normalized=out/'normalized.pts'
normalized.write_text('23\n'+''.join(f'{x} {y}\n' for x,y in q))
v=subprocess.run([str(ROOT/'direct/verify'),'--input',str(normalized),'--gon','7','--hole','6'],text=True,capture_output=True)
assert v.returncode==0,v.stdout+v.stderr
geometry=json.loads(v.stdout)
lit=[rank(a,b,c)*s for (a,b,c),s in zip(triples,signs)]
formula=CNF(from_file=str(ROOT/'7gon-6hole-23-compact.cnf'))
with Cadical195(bootstrap_with=formula.clauses) as solver:
    sat=solver.solve(assumptions=lit)
    if sat:
        model=set(solver.get_model())
        violated=sum(not any(v in model for v in clause) for clause in formula.clauses)
        assert violated==0
        (out/'full_cnf.model').write_text('v '+' '.join(map(str,solver.get_model()))+' 0\n')
    else: violated=None
comparison=subprocess.run(['python3',str(ROOT/'direct/compare_points.py'),'--first',str(ROOT/'direct/seeds/paper23.pts'),
                           '--second',str(normalized)],text=True,capture_output=True,check=True)
record_path=source/('result.json' if (source/'result.json').exists() else 'audit.json')
record=json.loads(record_path.read_text())
report={'provenance':args.provenance,
        'classification':'SAT-guided geometric solution; exact input orientation status is recorded separately.',
        'original_run':record,'normalization_grid':used_grid,
        'normalized_sha256':digest(normalized),'all_1771_labeled_signs_preserved':True,
        'independent_int128_geometry':geometry,'original_full_cnf_sat_for_new_order_type':sat,
        'violated_original_clauses_in_extension':violated,'paper_comparison':json.loads(comparison.stdout)}
(out/'certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
