"""Biquadratic final-polynomial filter with exact rational certificates.

For each signed Grassmann-Pluecker relation P-Q+R=0, the term with
the unique sign has magnitude equal to the sum of the other two. Thus
log|dominant|-log|other| >0. A nonnegative, nonzero rational combination
of these inequalities with identically zero left side proves impossibility.

HiGHS only proposes weights. No non-realizability claim or blocking clause
is emitted without verifying their cancellation in exact integer arithmetic.
Failure to find this restricted certificate does NOT establish realizability.
"""
import argparse
from collections import Counter
from fractions import Fraction
from itertools import combinations
import json
import math
from pathlib import Path
import sys
import time
import warnings

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix,vstack

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sat_orient_conversion import orient,parse_constraints


def literal(a,b,c):
    return orient(a,b,c)*(-1 if ((a>b)+(a>c)+(b>c))%2 else 1)


def read_model(path,n,partial=False):
    values={}
    for sign,triple in parse_constraints(path):
        var=literal(*triple);v=abs(var)
        if v in values:raise ValueError('duplicate orientation')
        values[v]=sign*(1 if var>0 else -1)
    allowed=set(range(1,n*(n-1)*(n-2)//6+1))
    if not values or not set(values)<=allowed or (not partial and set(values)!=allowed):
        raise ValueError('full nonzero orientation model required unless --partial')
    return values


def inequalities(values,n,vertices=None):
    rows=[];witnesses=[]
    for five in combinations(vertices if vertices is not None else range(1,n+1),5):
        for a in five:
            b,c,d,e=[x for x in five if x!=a]
            vs=[literal(a,b,c),literal(a,d,e),literal(a,b,d),literal(a,c,e),literal(a,b,e),literal(a,c,d)]
            if any(abs(v) not in values for v in vs):continue
            signs=[values[abs(v)]*(1 if v>0 else -1) for v in vs]
            terms=[signs[0]*signs[1],-signs[2]*signs[3],signs[4]*signs[5]]
            if abs(sum(terms))==3:raise ValueError('orientation model violates GP sign axiom')
            dominant=terms.index(-sum(terms))
            for other in range(3):
                if other==dominant:continue
                row=Counter()
                for i in (2*dominant,2*dominant+1):row[abs(vs[i])]+=1
                for i in (2*other,2*other+1):row[abs(vs[i])]-=1
                rows.append(dict(row));witnesses.append({'anchor':a,'remaining':[b,c,d,e],
                                                        'dominant_term':dominant,'smaller_term':other})
    return rows,witnesses


def exact_weights(raw,rows):
    support=np.flatnonzero(raw>1e-9).tolist()
    if not support:return None
    for normalization in (1,max(raw)):
        for denominator in (10000,1000000,1000000000):
            weights=[Fraction(float(raw[i]/normalization)).limit_denominator(denominator) for i in support]
            if any(w<=0 for w in weights):continue
            scale=math.lcm(*(w.denominator for w in weights))
            integers=[w.numerator*(scale//w.denominator) for w in weights]
            total=Counter()
            for i,weight in zip(support,integers):
                for var,value in rows[i].items():total[var]+=weight*value
            if not any(total.values()):
                divisor=math.gcd(*integers)
                return [(i,w//divisor) for i,w in zip(support,integers)]
    # LP extrema usually have a small one-dimensional supported kernel.
    # Reconstruct that kernel over the rationals, rather than trusting floats.
    if len(support)<=1000:
        from sympy import Matrix
        from sympy.polys.matrices import DomainMatrix
        used=sorted({v for i in support for v in rows[i]})
        matrix=Matrix([[rows[i].get(v,0) for i in support] for v in used])
        kernel=DomainMatrix.from_Matrix(matrix).to_field().nullspace().to_Matrix()
        for j in range(kernel.rows):
            vector=kernel[j,:]
            if all(v<=0 for v in vector):vector=-vector
            if not all(v>=0 for v in vector) or not any(vector):continue
            scale=math.lcm(*(int(v.q) for v in vector))
            integers=[int(v*scale) for v in vector];divisor=math.gcd(*integers)
            return [(i,w//divisor) for i,w in zip(support,integers) if w]
    return None


def verify_certificate(certificate,values,n):
    total=Counter();premises=set();weight_sum=0
    for term in certificate:
        weight=term['weight'];a=term['anchor'];b,c,d,e=term['remaining']
        if type(weight)is not int or weight<=0 or len({a,b,c,d,e})!=5 or not all(1<=v<=n for v in (a,b,c,d,e)):
            raise ValueError('invalid certificate term')
        vs=[literal(a,b,c),literal(a,d,e),literal(a,b,d),literal(a,c,e),literal(a,b,e),literal(a,c,d)]
        signs=[values[abs(v)]*(1 if v>0 else -1) for v in vs]
        products=[signs[0]*signs[1],-signs[2]*signs[3],signs[4]*signs[5]]
        dominant=term['dominant_term'];other=term['smaller_term']
        if dominant not in range(3) or other not in range(3) or dominant==other or abs(sum(products))==3 or products[dominant]!=-sum(products):
            raise ValueError('invalid strict product inequality')
        for i in (2*dominant,2*dominant+1):total[abs(vs[i])]+=weight
        for i in (2*other,2*other+1):total[abs(vs[i])]-=weight
        premises.update(abs(v)*values[abs(v)] for v in vs);weight_sum+=weight
    if not weight_sum or any(total.values()):raise ValueError('certificate does not cancel exactly')
    return sorted((-v for v in premises),key=abs)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('orientations');parser.add_argument('--n',type=int,default=19)
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--output',required=True)
    parser.add_argument('--verify',help='verify an existing JSON proof without LP')
    parser.add_argument('--vertices',help='optional comma-separated subset of original point labels')
    parser.add_argument('--partial',action='store_true',help='use only GP identities whose six orientations are specified')
    parser.add_argument('--relax-mutations',action='store_true',help='drop orientations not occurring in any dominant GP product before seeking a stronger proof')
    args=parser.parse_args();start=time.monotonic();values=read_model(args.orientations,args.n,args.partial)
    if args.verify:
        proof=json.loads(Path(args.verify).read_text());clause=verify_certificate(proof['certificate'],values,args.n)
        if clause!=proof['blocking_clause']:raise ValueError('blocking clause mismatch')
        print(json.dumps({'verified':True,'inequalities':len(proof['certificate']),'blocked_literals':len(clause)}));return
    vertices=list(map(int,args.vertices.split(','))) if args.vertices else None
    if vertices is not None and (len(set(vertices))!=len(vertices) or not all(1<=v<=args.n for v in vertices)):
        raise ValueError('invalid vertex subset')
    rows,witnesses=inequalities(values,args.n,vertices);variables=args.n*(args.n-1)*(args.n-2)//6;m=len(rows)
    dropped=[]
    if args.relax_mutations:
        required={v for row in rows for v,c in row.items() if c>0}
        dropped=sorted(set(values)-required)
        values={v:s for v,s in values.items() if v in required}
        rows,witnesses=inequalities(values,args.n,vertices);m=len(rows)
    rr=[];cc=[];dd=[]
    for i,row in enumerate(rows):
        for v,c in row.items():rr.append(v-1);cc.append(i);dd.append(c)
    matrix=coo_matrix((dd,(rr,cc)),shape=(variables,m)).tocsr()
    equality=vstack([matrix,coo_matrix(np.ones((1,m)))]).tocsr()
    rhs=np.zeros(variables+1);rhs[-1]=1
    print(json.dumps({'event':'lp_start','inequalities':m,'log_variables':variables,'elapsed':time.monotonic()-start}),flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        answer=linprog(np.zeros(m),A_eq=equality,b_eq=rhs,bounds=(0,None),method='highs',options={'time_limit':args.seconds,'threads':1,
                       'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9})
    report={'input':args.orientations,'n':args.n,'vertices':vertices,'partial':args.partial,'dropped_orientations':dropped,
            'specified_orientations':len(values),'inequalities':m,'lp_status':int(answer.status),
            'lp_message':answer.message,'status':'UNKNOWN','certificate':None,'blocking_clause':None}
    if answer.status==0:
        report['numeric_support_size']=int(sum(answer.x>1e-9))
        report['numeric_max_residual']=float(np.max(np.abs(equality@answer.x-rhs)))
        print(json.dumps({'event':'numeric_candidate','support':report['numeric_support_size'],
                          'max_residual':report['numeric_max_residual']}),flush=True)
        weights=exact_weights(answer.x,rows)
        if weights:
            certificate=[dict(witnesses[i],weight=w) for i,w in weights]
            clause=verify_certificate(certificate,values,args.n)
            report.update(status='PROVED_NONREALIZABLE',certificate=certificate,blocking_clause=clause)
        else:report['status']='NUMERIC_CANDIDATE_UNCERTIFIED'
    elif answer.status==2:report['status']='NO_BFP_FOUND'
    report['seconds']=time.monotonic()-start
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('certificate','blocking_clause')},indent=2),flush=True)


if __name__=='__main__':main()
