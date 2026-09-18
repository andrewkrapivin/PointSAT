#!/usr/bin/env python3
"""Independent geometry audit of the fixed-work calibration outputs."""
import json
from pathlib import Path
from matched import ROOT,HERE,audit
directory=HERE/'results/kernel_v1'
cases=json.loads((HERE/'controls_manifest.json').read_text())['cases']
rows=[json.loads(line) for line in (directory/'results.jsonl').read_text().splitlines()]
results=[]
for case in cases:
    row=next(r for r in rows if r['case']==case['id'] and r['mode']=='fast' and r['repeat']==0)
    real=directory/f'{case["id"]}-r0-fast.real'
    result={'case':case['id'],'known_coordinate_derived_orientation_control':True,
            'native_stats':row['stats'],'audit':audit(real,ROOT/case['orientation'],case)}
    results.append(result)
(directory/'independent_audit.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps([{'case':r['case'],'orientation_violations':r['audit']['orientation_violations'],
                  'geometry_valid':r['audit']['geometry']['valid'],
                  'ordered_geometry_valid':r['audit'].get('ordered_geometry',{}).get('valid'),
                  'actual_iterations':r['native_stats'][0]['iterations']}for r in results],indent=2))
summary=json.loads((directory/'summary.json').read_text())
summary['max_iterations']=summary.pop('iterations')
for problem,group in summary['groups'].items():
    rr=next(r for r in rows if r['problem']==problem and r['mode']=='fast')
    group['actual_iterations']=rr['stats'][0]['iterations']
    group['solved_before_iteration_cap']=rr['stats'][0]['best_violations']==0
    group['timing_caveat']='Short solved controls include startup overhead; fixed trajectory, not necessarily full100k iterations.'
(directory/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
