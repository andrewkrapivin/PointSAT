#!/usr/bin/env python3
"""Independent unattended certificate API for PointSAT candidate coordinates.

No pipeline orientation-mapping or geometry code is imported. Decimal tokens
are read exactly. A fresh SAT instance checks the original CNF, and every clause
is then scanned against its full model. Geometry and exact C3 are separate tests.
"""
import argparse
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import time
from pysat.formula import CNF
from pysat.solvers import Cadical195
if __package__:
    from .matched import ROOT,HERE,integer_points,cross,cap_count,constraints,digest
else:
    from matched import ROOT,HERE,integer_points,cross,cap_count,constraints,digest

FAMILIES={'mixed23':(23,7,6,0),'holes29':(29,0,6,0),'gons32':(32,7,0,0),
          'caps26':(26,7,0,5),'hex19':(19,0,0,0),'symmetry19':(19,0,0,0)}

def colex_rank(triple):
    a,b,c=triple
    return a+(b-1)*(b-2)//2+(c-1)*(c-2)*(c-3)//6

def model_from_points(p):
    model=[]
    for k in range(2,len(p)):
        for j in range(1,k):
            for i in range(j):
                d=cross(p[i],p[j],p[k])
                if not d:return None
                model.append((len(model)+1)*(1 if d>0 else -1))
    return model

