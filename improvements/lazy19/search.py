"""Lazy rank-3 order-type SAT, without any combinatorial/geometric C3 constraint.

Every generated cut is necessary for the forbidden-interior-count property.
SAT models are abstract candidates, NEVER certificates of realizability.
"""
import argparse
from itertools import combinations, product
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import os

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sat_orient_conversion import orient, parse_constraints, integer_points, det, get_orientations
from pysat.solvers import Cadical195
from pysat.card import ITotalizer


def lit(a,b,c):
    sign=-1 if ((a>b)+(a>c)+(b>c))%2 else 1
    return sign*orient(a,b,c)


def base_clauses(n):
    # The rank-3 Grassmann-Pluecker sign axiom: the three displayed
    # products cannot all have the same sign. Encode all16 forbidden cubes.
    for five in combinations(range(1,n+1),5):
        for a in five:
            b,c,d,e=[v for v in five if v!=a]
            variables=[lit(a,b,c),lit(a,d,e),lit(a,b,d),lit(a,c,e),lit(a,b,e),lit(a,c,d)]
            for target in (-1,1):
                for u,v,w in product((-1,1),repeat=3):
                    signs=(u,target*u,v,-target*v,w,target*w)
                    yield [-s*x for s,x in zip(signs,variables)]
    # Exclude positive4-element circuits: precisely the two non-acyclic
    # alternating orientation patterns on each sorted quadruple.
    for a,b,c,d in combinations(range(1,n+1),4):
        variables=[lit(a,b,c),-lit(a,b,d),lit(a,c,d),-lit(b,c,d)]
        yield variables
        yield [-v for v in variables]


