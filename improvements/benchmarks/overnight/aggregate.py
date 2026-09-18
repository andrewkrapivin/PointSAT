#!/usr/bin/env python3
"""Read-only experiment aggregation; writes only this folder's reports."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LABELS=['v5_default','v5_line10','v5_pair_line10','v6_default','v6_ordered_x']
FAMILIES=['mixed23','holes29','gons32','caps26']

def mean(values):return statistics.mean(values)if values else None
def cpu(r):return r.get('cpu_user_seconds',0)+r.get('cpu_system_seconds',0)
def paired(records,baseline,treatment):
    by={(r['case'],r['seed'],r['label']):r for r in records if r.get('eligible_for_matched_comparison',True)}
    assert len(by)==sum(r.get('eligible_for_matched_comparison',True)for r in records)
    pairs=[]
    for (case,seed,label),a in by.items():
        b=by.get((case,seed,treatment))
        if label!=baseline or b is None:continue
        assert a['orientation_sha256']==b['orientation_sha256']and a['wall_limit_seconds']==b['wall_limit_seconds']==45
        if 'orientation_violations'in a and'orientation_violations'in b:pairs.append((a,b))
    differences=[a['orientation_violations']-b['orientation_violations']for a,b in pairs]
    clusters=defaultdict(list)
    for a,b in pairs:clusters[a['orientation_sha256']].append(a['orientation_violations']-b['orientation_violations'])
    model_means=[mean(v)for v in clusters.values()]
    interval=None
    if len(model_means)>1:
        rng=random.Random(20260905)
        boot=sorted(mean(rng.choices(model_means,k=len(model_means)))for _ in range(10000))
        interval=[boot[250],boot[9749]]
    return {'baseline':baseline,'treatment':treatment,'auditable_pairs':len(pairs),'unique_model_clusters':len(clusters),
            'wins':sum(v>0 for v in differences),'ties':sum(v==0 for v in differences),'losses':sum(v<0 for v in differences),
            'mean_violation_reduction':mean(differences),'mean_unique_model_reduction':mean(model_means),
            'model_cluster_bootstrap_95pct':interval,
            'baseline_cpu_seconds':sum(cpu(a)for a,b in pairs),'treatment_cpu_seconds':sum(cpu(b)for a,b in pairs)}

def main():
    registration=json.loads((HERE/'registration.json').read_text());families={};all_records=[];pending=[];problems=[]
    for family in FAMILIES:
        jobs=[c for c in registration['cases']if c['problem']==family];cases=[];records=[];batches=[]
        for job in jobs:
            folder=ROOT/job['output'];result=folder/'case_result.json';batch=folder/'batch_result.json'
            if result.exists():
                value=json.loads(result.read_text());cases.append(value)
                assert value['case']==job
                for r in value.get('native_runs',[]):
                    assert r['wall_limit_seconds']==registration['native_seconds']==45
                    expected=next(t['binary']for t in registration['treatments']+registration['caps_treatments']if t['label']==r['label'])
                    assert r['binary_sha256']==registration['binary_sha256'][expected]
                records.extend(value.get('native_runs',[]))
            if batch.exists():batches.append(json.loads(batch.read_text()))
            else:pending.append(job['id'])
        sat=[c for c in cases if c.get('sat',{}).get('returncode')==10]
        hashes=Counter(c['orientation_sha256']for c in sat)
        group={'registered_draws':len(jobs),'saved_case_results':len(cases),'supervisor_finished_cases':len(batches),
               'sat_successes':len(sat),'sat_timeouts':sum(c.get('sat',{}).get('timed_out',False)for c in cases),
               'sat_other_failures':sum('sat'in c and c['sat']['returncode']!=10 and not c['sat'].get('timed_out')for c in cases),
               'sat_interrupted':sum(c.get('sat',{}).get('interrupted',False)for c in cases),
               'sat_budget_seconds':jobs[0]['sat_seconds'],'unique_orientation_models':len(hashes),
               'duplicate_orientation_clusters':{h:n for h,n in hashes.items()if n>1},
               'independent_original_cnf_passes':sum(c.get('independent_original_cnf',{}).get('satisfiable',False)for c in cases),
               'sat_sum_wall_seconds':sum(c.get('sat',{}).get('wall_seconds',0)for c in cases),
               'sat_sum_cpu_seconds':sum(c.get('sat',{}).get('cpu_seconds',0)for c in cases),
               'shuffle_sum_cpu_seconds':sum(c.get('shuffle',{}).get('cpu_seconds',0)for c in cases),
               'native_saved_runs':len(records),'native_expected_if_all_sat_cases_finish':len(sat)*3*(5 if family=='caps26'else 3),
               'native_sum_wall_seconds':sum(r['wall_seconds']for r in records),'native_sum_cpu_seconds':sum(cpu(r)for r in records),
               'completed_all_native_cases':sum(c.get('completed_all_native_runs',False)for c in cases),'treatments':{},'paired_comparisons':[]}
        for label in LABELS:
            rr=[r for r in records if r['label']==label]
            if not rr:continue
            eligible=[r for r in rr if r.get('eligible_for_matched_comparison',True)]
            good=[r for r in eligible if 'orientation_violations'in r]
            geometry=[r for r in eligible if r.get('geometry',{}).get('valid')]
            group['treatments'][label]={'saved_runs':len(rr),'eligible_runs':len(eligible),'audited_runs':len(good),
                'interrupted_runs':sum(r.get('interrupted',False)for r in rr),'missing_or_failed_audits':sum('audit_error'in r for r in rr),
                'orientation_successes':sum(r['orientation_violations']==0 for r in good),'geometric_successes':len(geometry),
                'geometric_success_draws':len({r['case']for r in geometry}),
                'geometric_success_rate_all_registered_draws':len({r['case']for r in geometry})/len(jobs),
                'ordered_projection_successes':sum(r.get('ordered_geometry',{}).get('valid',False)for r in eligible),
                'mean_orientation_violations':mean([r['orientation_violations']for r in good]),
                'median_orientation_violations':statistics.median([r['orientation_violations']for r in good])if good else None,
                'mean_cpu_seconds':mean([cpu(r)for r in eligible]),'sum_cpu_seconds':sum(cpu(r)for r in rr),
                'sum_wall_seconds':sum(r['wall_seconds']for r in rr),
                'early_native_finishes':sum(not r.get('timed_out')and not r.get('interrupted')for r in rr)}
        for a,b in [('v5_default','v5_line10'),('v5_default','v5_pair_line10')]+([('v6_default','v6_ordered_x')]if family=='caps26'else[]):
            group['paired_comparisons'].append(paired(records,a,b))
        families[family]=group;all_records.extend(records)
    summary={'snapshot_utc':datetime.now(timezone.utc).isoformat(),'complete':not pending,'pending_supervisor_jobs':pending,
             'registration_sha256':hashlib.sha256((HERE/'registration.json').read_bytes()).hexdigest(),
             'native_budget_seconds':45,'native_seeds':registration['native_seeds'],'families':families,
             'totals':{'registered_draws':80,'sat_successes':sum(g['sat_successes']for g in families.values()),
                       'sat_timeouts':sum(g['sat_timeouts']for g in families.values()),'native_runs':len(all_records),
                       'geometric_successes':sum(r.get('geometry',{}).get('valid',False)for r in all_records),
                       'orientation_successes':sum(r.get('orientation_violations')==0 for r in all_records),
                       'native_cpu_seconds':sum(cpu(r)for r in all_records),
                       'sat_cpu_seconds':sum(g['sat_sum_cpu_seconds']for g in families.values())},
             'uncertainty':'Exploratory percentile bootstrap resamples unique orientation SHA256 clusters, averaging native seeds and duplicate SAT draws within model. No multiplicity adjustment. Failures or no certificate do not prove nonrealizability.'}
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Prospective overnight native-move comparison','',f'Snapshot: {summary["snapshot_utc"]}. '+('All 80 jobs completed.'if summary['complete']else f'{80-len(pending)}/80 supervisor jobs completed; pending: {", ".join(pending)}.'),'',
      'This measures optional native search moves on newly generated SAT targets. It is **not** the earlier fixed-work 1.88–2.12× evaluator-speed test, and it is not an upstream-versus-improved pipeline benchmark.','',
      '## Registered protocol','',
      'Before target generation, registration froze 20 SAT draws per family, binaries, and treatments. Clause-only shuffling preserves every variable and sign; default Kissat generates the models. Native runs use one thread, `-i 10 -r 30000`, seeds 1/17/101, no warm coordinates, and the same **45-second wall budget**. Treatment order is prospectively randomized within each SAT draw. These are equal-time, **not equal-iteration/evaluation**, comparisons; actual CPU time is recorded because the shared machine was loaded. Failed SAT draws are retained, not replaced.','',
      'The three main treatments share the same frozen v5 binary: default, `--line-every 10`, and `--pair-every 10 --line-every 10`. The cap-specific comparison separately uses the same frozen v6 binary with `--ordered-x` off/on. Native orientation success is not accepted as geometric success without exact polygon/cap checks.','',
      '## SAT generation and denominators','',
      '| Family | Registered | SAT | SAT timeout | Unique orientation models | SAT CPU seconds | Native saved / expected |',
      '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name,g in families.items():lines.append(f'| {name} | {g["registered_draws"]} | {g["sat_successes"]} | {g["sat_timeouts"]} | {g["unique_orientation_models"]} | {g["sat_sum_cpu_seconds"]:.1f} | {g["native_saved_runs"]} / {g["native_expected_if_all_sat_cases_finish"]} |')
    lines+=['','Families: mixed23=no convex7/no empty6; holes29=no empty6; gons32=no convex7; caps26=no convex7/no5cap. SAT caps were respectively300/1800/180/180 seconds. Every generated target independently passed the original CNF check. Duplicate orientation hashes are clustered rather than treated as independent models.','',
      '## Native quality and timing','',
      '| Family | Treatment | Audited runs | Mean orientation errors | Exact orientation successes | Valid geometries | Mean CPU seconds |',
      '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for name,g in families.items():
        for label,t in g['treatments'].items():lines.append(f'| {name} | {label} | {t["audited_runs"]} | {t["mean_orientation_violations"]:.2f} | {t["orientation_successes"]} | {t["geometric_successes"]} | {t["mean_cpu_seconds"]:.2f} |')
    lines+=['','## Matched effects','',
      'Positive reductions mean fewer errors with the optional treatment. Wins/ties/losses compare identical model hashes and native seeds. Intervals are exploratory 95% bootstrap intervals clustered by unique orientation model, not independent repetitions of each seed.','',
      '| Family | Comparison | Pairs | Models | Wins / ties / losses | Mean error reduction | Cluster interval |',
      '| --- | --- | ---: | ---: | ---: | ---: | --- |']
    for name,g in families.items():
        for p in g['paired_comparisons']:
            ci=p['model_cluster_bootstrap_95pct'];interval=f'[{ci[0]:.2f}, {ci[1]:.2f}]'if ci else'not estimated'
            lines.append(f'| {name} | {p["baseline"]} → {p["treatment"]} | {p["auditable_pairs"]} | {p["unique_model_clusters"]} | {p["wins"]} / {p["ties"]} / {p["losses"]} | {p["mean_violation_reduction"]:.2f} | {interval} |')
    lines+=['','## Interpretation and reproduction','',
      f'Total recorded native CPU: {summary["totals"]["native_cpu_seconds"]:.1f}s; SAT CPU: {summary["totals"]["sat_cpu_seconds"]:.1f}s. Exact geometry successes: {summary["totals"]["geometric_successes"]}. SAT timeouts and unsuccessful realization searches are empirical failures under these budgets, not impossibility proofs. Lower orientation error is only a search proxy; the coordinate geometry remains the acceptance criterion.','',
      'In this prospective sample, both optional v5 treatments have worse mean orientation error than default in every family; the paired move is consistently worse. These data do not support enabling either universally. Ordered-x also has a substantial search cost here, although enforcing x order addresses a genuine cap-semantics constraint; the independent cap acceptance check remains necessary whichever proposal method is used. These conclusions concern cold 45-second searches, not warm SAT-feedback portfolios or all possible budgets.','',
      'The successful19-point discovery came from the separate SAT-feedback portfolio, not this cold four-family benchmark. These results also do not erase the separately measured evaluator speedup.','',
      'Reproduce this aggregation without rerunning any search:','',
      '```sh','python3 improvements/benchmarks/overnight/aggregate.py','```','',
      'Machine-readable [summary.json](summary.json) includes full denominators, duplicate clusters, interruptions, CPU totals, and paired effects. [registration.json](registration.json) records immutable binary/CNF hashes and prespecified treatments; per-draw raw records are under [runs/](runs/).']
    (HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'complete':summary['complete'],'pending':pending,'totals':summary['totals']}))

if __name__=='__main__':main()
