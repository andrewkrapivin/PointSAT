"""Independently verified non-realizability cuts and signed-map projection."""
import hashlib
import json
from pathlib import Path

from improvements.benchmarks import verify_bfp
from sat_orient_conversion import orient, parse_constraints


def load_verified_proof(filename, n):
    proof = json.loads(Path(filename).read_text())
    if proof.get('status') != 'PROVED_NONREALIZABLE' or proof['n'] != n:
        raise ValueError('Not a non-realizability proof for this point count')
    values = verify_bfp.read(proof['input'], n, partial=proof.get('partial') is True)
    report = verify_bfp.check(proof, values, n)
    return {'path':str(filename),'sha256':hashlib.sha256(Path(filename).read_bytes()).hexdigest(),
            'blocking_clause':proof['blocking_clause'],'verified':report,'values':values}


def mapped_clause(proof, adapter):
    mapping = {rank:literal for _,literal,rank in adapter.entries}
    clause = sorted({(1 if literal>0 else -1)*mapping[abs(literal)] for literal in proof['blocking_clause']},key=abs)
    if any(-literal in clause for literal in clause):
        raise ValueError('Mapped blocking clause is tautological; incompatible source assignment')
    model = [0]*len(adapter.entries)
    for triple,sign in proof['values'].items():
        rank = orient(*triple)
        model[rank-1] = rank*sign
    if not all(model):
        # Partial proofs need only a support-consistent mapped truth assignment.
        assignments = {}
        for literal in proof['blocking_clause']:
            primary = -(1 if literal>0 else -1)*mapping[abs(literal)]
            if abs(primary) in assignments and assignments[abs(primary)] != primary:
                raise ValueError('Proof premises conflict under the signed map')
            assignments[abs(primary)] = primary
        truth = set(assignments.values())
    else:
        projected, conflicts = adapter.project(model)
        if conflicts:
            raise ValueError('Certified source model conflicts with orientation map')
        truth = set(projected)
    if not all(-literal in truth for literal in clause):
        raise ValueError('Mapped clause does not exclude its certified premise assignment')
    return clause


def supported_by_target(proof, orientation_file):
    retained = {sign*orient(*indices) for sign,indices in parse_constraints(orientation_file)}
    return all(-literal in retained for literal in proof['blocking_clause'])
