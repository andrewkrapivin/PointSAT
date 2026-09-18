#!/usr/bin/env python3
"""Remove a label-only radial symmetry-breaking mismatch from a witness."""
import functools
import itertools
import json
from pathlib import Path
import subprocess
from pysat.formula import CNF
from pysat.solvers import Cadical195
from matched import ROOT,cross,digest
from audit_sat import rank

directory=ROOT/'improvements/benchmarks/successes/sat-guided23-case33'
tokens=list(map(int,(directory/'normalized.pts').read_text().split()))
p=list(zip(tokens[1::2],tokens[2::2]));n=len(p)
anchor=min(range(n),key=lambda i:p[i])
order=[i for i in range(n) if i!=anchor]
def compare(a,b):
    value=cross(p[anchor],p[a],p[b]);assert value
    return -1 if value>0 else 1
order=[anchor]+sorted(order,key=functools.cmp_to_key(compare))
q=[p[i] for i in order]
assert all(cross(q[0],q[i],q[j])>0 for i in range(1,n) for j in range(i+1,n))
lits=sorted((rank(a,b,c)*(1 if cross(q[a],q[b],q[c])>0 else -1)
             for a,b,c in itertools.combinations(range(n),3)),key=abs)
formula=CNF(from_file=str(ROOT/'7gon-6hole-23-compact.cnf'))
with Cadical195(bootstrap_with=formula.clauses) as solver:
    sat=solver.solve(assumptions=lits)
    assert sat,'Unexpected failure after radial symmetry-breaking relabel'
    full=solver.get_model();model=set(full)
    violations=sum(not any(lit in model for lit in clause) for clause in formula.clauses)
    assert violations==0
pts=directory/'radial_canonical.pts'
pts.write_text(str(n)+'\n'+''.join(f'{x} {y}\n' for x,y in q))
(directory/'radial_canonical.model').write_text('v '+' '.join(map(str,full))+' 0\n')
v=subprocess.run([str(ROOT/'direct/verify'),'--input',str(pts),'--gon','7','--hole','6'],text=True,capture_output=True)
assert v.returncode==0
report={'radial_anchor_original_1based':anchor+1,'new_labels_to_original_labels_1based':[i+1 for i in order],
        'coordinates_unchanged_up_to_relabeling':True,'full_original_cnf_satisfiable':sat,
        'original_clauses_checked':len(formula.clauses),'violated_original_clauses':violations,
        'integer_points_sha256':digest(pts),'geometry':json.loads(v.stdout),
        'interpretation':'Original Localizer failure included a label-only radial symmetry-breaking mismatch. Relabeling the same valid geometric points supplies a full CNF model.'}
(directory/'radial_certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
