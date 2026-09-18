"""Aggregate exact-audited19 repair outcomes without counting SAT as geometry."""
import argparse
import json
from pathlib import Path
from statistics import mean

def summarize(folder):
    rows=[]
    for path in sorted(Path(folder).rglob('result.json')):
        record=json.loads(path.read_text());geometry=record.get('verification',{})
        histogram=geometry.get('interior_histogram')
        rows.append({'file':str(path),'valid':geometry.get('valid',False),
                     'bad_hexagons':histogram[0]+histogram[3] if histogram else None,
                     'orientation_violations':record.get('orientation_violations'),
                     'wall_seconds':record.get('wall_seconds'),
                     'collinear_triples':geometry.get('collinear_triples')})
    bad=[r['bad_hexagons'] for r in rows if r['bad_hexagons'] is not None]
    orientations=[r['orientation_violations'] for r in rows if r['orientation_violations'] is not None]
    return {'input':folder,'runs':len(rows),'valid':sum(r['valid'] for r in rows),
            'best_geometric_violations':min(bad,default=None),
            'best_orientation_violations':min(orientations,default=None),
            'mean_orientation_violations':mean(orientations) if orientations else None,
            'total_worker_wall_seconds':sum(r['wall_seconds'] or 0 for r in rows),'results':rows}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--output');args=parser.parse_args()
    result=summarize(args.folder)
    if args.output:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'}))
