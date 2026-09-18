#!/usr/bin/env python3
"""Regenerate paired summaries, clustering duplicate SAT outputs by hash."""
import argparse
import contextlib
import io
import json
from matched import HERE,compare

def refresh(name,baseline,improved):
    paths=lambda labels:[str(HERE/'results'/label/'results.jsonl')for label in labels]
    args=argparse.Namespace(baseline=paths(baseline),improved=paths(improved),output=str(HERE/(name+'.json')))
    with contextlib.redirect_stdout(io.StringIO()):compare(args)
    data=json.loads((HERE/(name+'.json')).read_text())
    print(name,json.dumps({'pairs':data['pairs'],'groups':{k:{'unique_models':v['independent_model_clusters'],
          'baseline_mean':v['baseline']['mean_violations'],'improved_mean':v['improved']['mean_violations'],
          'geometry_successes':[v['baseline']['geometric_successes'],v['improved']['geometric_successes']]}
          for k,v in data['groups'].items()}}))

refresh('legacy23_comparison',['legacy23_baseline'],['legacy23_v1'])
refresh('fresh_v1_comparison',['fresh_baseline','late29_baseline'],['fresh_v1','late29_v1'])
refresh('fresh_v3_comparison',['fresh_baseline','late29_baseline'],['fresh_v3_line10'])
refresh('round2_line10_comparison',['round2_v5_default_first6'],['round2_v5_line10_first6'])
refresh('round2_pair_line10_comparison',['round2_v5_default_first6'],['round2_v5_pair_line10_first6'])
