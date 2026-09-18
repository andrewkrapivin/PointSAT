"""Compact read-only status collection for the bounded overnight experiments."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def read(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,json.JSONDecodeError):return default

def main():
    folders={'benchmarks':ROOT/'benchmarks/overnight','pipeline':ROOT/'pipeline/unattended_20260905',
             'geometry':ROOT/'localizer/unattended14','proofsearch':ROOT/'lazy19/overnight'}
    report={'utc':datetime.now(timezone.utc).isoformat(),'deadline_utc':'2026-09-05T14:00:00+00:00','queues':{}}
    for name,path in folders.items():
        supervisor=path/'supervisor';metadata=read(supervisor/'supervisor.json',{})
        events=[]
        try:
            for line in (supervisor/'events.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except json.JSONDecodeError:continue
        except OSError:pass
        report['queues'][name]={'pid':metadata.get('pid'),'finished':(supervisor/'summary.json').exists(),
                               'handled_records':len(events),
                               'ended_jobs':sum('returncode' in r for r in events),
                               'completed_jobs':sum(r.get('returncode')==0 and not r.get('watchdog_stopped',False) for r in events),
                               'skipped_jobs':sum('skipped' in r for r in events),
                               'job_errors':sum('error' in r for r in events),
                               'watchdog_stops':sum(r.get('watchdog_stopped',False) for r in events),
                               'remaining_child_reports':sum(bool(r.get('remaining_tagged_pids')) for r in events)}
    certificates=[]
    for name in ('benchmarks','pipeline','proofsearch'):
        for path in folders[name].rglob('certificate.json'):
            data=read(path,{})
            if data.get('accepted'):
                certificates.append({'certificate':str(path),'n':data.get('n'),'family':data.get('family')})
    report['certified_output_files']=certificates
    geometry=[]
    for path in folders['geometry'].glob('*/audit.json'):
        if not path.parent.name[:3].isdigit():continue
        data=read(path,{})
        if 'best_score' in data:geometry.append({'audit':str(path),'valid':data.get('any_valid'),
                                               'best_score':data['best_score'],'certificate':data.get('best_certificate')})
    report['completed_geometry_audits']=len(geometry)
    report['best_geometry']=min(geometry,key=lambda r:r['best_score']) if geometry else None
    report['valid_geometry_jobs']=[row for row in geometry if row['valid']]
    checkpoint=read(folders['proofsearch']/'consumer/checkpoint.json',{})
    report['consumer']={'processed_models':len(checkpoint.get('processed_hashes',[])),
                        'fallbacks':checkpoint.get('fallbacks'),'best':checkpoint.get('best_verification'),
                        'best_file':checkpoint.get('best_geometry'),'successes':checkpoint.get('successes',[])}
    corpus=folders['proofsearch']/'corpus'
    report['producer']={'independently_verified_new_proofs':len(list((corpus/'bfp').glob('*.checked.json'))),
                        'surviving_models':len(list(corpus.glob('model*.json')))}
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
