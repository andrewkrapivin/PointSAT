#!/usr/bin/env python3
"""Independent integer checker for product-inequality impossibility proofs.

No LP, symbolic package, root helper, or BFP implementation is imported.
Bracket variables are canonical triples, not the producer's integer indices.
"""
import argparse
from collections import defaultdict
import itertools
import json
from pathlib import Path
import random
import re

def parity(t):return -1 if sum(t[i]>t[j]for i in range(3)for j in range(i+1,3))%2 else 1
def rank(t):
    a,b,c=sorted(t);return a+(b-1)*(b-2)//2+(c-1)*(c-2)*(c-3)//6
def read(path,n,partial=False):
    values={}
    for row in Path(path).read_text().splitlines():
        m=re.fullmatch(r'([AB])_\((\d+),\s*(\d+),\s*(\d+)\)',row.strip())
        if not m:raise ValueError('expected full GP orientation file')
        t=tuple(map(int,m.groups()[1:]));key=tuple(sorted(t))
        if len(set(t))!=3 or min(t)<1 or max(t)>n or key in values:raise ValueError('bad triple')
        values[key]=(1 if m[1]=='A' else -1)*parity(t)
    if not partial and set(values)!=set(itertools.combinations(range(1,n+1),3)):raise ValueError('incomplete model')
    if not values:raise ValueError('empty orientation model')
    return values
def brackets(anchor,remaining):
    b,c,d,e=remaining;a=anchor
    return [(a,b,c),(a,d,e),(a,b,d),(a,c,e),(a,b,e),(a,c,d)]
def check(proof,values,n):
    cancellation=defaultdict(int);premises=set();total_weight=0
    for item in proof['certificate']:
        weight=item['weight'];a=item['anchor'];rest=item['remaining']
        if type(weight)is not int or weight<=0 or len(rest)!=4 or len(set([a]+rest))!=5:
            raise ValueError('bad positive weighted inequality')
        if any(type(v)is not int or not 1<=v<=n for v in [a]+rest):raise ValueError('bad vertex')
        terms=brackets(a,rest)
        if any(tuple(sorted(t))not in values for t in terms):raise ValueError('certificate uses an unspecified orientation premise')
        s=[values[tuple(sorted(t))]*parity(t)for t in terms]
        signed_products=[s[0]*s[1],-s[2]*s[3],s[4]*s[5]]
        dominant=item['dominant_term'];smaller=item['smaller_term']
        if type(dominant)is not int or type(smaller)is not int or dominant not in range(3)or smaller not in range(3)or dominant==smaller:
            raise ValueError('bad term index')
        # The two non-dominant signed products must agree, with the opposite
        # sign to the dominant one. Thus its magnitude equals their sum.
        other=[i for i in range(3)if i!=dominant]
        if not signed_products[other[0]]==signed_products[other[1]]==-signed_products[dominant]:
            raise ValueError('signs do not entail strict magnitude inequality')
        for index in (2*dominant,2*dominant+1):cancellation[tuple(sorted(terms[index]))]+=weight
        for index in (2*smaller,2*smaller+1):cancellation[tuple(sorted(terms[index]))]-=weight
        for t in terms:
            key=tuple(sorted(t));premises.add(rank(key)*values[key])
        total_weight+=weight
    if not total_weight or any(cancellation.values()):raise ValueError('positive combination does not cancel')
    expected=sorted([-v for v in premises],key=abs)
    if expected!=proof['blocking_clause']:raise ValueError('blocking clause does not match exact premises')
    return {'verified':True,'arithmetic':'Python arbitrary-size integers only',
            'weighted_strict_inequalities':len(proof['certificate']),'weight_sum':total_weight,
            'distinct_bracket_variables':len(cancellation),'blocking_literals':len(expected),
            'claim':'Every orientation assignment retaining these explicitly specified premises has no real point realization.'}
def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def positive_tests():
    rng=random.Random(605219);checked=0;cases=40
    for trial in range(cases):
        n=5+trial%8;p=[]
        while len(p)<n:
            q=(rng.randrange(-10000,10001),rng.randrange(-10000,10001))
            if q not in p and all(cross(a,b,q)for a,b in itertools.combinations(p,2)):p.append(q)
        for five in itertools.combinations(range(n),5):
            for a in five:
                t=brackets(a,[v for v in five if v!=a]);v=[cross(*(p[i]for i in x))for x in t]
                products=[v[0]*v[1],-v[2]*v[3],v[4]*v[5]]
                assert sum(products)==0
                dominant=max(range(3),key=lambda i:abs(products[i]))
                for other in range(3):
                    if other!=dominant:assert abs(products[dominant])>abs(products[other]);checked+=1
    return {'random_general_position_sets':cases,'exact_GP_product_identities_and_strict_inequalities':checked}
def main():
    p=argparse.ArgumentParser();p.add_argument('--proof',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    proof=json.loads(Path(a.proof).read_text());values=read(proof['input'],proof['n'],partial=proof.get('partial')is True);report=check(proof,values,proof['n'])
    report.update(input_constraints=len(values),partial_input=proof.get('partial')is True)
    report.update(positive_tests());report['source_proof']=a.proof
    bad=json.loads(json.dumps(proof));bad['certificate'][0]['weight']+=1
    try:check(bad,values,proof['n'])
    except ValueError:report['corrupted_weight_rejected']=True
    else:raise AssertionError('corrupted proof accepted')
    missing=dict(values);first=proof['certificate'][0];del missing[tuple(sorted(brackets(first['anchor'],first['remaining'])[0]))]
    try:check(proof,missing,proof['n'])
    except ValueError:report['unspecified_premise_rejected']=True
    else:raise AssertionError('unspecified premise accepted')
    Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
