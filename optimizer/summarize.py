#!/usr/bin/env python3
"""Condense completed, exactly audited experiments for the main report."""
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent/'results'
def compact(row):
    a=row['audit']
    return {'case':row.get('case',row.get('label')),'label':row['label'],
            'family':row.get('family','mixed23'),'valid':a['valid'],
            'width':a['bbox_width'],'height':a['bbox_height'],'area':a['bbox_area'],
            'layers':a['hull_layers'],'cpu_seconds':row.get('cpu_seconds',row.get('cpu_user_seconds',0)+row.get('cpu_system_seconds',0)),
            'orientation_changes':row.get('orientation_changes'),
            'output_sha256':row.get('output_sha256')}
def main():
    out={'interpretation':'Bounded single-seed compaction experiments; no global optimum or universal speedup claim.','phases':{}}
    for name,directory,pair in (
        ('initial_equal_budget','paired120s-20260906',('old','new')),
        ('cross_family','heldout30s-20260906',('old','new')),
        ('same_mode_ablation','ablation30s-20260906',('v1','v2'))):
        path=BASE/directory/'summary.json'
        if not path.exists():continue
        source=json.loads(path.read_text());rows=[compact(r) for r in source['results']]
        assert all(r['valid'] for r in rows)
        grouped={}
        for row in rows:grouped.setdefault(row['case'],{})[row['label']]=row
        wins=ties=losses=0
        for r in grouped.values():
            a,b=r[pair[0]]['area'],r[pair[1]]['area'];wins+=b<a;ties+=b==a;losses+=b>a
        out['phases'][name]={'source':str(path.relative_to(BASE.parent)),
            'runs':len(rows),'valid_runs':len(rows),'cpu_seconds':sum(r['cpu_seconds'] for r in rows),
            'candidate_area_wins':wins,'candidate_area_ties':ties,'candidate_area_regressions':losses,
            'comparison':list(pair),'same_preservation_mode':name=='same_mode_ablation',
            'rows':rows}
    rows=[]
    for path in (BASE/'refinement600s-20260906').glob('*/batch_result.json'):
        native=json.loads((path.parent/'batch.stdout').read_text().splitlines()[-1]);audit=json.loads((path.parent/'audit.stdout').read_text())
        assert audit['valid']
        rows.append({'label':path.parent.name,'valid':audit['valid'],'width':audit['bbox_width'],'height':audit['bbox_height'],'area':audit['bbox_area'],'layers':audit['hull_layers'],'cpu_seconds':native['cpu_seconds'],'orientation_changes':native['orientation_changes']})
    out['phases']['refinements']={'runs':len(rows),'valid_runs':len(rows),'cpu_seconds':sum(r['cpu_seconds'] for r in rows),'rows':rows}
    out['total_runs']=sum(p['runs'] for p in out['phases'].values());out['total_cpu_seconds']=sum(p['cpu_seconds'] for p in out['phases'].values())
    (BASE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='phases'}))
if __name__=='__main__':main()
