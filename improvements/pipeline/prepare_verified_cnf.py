#!/usr/bin/env python3
"""Append only independently verified geometric impossibility cuts to a NEW CNF."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from improvements.pipeline.orientation_map import OrientationMap
from improvements.pipeline.verified_cuts import load_verified_proof, mapped_clause


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True)
    parser.add_argument('--map',required=True)
    parser.add_argument('--n',type=int,required=True)
    parser.add_argument('--proof',action='append',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        raise SystemExit('Refusing to overwrite an existing augmented CNF')
    adapter = OrientationMap(args.map,args.n)
    clauses, records = [], []
    for filename in args.proof:
        proof = load_verified_proof(filename,args.n)
        clause = mapped_clause(proof,adapter)
        if clause not in clauses:
            clauses.append(clause)
        records.append({key:value for key,value in proof.items()if key!='values'}|{'mapped_clause':clause})
    target.parent.mkdir(parents=True,exist_ok=True)
    with Path(args.base).open() as source, target.open('x') as output:
        for line in source:
            if line.startswith('p cnf '):
                parts = line.split()
                if any(abs(lit)>int(parts[2])for clause in clauses for lit in clause):
                    raise ValueError('Mapped cut refers outside the original CNF header')
                parts[3] = str(int(parts[3])+len(clauses))
                output.write(' '.join(parts)+'\n')
                break
            output.write(line)
        else:
            raise ValueError('Missing original CNF header')
        shutil.copyfileobj(source,output)
        output.write('\n')
        for clause in clauses:
            output.write(' '.join(map(str,clause))+' 0\n')
    metadata = {'source_cnf':args.base,'source_sha256':hashlib.sha256(Path(args.base).read_bytes()).hexdigest(),
                'augmented_cnf':str(target),'augmented_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                'orientation_map':args.map,'new_sound_clauses':len(clauses),'proofs':records}
    target.with_suffix('.proofs.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'augmented_cnf':str(target),'sound_clauses':len(clauses),'mapped_lengths':[len(c)for c in clauses]}))


if __name__=='__main__':
    main()
