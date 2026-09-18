#!/usr/bin/env python3
"""Check frozen orientation projections against ORIGINAL, unshuffled CNFs.

The generator used Kissat. This audit uses CaDiCaL under all projected literals,
then independently scans every original clause against the returned full model.
It is not, and does not claim to be, a geometric realizability test.
"""
import argparse
import json
from pathlib import Path
import time
from pysat.formula import CNF
from pysat.solvers import Cadical195
from matched import ROOT,constraints,digest

def rank(a,b,c):
    a,b,c=sorted((a+1,b+1,c+1))
    return a+(b-1)*(b-2)//2+(c-1)*(c-2)*(c-3)//6

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();cases=json.loads(Path(args.manifest).read_text())['cases'];results=[]
    for problem in sorted({c['problem'] for c in cases}):
        group=[c for c in cases if c['problem']==problem]
        formula_path=ROOT/group[0]['generation_result']['cnf']
        formula=CNF(from_file=str(formula_path))
        with Cadical195(bootstrap_with=formula.clauses) as solver:
            for case in group:
                orient=ROOT/case['orientation'];assert digest(orient)==case['sha256']
                lits=[rank(a,b,c)*s for a,b,c,s in constraints(orient)]
                assert len({abs(lit) for lit in lits})==len(lits)
                start=time.process_time();sat=solver.solve(assumptions=lits)
                if not sat: raise AssertionError('Orientation projection is UNSAT: '+case['id'])
                model=set(solver.get_model())
                violated=sum(not any(lit in model for lit in clause) for clause in formula.clauses)
                wrong_assumptions=sum(lit not in model for lit in lits)
                assert violated==wrong_assumptions==0
                result={'case':case['id'],'problem':problem,'sat_under_all_orientation_literals':sat,
                        'cnf_sha256':digest(formula_path),'orientation_sha256':case['sha256'],
                        'variables':formula.nv,'clauses':len(formula.clauses),
                        'violated_original_clauses':violated,'wrong_orientation_literals':wrong_assumptions,
                        'cpu_seconds':time.process_time()-start}
                print(json.dumps(result),flush=True);results.append(result)
    Path(args.output).write_text(json.dumps({'cases':results,'all_passed':True},indent=2)+'\n')

if __name__=='__main__':main()
