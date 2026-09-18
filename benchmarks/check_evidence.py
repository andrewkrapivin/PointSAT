#!/usr/bin/env python3
"""Read-only consistency audit of registered trials and compressed evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import zlib


def check(database, require_complete=False):
    database=Path(database)
    config=json.loads(database.with_name('registration.json').read_text())
    with sqlite3.connect(database)as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        rows=[(i,json.loads(raw))for i,raw in db.execute('SELECT job_index,result_json FROM trials')]
        artifacts={}
        for index,name,digest,compressed in db.execute('SELECT job_index,name,sha256,data_zlib FROM artifacts'):
            assert Path(name).name==name
            assert hashlib.sha256(zlib.decompress(compressed)).hexdigest()==digest
            artifacts[index,name]=digest
    if require_complete:
        assert len(rows)==len(config['jobs'])
    paired={}
    errors=[]
    for index,row in rows:
        assert row['job_index']==index and row['job']==config['jobs'][index]
        assert row['budget_seconds']==config['budget_seconds']
        assert row['wall_seconds']<=row['budget_seconds']+1.1
        assert not row['externally_interrupted']
        case=row['job']['case'];n=case['n']
        valid=[]
        for saved in row['posthoc']['saved_checkpoints']:
            assert (index,saved['stage_file'])in artifacts
            if 'audit_error'in saved:
                errors.append((index,saved['audit_error']));continue
            g=saved['geometry']
            assert g['n']==n
            assert g['gon_subsets_checked']==(math.comb(n,case['gon'])if case['gon']else 0)
            assert g['hole_subsets_checked']==(math.comb(n,case['hole'])if case['hole']else 0)
            if g['valid']:
                assert not g['collinear_triples']
                assert not g.get('duplicate_pairs',0)
                assert not g['convex_gons']and not g['empty_holes']and not g.get('convex_caps',0)
                valid.append(saved)
        assert row['posthoc']['valid_geometry']==bool(valid)
        for stage in row['stages']:
            assert stage['target_sha256']==artifacts[index,f'stage{stage["stage"]}.or']
            assert stage['seed']==row['job']['seed']+stage['stage']
        paired[case['id'],row['job']['seed'],row['job']['arm']]=row
    complete_pairs=0
    for (case,seed,arm),a in paired.items():
        b=paired.get((case,seed,'core_feedback'))
        if arm=='warm_retry'and b:
            assert a['initial_flippable_count']==b['initial_flippable_count']
            assert a['stages'][0]['target_sha256']==b['stages'][0]['target_sha256']
            complete_pairs+=1
    assert not errors,errors
    return {'database':str(database),'complete':len(rows)==len(config['jobs']),
            'trials_checked':len(rows),'complete_pairs_checked':complete_pairs,
            'artifacts_hash_checked':len(artifacts),'audit_errors':errors,
            'all_checks_passed':True}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--database',required=True)
    p.add_argument('--require-complete',action='store_true')
    p.add_argument('--output')
    args=p.parse_args();result=check(args.database,args.require_complete)
    if args.output:
        Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
