#!/usr/bin/env python3
"""Audit completed pipeline runs without trusting their success classification."""
import argparse
import json
from pathlib import Path
import shutil
from matched import ROOT,audit,digest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--n',type=int,default=23);parser.add_argument('--gon',type=int,default=7)
    parser.add_argument('--hole',type=int,default=6);parser.add_argument('--cap',type=int,default=0)
    a=parser.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    records=[json.loads(s) for s in Path(a.input).read_text().splitlines()];results=[]
    for record in records:
        if record.get('type')!='Realize':continue
        source=ROOT/record['realization_file'];orient=ROOT/record['orientations_file']
        if not source.exists():continue
        directory=out/str(record['id']);directory.mkdir()
        real=directory/'points.real';o=directory/'constraints.or'
        shutil.copyfile(source,real);shutil.copyfile(orient,o)
        r={'original_record_id':record['id'],'source':str(source.relative_to(ROOT)),
           'source_sha256':digest(source),'pipeline_reported_realized':record.get('realized'),
           'pipeline_reported_violations':record.get('violations')}
        try:r.update(audit(real,o,{'n':a.n,'gon':a.gon,'hole':a.hole,'cap':a.cap}))
        except Exception as e:r['audit_error']=str(e)
        (directory/'audit.json').write_text(json.dumps(r,indent=2)+'\n');results.append(r)
    summary={'audited':len(results),'geometric_valid':sum(r.get('geometry',{}).get('valid',False) for r in results),
             'orientation_exact':sum(r.get('orientation_violations')==0 for r in results),
             'audit_errors':sum('audit_error' in r for r in results),'results':results}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'}))
if __name__=='__main__':main()
