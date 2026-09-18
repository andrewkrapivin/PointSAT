#!/usr/bin/env python3
"""Independent numeric checks of lazy abstract19 histograms and learned cuts."""
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from matched import ROOT,HERE,constraints,cross
from audit_sat import rank

spec=importlib.util.spec_from_file_location('lazy_search_under_test',ROOT/'improvements/lazy19/search.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def cube(p):
    values={rank(i,j,k):(1 if cross(p[i],p[j],p[k])>0 else -1)
            for i,j,k in itertools.combinations(range(len(p)),3)}
    return [i*values[i]for i in range(1,len(values)+1)]

def known_cube():
    values={}
    for a,b,c,s in constraints(ROOT/'improvements/symmetry19/decoded/center19-adjacent.or'):
        parity=sum(x>y for x,y in ((a,b),(a,c),(b,c)))%2
        values[rank(a,b,c)]=s*(-1 if parity else 1)
    return [i*values[i]for i in range(1,970)]

def main():
    rng=random.Random(53719);known=set(known_cube());numeric_checks=0;cut_checks=0;base_checks=0
    with tempfile.TemporaryDirectory(dir=HERE)as tmp:
        pointfile=Path(tmp)/'points.pts'
        for n in (6,9,12,15,19):
            fixtures=[]
            for _ in range(8):
                while True:
                    p=[(rng.randrange(-10000,10001),rng.randrange(-10000,10001))for _ in range(n)]
                    if all(cross(*triple)!=0 for triple in itertools.combinations(p,3)):break
                fixtures.append((p,cube(p)))
            request=''.join(' '.join(map(str,c))+' 0\n'for p,c in fixtures)
            result=subprocess.run([str(ROOT/'improvements/lazy19/audit'),str(n),'128'],input=request,text=True,capture_output=True,check=True)
            reports=[json.loads(line)for line in result.stdout.splitlines()];assert len(reports)==len(fixtures)
            for (p,c),report in zip(fixtures,reports):
                pointfile.write_text(str(n)+'\n'+''.join(f'{x} {y}\n'for x,y in p))
                numeric=subprocess.run([str(ROOT/'improvements/symmetry19/verify_hexagons'),str(pointfile)],text=True,capture_output=True)
                assert numeric.returncode in(0,1),numeric.stderr
                independently=json.loads(numeric.stdout)
                assert report['histogram']==independently['interior_histogram'],(n,report,independently)
                assert report['six_subsets']==math.comb(n,6);numeric_checks+=1
                truth=set(c)
                for clause in report['cuts']:
                    assert clause and all(-lit in truth for lit in clause)
                    if n==19:assert any(lit in known for lit in clause),'valid known abstracttarget excluded'
                    cut_checks+=1
            # Scan every generated base clause against several true geometries.
            selected=[set(c)for p,c in fixtures[:2]]
            if n==19:selected.append(known)
            for clause in module.base_clauses(n):
                assert all(any(lit in assignment for lit in clause)for assignment in selected),(n,clause)
                base_checks+=len(selected)
    expected=subprocess.run([str(ROOT/'improvements/lazy19/audit'),'19','128'],
                            input=' '.join(map(str,known_cube()))+' 0\n',text=True,capture_output=True,check=True)
    known_report=json.loads(expected.stdout)
    assert known_report['histogram'][0]==known_report['histogram'][3]==0 and not known_report['cuts']
    summary={'status':'passed','random_general_position_geometry_fixtures':numeric_checks,
             'learned_cuts_falsified_by_input':cut_checks,'all_n19_cuts_satisfied_by_known_valid_abstract_target':True,
             'base_clause_assignment_checks':base_checks,'known_abstract_target_histogram':known_report['histogram']}
    (HERE/'lazy19_independent_tests.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
