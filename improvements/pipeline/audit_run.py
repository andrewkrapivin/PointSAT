#!/usr/bin/env python3
"""Independently audit each distinct accepted result in a completed pipeline run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from improvements.benchmarks.independent_audit import audit_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--family',required=True)
    args = parser.parse_args()
    directory = Path(args.input)
    settings = json.loads((directory/'settings.json').read_text())
    output = Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    records = [json.loads(line) for line in (directory/'raw_results.jsonl').read_text().splitlines()]
    cycles = None
    extra = settings.get('localizer_extra_args',[])
    if '-c' in extra:
        cycles = extra[extra.index('-c')+1]
    audits, seen = [], set()
    for record in records:
        if not record.get('realized'):
            continue
        point_file = Path(record.get('accepted_realization_file',record['realization_file']))
        digest = hashlib.sha256(point_file.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        try:
            result = audit_file(real=point_file,n=settings['n'],family=args.family,
                                output=output/f"sample{record['original_id']}-job{record['id']}",
                                cnf=settings.get('audit_base_file', settings['base_file']),orientation_map=settings.get('orientation_map_file'),
                                cycles=cycles)
            entry = {'id':record['id'],'original_id':record['original_id'],'sha256':digest,
                     'accepted':result['accepted'],'result':result}
        except Exception as exc:
            entry = {'id':record['id'],'original_id':record['original_id'],'sha256':digest,
                     'accepted':False,'error':f'{type(exc).__name__}: {exc}'}
        audits.append(entry)
        print(json.dumps(entry),flush=True)
    summary = {'pipeline_accepted_attempts':sum(bool(r.get('realized'))for r in records),
               'unique_candidates':len(audits),'independently_accepted':sum(a['accepted']for a in audits),
               'rejected':sum(not a['accepted']for a in audits),'audits':audits}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return int(bool(summary['rejected']))


if __name__=='__main__':
    raise SystemExit(main())