def read_cube(path,n):
    result={orient(*triple):sign*lit(*triple)//orient(*triple) for sign,triple in parse_constraints(path)}
    count=n*(n-1)*(n-2)//6
    if set(result)!=set(range(1,count+1)):raise ValueError('complete orientation file required')
    return [v*result[v] for v in range(1,count+1)]


def point_cube(p):
    out=[]
    for k in range(2,len(p)):
        for j in range(1,k):
            for i in range(j):
                d=det(p[i],p[j],p[k])
                if not d:raise ValueError('degenerate seed geometry')
                out.append((len(out)+1)*(1 if d>0 else -1))
    return out


def geometric_cube(path):return point_cube(integer_points(path))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--n',type=int,default=19)
    parser.add_argument('--known',default='improvements/symmetry19/decoded/center19-adjacent.or')
    parser.add_argument('--phase-real')
    parser.add_argument('--phase-points',help='integer .pts seed; also snapshot as output/phase.real')
    parser.add_argument('--output',required=True)
    parser.add_argument('--seconds',type=float,default=900)
    parser.add_argument('--samples',type=int,default=32)
    parser.add_argument('--seed',type=int,default=19541)
    parser.add_argument('--audit',default='improvements/lazy19/audit')
    parser.add_argument('--cuts-per-round',type=int,default=128)
    parser.add_argument('--distance-limit',type=int,help='enumerate increasing Hamming balls around --phase-real')
    parser.add_argument('--bfp-seconds',type=float,default=0,help='optional LP filter; prune only after independent exact proof verification')
    parser.add_argument('--bfp-relax-mutations',action='store_true')
    parser.add_argument('--proof',action='append',default=[],help='load a previously independently verified colex BFP blocking clause')
    parser.add_argument('--bfp-script',default='improvements/realizability/bfp.py')
    parser.add_argument('--proof-verifier',default='improvements/benchmarks/verify_bfp.py')
    args=parser.parse_args();rng=random.Random(args.seed)
    folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();log=(folder/'events.jsonl').open('a',buffering=1)
    def event(**values):
        values['elapsed']=time.monotonic()-start
        row=json.dumps(values);log.write(row+'\n');print(row,flush=True)
    solver=Cadical195();clauses=0
    for clause in base_clauses(args.n):solver.add_clause(clause);clauses+=1
    known=read_cube(args.known,args.n);count=len(known)
    if not solver.solve(assumptions=known):raise RuntimeError('known candidate violates new base encoding')
    event(event='initialized',base_clauses=clauses,variables=count,seed=args.seed,symmetry=False)
    worker=subprocess.Popen([args.audit,str(args.n),str(args.cuts_per_round)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    def audit(cube):
        worker.stdin.write(' '.join(map(str,cube))+' 0\n');worker.stdin.flush()
        line=worker.stdout.readline()
        if not line:raise RuntimeError('native auditor exited')
        return json.loads(line)
    known_audit=audit(known)
    if known_audit['histogram'][0] or known_audit['histogram'][3]:raise RuntimeError('known abstract candidate fails target')
    solver.add_clause([-v for v in known])
    for filename in args.proof:
        proof=json.loads(Path(filename).read_text())
        checked=folder/('loaded-'+Path(filename).stem+'.checked.json')
        verify=subprocess.run(['python3',args.proof_verifier,'--proof',filename,'--output',str(checked)],
                              capture_output=True,text=True,timeout=30)
        if verify.returncode or proof['n']!=args.n:raise RuntimeError('loaded proof failed independent validation')
        solver.add_clause(proof['blocking_clause'])
        event(event='loaded_realizability_cut',file=filename,literals=len(proof['blocking_clause']))
    if args.phase_points:
        if args.phase_real:raise ValueError('choose only one phase geometry format')
        values=list(map(int,Path(args.phase_points).read_text().split()))
        if not values or values[0]!=args.n or len(values)!=1+2*args.n:raise ValueError('invalid integer points')
        points=list(zip(values[1::2],values[2::2]))
        phase=point_cube(points)
        (folder/'phase.real').write_text(''.join(f'{i} {x} {y}\n' for i,(x,y) in enumerate(points,1)))
    else:phase=geometric_cube(args.phase_real) if args.phase_real else known
    if len(phase)!=count:raise ValueError('phase geometry point count mismatch')
    solver.set_phases(phase)
    totalizer=None;bound=0
    if args.distance_limit is not None:
        if not 0<=args.distance_limit<count:raise ValueError('distance limit outside0..variables-1')
        totalizer=ITotalizer(lits=[-v for v in phase],ubound=args.distance_limit,top_id=count)
        for clause in totalizer.cnf.clauses:solver.add_clause(clause)
        event(event='distance_encoding',clauses=len(totalizer.cnf.clauses),limit=args.distance_limit)
    accepted=0;rounds=0;cuts=0;proofs=0
    try:
        while time.monotonic()-start<args.seconds and accepted<args.samples:
            solver.conf_budget(100000)
            sat=solver.solve_limited(assumptions=[-totalizer.rhs[bound]] if totalizer else [])
            if sat is None:
                event(event='conflict_budget',round=rounds);continue
            if not sat:
                if totalizer:
                    event(event='distance_exhausted',bound=bound,accepted=accepted)
                    bound+=1
                    if bound<=args.distance_limit:continue
                event(event='unsat_remaining');break
            model={abs(v):v for v in solver.get_model()};cube=[model[v] for v in range(1,count+1)]
            report=audit(cube);rounds+=1
            bad=report['histogram'][0]+report['histogram'][3]
            if bad:
                for clause in report['cuts']:solver.add_clause(clause)
                cuts+=len(report['cuts'])
                if rounds<=10 or rounds%50==0:event(event='refine',round=rounds,bad=bad,total_cuts=cuts)
            else:
                if args.bfp_seconds:
                    candidate=folder/'bfp'/f'round{rounds:06d}'
                    candidate.parent.mkdir(exist_ok=True)
                    candidate.with_suffix('.or').write_text(get_orientations(cube,args.n))
                    command=['python3',args.bfp_script,str(candidate.with_suffix('.or')),
                             '--n',str(args.n),'--seconds',str(args.bfp_seconds),'--output',str(candidate.with_suffix('.proof.json'))]
                    if args.bfp_relax_mutations:command.append('--relax-mutations')
                    environment=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
                    try:
                        with candidate.with_suffix('.log').open('w') as logfile:
                            subprocess.run(command,stdout=logfile,stderr=subprocess.STDOUT,env=environment,
                                           timeout=args.bfp_seconds+90,check=True)
                        proof=json.loads(candidate.with_suffix('.proof.json').read_text())
                    except (subprocess.SubprocessError,OSError,json.JSONDecodeError) as error:
                        proof={'status':'UNKNOWN'};event(event='bfp_unknown',reason=str(error),round=rounds)
                    if proof['status']=='PROVED_NONREALIZABLE':
                        verify=subprocess.run(['python3',args.proof_verifier,'--proof',
                                               str(candidate.with_suffix('.proof.json')),'--output',str(candidate.with_suffix('.checked.json'))],
                                              capture_output=True,text=True,timeout=30)
                        if verify.returncode:raise RuntimeError('independent BFP verification failed: '+verify.stderr)
                        clause=proof['blocking_clause']
                        if not clause or any(v==cube[abs(v)-1] for v in clause):raise RuntimeError('BFP clause does not exclude current model')
                        solver.add_clause(clause);proofs+=1
                        event(event='proved_nonrealizable',round=rounds,proofs=proofs,blocking_literals=len(clause))
                        continue
                prefix=folder/f'model{accepted:03d}'
                prefix.with_suffix('.or').write_text(get_orientations(cube,args.n))
                info={'cube':cube,'audit':report,'hamming_from_known':sum(a!=b for a,b in zip(cube,known)),
                      'hamming_from_geometry':sum(a!=b for a,b in zip(cube,phase)),
                      'elapsed':time.monotonic()-start,'rounds':rounds,'cuts':cuts,'bfp_status':proof['status'] if args.bfp_seconds else 'NOT_RUN'}
                prefix.with_suffix('.json').write_text(json.dumps(info,indent=2)+'\n')
                event(event='abstract_candidate',sample=accepted,round=rounds,hamming=info['hamming_from_known'],geometry_hamming=info['hamming_from_geometry'],histogram=report['histogram'])
                accepted+=1;solver.add_clause([-v for v in cube])
                # Start from the geometric phase each time, gently diversify.
                solver.set_phases([v if rng.random()>.005 else -v for v in phase])
    finally:
        worker.stdin.close();worker.wait(timeout=10);solver.delete();log.close()
        if totalizer:totalizer.delete()
    print(json.dumps({'event':'finished','accepted':accepted,'rounds':rounds,'cuts':cuts,'proofs':proofs,'elapsed':time.monotonic()-start}),flush=True)


if __name__=='__main__':main()
