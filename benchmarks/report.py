#!/usr/bin/env python3
"""Aggregate SQLite strategy trials or export their compressed exact evidence."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import zlib

def avg(v):return statistics.mean(v)if v else None
def budget_signal_exit(row):
    return(row['returncode']in(-2,-9,-15)and row['budget_watchdog_fired']
           and not row['externally_interrupted']and bool(row.get('posthoc',{}).get('saved_checkpoints'))
           and row.get('status')in('BUDGET_EXHAUSTED','INTERRUPTED'))
def load(database):
    with sqlite3.connect(database)as db:return [json.loads(r[0])for r in db.execute('SELECT result_json FROM trials ORDER BY job_index')]
def calculate(rows,config):
    """Pure aggregation, shared by per-cohort and combined reports."""
    families={}
    for family in('mixed23','holes29','gons32','caps26'):
        group=[r for r in rows if r['job']['case']['problem']==family];arms={}
        for arm in('warm_retry','core_feedback'):
            rr=[r for r in group if r['job']['arm']==arm];audit=[s for r in rr for s in r['posthoc']['saved_checkpoints']]
            arms[arm]={'trials':len(rr),'valid_geometry_trials':sum(r['posthoc']['valid_geometry']for r in rr),
                'successes_in_shared_initial_stage':sum(any(s['stage_file']=='stage0.real'and s.get('geometry',{}).get('valid')for s in r['posthoc']['saved_checkpoints'])for r in rr),
                'valid_geometry_target_clusters':len({r['job']['case']['orientation_sha256']for r in rr if r['posthoc']['valid_geometry']}),
                'native_stages':sum(len(r.get('stages',[]))for r in rr),'feedback_calls':sum(len(r.get('feedback',[]))for r in rr),
                'feedback_sat_repairs':sum(f['status']=='SAT'for r in rr for f in r.get('feedback',[])),
                'mean_wall_seconds':avg([r['wall_seconds']for r in rr]),
                'mean_cpu_seconds':avg([r['parent_observed_cpu_seconds']for r in rr]),
                'mean_native_cpu_seconds':avg([sum(s['native_cpu_seconds']for s in r.get('stages',[]))for r in rr]),
                'mean_feedback_wall_seconds':avg([sum(f['total_feedback_wall_seconds']for f in r.get('feedback',[]))for r in rr]),
                'mean_initial_flippability_seconds':avg([r.get('timings',{}).get('initial_flippability',0)for r in rr]),
                'mean_best_forbidden_count':avg([r['posthoc']['minimum_forbidden_count']for r in rr if r['posthoc']['minimum_forbidden_count']is not None]),
                'median_best_forbidden_count':statistics.median([r['posthoc']['minimum_forbidden_count']for r in rr if r['posthoc']['minimum_forbidden_count']is not None])if any(r['posthoc']['minimum_forbidden_count']is not None for r in rr)else None,
                'budget_watchdog_trials':sum(r['budget_watchdog_fired']for r in rr),
                'external_interruptions':sum(r['externally_interrupted']for r in rr),
                'nonzero_exit_trials':sum(r['returncode']!=0 for r in rr),
                'budget_signal_exit_trials':sum(budget_signal_exit(r)for r in rr),
                'unexpected_nonzero_exit_trials':sum(r['returncode']!=0 and not budget_signal_exit(r)for r in rr),
                'operational_inspection_errors':sum('inspection_error'in s for r in rr for s in r.get('stages',[])),
                'native_nonzero_exit_stages':sum(s['returncode']!=0 for r in rr for s in r.get('stages',[])),
                'posthoc_audit_errors':sum('audit_error'in s for s in audit),'posthoc_audit_wall_seconds':sum(r['posthoc']['audit_wall_seconds']for r in rr),
                'status_counts':{s:sum(r['status']==s for r in rr)for s in sorted({r['status']for r in rr})}}
        indexed={(r['job']['case']['id'],r['job']['seed'],r['job']['arm']):r for r in group if not r['externally_interrupted']}
        pairs=[]
        for (case,seed,arm),a in indexed.items():
            b=indexed.get((case,seed,'core_feedback'))
            if arm=='warm_retry'and b is not None:
                assert a['job']['case']['orientation_sha256']==b['job']['case']['orientation_sha256']
                pairs.append((a,b))
        differences=[int(b['posthoc']['valid_geometry'])-int(a['posthoc']['valid_geometry'])for a,b in pairs]
        geometric_differences=[a['posthoc']['minimum_forbidden_count']-b['posthoc']['minimum_forbidden_count']for a,b in pairs
                              if a['posthoc']['minimum_forbidden_count']is not None and b['posthoc']['minimum_forbidden_count']is not None]
        families[family]={'unique_target_models':len({r['job']['case']['orientation_sha256']for r in group}),
            'arms':arms,'paired_trials':len(pairs),'feedback_only_successes':sum(d>0 for d in differences),
            'retry_only_successes':sum(d<0 for d in differences),'both_successes':sum(a['posthoc']['valid_geometry']and b['posthoc']['valid_geometry']for a,b in pairs),
            'geometry_residual_comparison':{'pairs':len(geometric_differences),'feedback_better':sum(d>0 for d in geometric_differences),
                  'ties':sum(d==0 for d in geometric_differences),'retry_better':sum(d<0 for d in geometric_differences)},
            'neither_success':sum(not a['posthoc']['valid_geometry']and not b['posthoc']['valid_geometry']for a,b in pairs)}
        # Seeds within one model are not independent model-level replications.
        expected=defaultdict(set);observed=defaultdict(dict)
        for job in config['jobs']:
            if job['case']['problem']==family:
                expected[job['case']['orientation_sha256']].add((job['seed'],job['arm']))
        for row in group:
            if not row['externally_interrupted']:
                job=row['job'];observed[job['case']['orientation_sha256']][job['seed'],job['arm']]=row['posthoc']['valid_geometry']
        model_outcomes={'complete_models':0,'retry_only':0,'feedback_only':0,'both':0,'neither':0}
        for digest,records in observed.items():
            if set(records)!=expected[digest]:continue
            retry=any(success for (_,arm),success in records.items()if arm=='warm_retry')
            feedback=any(success for (_,arm),success in records.items()if arm=='core_feedback')
            model_outcomes['complete_models']+=1
            model_outcomes['both'if retry and feedback else'retry_only'if retry else'feedback_only'if feedback else'neither']+=1
        families[family]['target_cluster_outcomes']=model_outcomes
    report={'registered_trials':len(config['jobs']),'completed_trials':len(rows),'complete':len(rows)==len(config['jobs']),
            'budget_seconds':config['budget_seconds'],'families':families,
            'success_records':[{'job_index':r['job_index'],'phase':r.get('phase'),'job':r['job'],'audit':r['posthoc']}for r in rows if r['posthoc']['valid_geometry']]}
    report['totals']={'search_worker_wall_seconds':sum(r['wall_seconds']for r in rows),
        'parent_observed_search_cpu_seconds':sum(r['parent_observed_cpu_seconds']for r in rows),
        'native_cpu_seconds':sum(s['native_cpu_seconds']for r in rows for s in r.get('stages',[])),
        'posthoc_audit_wall_seconds':sum(r['posthoc']['audit_wall_seconds']for r in rows),
        'feedback_wall_seconds':sum(f['total_feedback_wall_seconds']for r in rows for f in r.get('feedback',[])),
        'maximum_trial_wall_seconds':max([r['wall_seconds']for r in rows],default=None),
        'external_interruptions':sum(r['externally_interrupted']for r in rows),
        'budget_signal_exit_trials':sum(budget_signal_exit(r)for r in rows),
        'unexpected_nonzero_exit_trials':sum(r['returncode']!=0 and not budget_signal_exit(r)for r in rows),
        'cpu_accounting_flagged_trials':sum(r.get('cpu_may_exclude_unreaped_descendants',False)for r in rows),
        'operational_inspection_errors':sum('inspection_error'in s for r in rows for s in r.get('stages',[])),
        'native_nonzero_exit_stages':sum(s['returncode']!=0 for r in rows for s in r.get('stages',[])),
        'posthoc_audit_errors':sum('audit_error'in s for r in rows for s in r['posthoc']['saved_checkpoints'])}
    report['nonzero_exit_records']=[{'phase':r.get('phase'),'job_index':r['job_index'],'returncode':r['returncode'],
        'classification':'budget_signal_after_saved_checkpoints'if budget_signal_exit(r)else'unexpected_nonzero_exit',
        'status':r['status'],'wall_seconds':r['wall_seconds'],
        'saved_checkpoints':len(r['posthoc']['saved_checkpoints'])}for r in rows if r['returncode']!=0]
    return report
def summarize(args):
    database=Path(args.database);rows=load(database);out=database.parent
    config=json.loads((out/'registration.json').read_text());report=calculate(rows,config)
    report['registration']=str(out/'registration.json');families=report['families']
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# Equal-total-budget feedback versus warm retries','',
        f'{len(rows)}/{len(config["jobs"])} registered trials completed; {config["budget_seconds"]:g}s whole-trial wall limit per arm. Native code and starting target/seed are matched. Feedback costs, initial flippability, loading, and operational acceptance are charged to the limit. Independent post-hoc audits are separately timed and never guide search.','',
        '## Exact geometry outcomes','',
        '| Family | Target models | Paired trials | Retry only | Feedback only | Both | Neither |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for n,g in families.items():lines.append(f'| {n} | {g["unique_target_models"]} | {g["paired_trials"]} | {g["retry_only_successes"]} | {g["feedback_only_successes"]} | {g["both_successes"]} | {g["neither_success"]} |')
    lines+=['','## Exposure and overhead','',
        '| Family | Arm | Trials | Stages | Mean wall | Mean CPU | Mean native CPU | Mean feedback wall | Mean initial flips |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for n,g in families.items():
        for arm,a in g['arms'].items():
            if a['trials']:lines.append(f'| {n} | {arm} | {a["trials"]} | {a["native_stages"]} | {a["mean_wall_seconds"]:.2f} | {a["mean_cpu_seconds"]:.2f} | {a["mean_native_cpu_seconds"]:.2f} | {a["mean_feedback_wall_seconds"]:.2f} | {a["mean_initial_flippability_seconds"]:.2f} |')
    lines+=['','## Secondary exact geometry residual','',
        'This counts forbidden polygons in the best saved general-position checkpoint, independent of whichever SAT target the arm followed. Zero is a solution. Counts are compared only within a family; fewer polygons is a diagnostic, not a success certificate.','',
        '| Family | Median retry count | Median feedback count | Feedback better / tie / retry better |',
        '| --- | ---: | ---: | ---: |']
    for n,g in families.items():
        d=g['geometry_residual_comparison'];a=g['arms']['warm_retry']['median_best_forbidden_count'];b=g['arms']['core_feedback']['median_best_forbidden_count']
        lines.append(f'| {n} | {a} | {b} | {d["feedback_better"]} / {d["ties"]} / {d["retry_better"]} |')
    lines+=['','## Interpretation','',
        'Primary outcomes are actual geometric validity, including caps, at saved native checkpoints. A feedback arm is allowed to change its target, so its remaining active-target errors are not an apples-to-apples metric against a fixed-target retry arm. Geometry-invalid trials are budget-censored, not certified nonrealizable. Discovery times, when present, are checkpoint upper bounds.','',
        'Successes in the shared initial native stage occur before either warm retries or feedback can act, so they cannot establish an effect of the assigned strategy. Their counts are recorded separately in summary.json.','',
        'This small reused-target pilot is not sufficient for a universal success-rate claim. With few or zero solution events, report the paired counts rather than a misleading zero-width bootstrap confidence interval. Native time is expected to be lower in the feedback arm because repair and rechecking consume its fixed total budget.','',
        'Nonzero exits are classified in summary.json: a watchdog SIGINT/SIGTERM/SIGKILL after saved checkpoints is a budget-censored exit, not automatically a solver error. Unexpected exits, native-stage exits, operational inspection errors, and independent audit errors have separate counters. Parent-observed CPU is retained exactly as measured; signal-killed trials carry a conservative flag that unreaped descendant CPU might be absent.','',
        'See [summary.json](summary.json) for solver errors, budget watchdogs, external interruptions, feedback call counts, and audit costs. Every exact decimal checkpoint and native target/log is stored compressed in [results.sqlite](results.sqlite). JSON paths pointing into temporary trial folders are historical paths; the artifact table is the persistent source of truth.','',
        '```sh',f'python3 benchmarks/report.py summarize --database {database}',
        f'python3 benchmarks/report.py export --database {database} --trial 0 --output benchmarks/export-trial0','```']
    (out/'RESULTS.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'completed':len(rows),'registered':len(config['jobs']),'successes':len(report['success_records'])}))
def export(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect(args.database)as db:
        row=db.execute('SELECT result_json FROM trials WHERE job_index=?',(args.trial,)).fetchone()
        if row is None:raise ValueError('Unknown trial')
        (out/'result.json').write_text(row[0]+'\n')
        for name,digest,data in db.execute('SELECT name,sha256,data_zlib FROM artifacts WHERE job_index=?',(args.trial,)):
            if Path(name).name!=name:raise ValueError('Invalid artifact name')
            content=zlib.decompress(data);assert hashlib.sha256(content).hexdigest()==digest
            (out/name).write_bytes(content)
    print(out)
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('summarize');q.add_argument('--database',required=True);q.set_defaults(fn=summarize)
    q=s.add_parser('export');q.add_argument('--database',required=True);q.add_argument('--trial',required=True,type=int);q.add_argument('--output',required=True);q.set_defaults(fn=export)
    a=p.parse_args();a.fn(a)
if __name__=='__main__':main()