def model_from_orientations(path,n):
    values={}
    for a,b,c,s in constraints(path):
        triple=(a+1,b+1,c+1)
        if tuple(sorted(triple))!=triple:raise ValueError('Expected sorted algebraic triples')
        if not s:return None
        rank=colex_rank(triple)
        if rank in values:raise ValueError('Repeated algebraic triple')
        values[rank]=rank*s
    if set(values)!=set(range(1,n*(n-1)*(n-2)//6+1)):raise ValueError('Incomplete algebraic chirotope')
    return [values[i]for i in range(1,len(values)+1)]

def project(model,n,mapping):
    if model is None:return None,[]
    if not mapping:return model,[]
    data=json.loads(Path(mapping).read_text())
    if data['n']!=n:raise ValueError('Mapping n mismatch')
    expected=set(itertools.combinations(range(1,n+1),3));seen=set();assignment={};origins={};conflicts=[]
    for entry in data['entries']:
        triple=tuple(entry['triple']);literal=entry['literal']
        if triple not in expected or triple in seen or not isinstance(literal,int)or not literal:
            raise ValueError('Invalid or duplicate orientation map entry')
        seen.add(triple);v=model[colex_rank(triple)-1]
        truth=(1 if v>0 else -1)*(1 if literal>0 else -1);variable=abs(literal)
        if variable in assignment and assignment[variable]!=truth:
            conflicts.append({'variable':variable,'first_triple':origins[variable],'conflicting_triple':triple})
        else:assignment[variable]=truth;origins.setdefault(variable,triple)
    if seen!=expected:raise ValueError('Mapping does not cover all triples')
    if data.get('primary_variables',len(assignment))!=len(assignment):raise ValueError('Mapping primary-variable mismatch')
    return ([v*assignment[v]for v in sorted(assignment)]if not conflicts else None),conflicts

def check_cnf(model,n,cnf,mapping,directory,stem):
    projected,conflicts=project(model,n,mapping)
    result={'mapping_conflicts':conflicts,'mapping_consistent':not conflicts,'satisfiable':False}
    if model is None:result['reason']='not_general_position';return result
    if conflicts:result['reason']='orientation_map_inconsistent';return result
    if cnf is None:result.update(satisfiable=None,reason='CNF not requested');return result
    formula=CNF(from_file=str(cnf))
    if any(abs(v)>formula.nv for v in projected):raise ValueError('Projected variable exceeds original CNF header')
    start=time.monotonic()
    with Cadical195(bootstrap_with=formula.clauses)as solver:
        sat=solver.solve(assumptions=projected)
        result.update(satisfiable=bool(sat),cnf_sha256=digest(cnf),variables=formula.nv,
                      clauses=len(formula.clauses),projected_orientation_variables=len(projected))
        if sat:
            full=solver.get_model();truth=set(full)
            violated=sum(not any(v in truth for v in clause)for clause in formula.clauses)
            missing=sum(v not in truth for v in projected)
            if violated or missing:raise RuntimeError('Independent full-clause verification failed')
            target=directory/(stem+'.cnf.model');target.write_text('v '+' '.join(map(str,full))+' 0\n')
            result.update(violated_clauses=violated,wrong_orientation_assumptions=missing,
                          full_model=str(target),full_model_sha256=digest(target))
    result['seconds']=time.monotonic()-start
    return result

def numeric_geometry(p,pts,family):
    n,gon,hole,cap=FAMILIES[family]
    if n==19:
        command=[str(ROOT/'improvements/symmetry19/verify_hexagons'),str(pts)]
        large=True
    else:
        large=max(abs(v)for pair in p for v in pair)>10**18
        command=[str(ROOT/'direct'/('verify_big'if large else'verify')),'--input',str(pts),
                 '--gon',str(gon),'--hole',str(hole)]
        if not large:command+=['--cap',str(cap)]
    result=subprocess.run(command,text=True,capture_output=True,timeout=120)
    if result.returncode not in(0,1):raise RuntimeError('Numeric verifier failed: '+result.stderr)
    geometry=json.loads(result.stdout)
    if cap and large:
        geometry['convex_caps']=cap_count(p,cap);geometry['valid']=geometry['valid']and not geometry['convex_caps']
    return geometry

def audit_file(real,n,family,output,cnf=None,orientation_map=None,cycles=None,orient=None):
    if family not in FAMILIES or FAMILIES[family][0]!=n:raise ValueError('Explicit family/n mismatch')
    if family=='symmetry19'and not cycles:raise ValueError('symmetry19 requires explicit3cycles file')
    real=Path(real).resolve();directory=Path(output).resolve()
    signature={'real_sha256':digest(real),'family':family,'n':n,
               'cnf_sha256':digest(cnf)if cnf else None,'mapping_sha256':digest(orientation_map)if orientation_map else None,
               'cycles_sha256':digest(cycles)if cycles else None,'orient_sha256':digest(orient)if orient else None}
    certificate=directory/'certificate.json'
    if certificate.exists():
        previous=json.loads(certificate.read_text())
        if previous['input_signature']!=signature:raise ValueError('Existing certificate is for different inputs')
        return previous
    signature_path=directory/'input_signature.json'
    if directory.exists():
        if not signature_path.exists() or json.loads(signature_path.read_text())!=signature:
            raise ValueError('Output directory already contains unrelated or different inputs')
    else:directory.mkdir(parents=True)
    signature_path.write_text(json.dumps(signature,indent=2)+'\n')
    start=time.monotonic()
    snapshot=directory/'points.real';shutil.copyfile(real,snapshot)
    p=integer_points(snapshot)
    if len(p)!=n:raise ValueError('Wrong point count')
    pts=directory/'points.pts';pts.write_text(str(n)+'\n'+''.join(f'{x} {y}\n'for x,y in p))
    model=model_from_points(p);geometry=numeric_geometry(p,pts,family)
    cnf_report=check_cnf(model,n,cnf,orientation_map,directory,'numeric')
    report={'input_signature':signature,'source':str(real),'n':n,'family':family,
            'numeric_geometry':geometry,'numeric_cnf':cnf_report,'integer_points':str(pts),
            'integer_points_sha256':digest(pts),'exact_C3_symmetry_certified':False}
    if orient:
        report['original_orientation_violations']=sum(((d>0)-(d<0))!=s for a,b,c,s in constraints(orient)for d in[cross(p[a],p[b],p[c])])
    accepted=geometry['valid']and(cnf_report['satisfiable']is not False)
    if cycles:
        symbolic=directory/'exact_c3.qsqrt3'
        command=[str(HERE/'verify_c3'),'--input',str(pts),'--cycles',str(cycles),'--output',str(symbolic)]
        if orient:command+=['--orient',str(orient)]
        process=subprocess.run(command,text=True,capture_output=True,timeout=120)
        if process.returncode not in(0,1):raise RuntimeError('Algebraic verifier failed: '+process.stderr)
        algebraic=json.loads(process.stdout);algebraic_model=model_from_orientations(str(symbolic)+'.or',n)
        algebraic_cnf=check_cnf(algebraic_model,n,cnf,orientation_map,directory,'exact_c3')
        report.update(exact_C3_geometry=algebraic,exact_C3_cnf=algebraic_cnf,
                      exact_C3_symmetry_certified=True,exact_C3_points=str(symbolic))
        if family=='symmetry19':accepted=algebraic['valid']and(algebraic_cnf['satisfiable']is not False)
    report.update(accepted=bool(accepted),certificate=str(certificate),seconds=time.monotonic()-start)
    certificate.write_text(json.dumps(report,indent=2)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--real',required=True);parser.add_argument('--n',required=True,type=int)
    parser.add_argument('--family',required=True,choices=FAMILIES);parser.add_argument('--output',required=True)
    parser.add_argument('--cnf');parser.add_argument('--orientation-map');parser.add_argument('--cycles');parser.add_argument('--orient')
    args=parser.parse_args();result=audit_file(**vars(args));print(json.dumps(result,indent=2))
    return 0 if result['accepted'] else 1
if __name__=='__main__':raise SystemExit(main())
