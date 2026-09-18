#!/usr/bin/env python3
"""Summarize finished logs and exact hexagon invariants; never runs a solver."""
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT/'improvements/pipeline/unattended_20260905'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hexagon_invariant(points):
    # This existing verifier's validity flag implements the different19-point
    # property. For23points use ONLY its exact exhaustive interior histogram.
    process = subprocess.run([str(ROOT/'improvements/symmetry19/verify_hexagons'), str(points)],
                             text=True, capture_output=True, timeout=60)
    if process.returncode not in (0, 1):
        raise RuntimeError(process.stderr)
    report = json.loads(process.stdout)
    assert report['n'] == 23 and report['six_subsets_checked'] == 100947
    assert report['collinear_triples'] == report['duplicate_pairs'] == 0
    histogram = report['interior_histogram']
    assert histogram[0] == 0
    return {'convex6_count': sum(histogram), 'interior_histogram': histogram,
            'six_subsets_checked': report['six_subsets_checked'],
            'points': str(points.relative_to(ROOT)), 'points_sha256': digest(points)}


def main():
    supervisor = json.loads((QUEUE/'supervisor/summary.json').read_text())
    started = json.loads((QUEUE/'supervisor/supervisor.json').read_text())
    groups, families, sat_modes = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    accepted, jobs = [], []
    for event in sorted(supervisor['results'], key=lambda x: x['label']):
        folder = Path(event['output'])
        config = json.loads((folder/'settings.json').read_text())
        family, arm = config['problem_family'], config['feedback_core_choice']
        records = [json.loads(line) for line in (folder/'raw_results.jsonl').read_text().splitlines()]
        stats = Counter(jobs=1, planned_sat_samples=config['n_solutions'],
                        job_wall_seconds=event['wall_seconds'], watchdogs=bool(event.get('watchdog_stopped')))
        stages = Counter()
        for record in records:
            kind, status = record['type'], record['status']
            stats[f'{kind.lower()}_records'] += 1
            stats[f'{kind.lower()}_status_{status}'] += 1
            for name, seconds in record.get('stage_seconds', {}).items():
                stages[name] += seconds
            if kind == 'Realize':
                stats['native_wrapper_timeouts'] += bool(record.get('localizer_timed_out'))
        stats['sat_unstarted_or_unlogged'] = stats['planned_sat_samples']-stats['sat_records']
        audits = json.loads((folder/'audit/summary.json').read_text())
        successes = []
        for entry in audits['audits']:
            if not entry['accepted']:
                stats['audit_rejections'] += 1
                continue
            certificate = Path(entry['result']['certificate'])
            report = json.loads(certificate.read_text())
            item = {'queue_job': event['label'], 'family': family, 'arm': arm,
                    'sample_id': entry['original_id'], 'pipeline_job_id': entry['id'],
                    'certificate': str(certificate.relative_to(ROOT)),
                    'certificate_sha256': digest(certificate),
                    'exact_output': report.get('exact_C3_points', report['integer_points'])}
            if family == 'mixed23':
                item.update(hexagon_invariant(Path(report['integer_points'])))
            accepted.append(item)
            successes.append(entry['original_id'])
        stats['accepted_certificates'] = len(successes)
        stats['accepted_samples'] = len(set(successes))
        stats['jobs_with_success'] = bool(successes)
        for name, seconds in stages.items():
            stats['stage_'+name+'_worker_seconds'] = seconds
        groups[family+'/'+arm].update(stats)
        families[family].update(stats)
        sat_modes[family+'/'+' '.join(config['sat_extra_args'])].update(stats)
        jobs.append({'label':event['label'], 'family':family, 'arm':arm, 'statistics':dict(stats)})
    previous = []
    for name in ('sat-guided23-case33','feedback23-sample3','archive23-sample2',
                 'archive23-sample7','control-margin23-sample6'):
        folder = ROOT/'improvements/benchmarks/successes'/name
        item = {'label':name, **hexagon_invariant(folder/'normalized.pts')}
        previous.append(item)
    overnight23 = [item for item in accepted if item['family']=='mixed23']
    old_invariants = {tuple(item['interior_histogram']) for item in previous}
    new_invariants = {tuple(item['interior_histogram']) for item in overnight23}
    output = {'started_utc':started['started_utc'], 'finished_utc':supervisor['finished_utc'],
              'queue_elapsed_seconds':(datetime.fromisoformat(supervisor['finished_utc'])-datetime.fromisoformat(started['started_utc'])).total_seconds(),
              'jobs_handled':supervisor['jobs_handled'], 'workers':started['workers'],
              'families':dict(families), 'arms':dict(groups), 'sat_modes':dict(sat_modes), 'accepted':accepted,
              'previous23':previous, 'jobs':jobs,
              'distinctness':{'overnight23_certificates':len(overnight23),
                'overnight_distinct_count_lower_bound':len({x['convex6_count'] for x in overnight23}),
                'overnight_distinct_histogram_lower_bound':len(new_invariants),
                'combined_distinct_histogram_lower_bound':len(old_invariants|new_invariants),
                'overnight_classes_distinct_from_all_five_previous':len(new_invariants-old_invariants),
                'method':'Exact convex6 interior-count histograms are invariant under relabeling and reflection. Different histograms prove nonisomorphism; equal histograms do not prove isomorphism. No literature novelty claim.'},
              'invariant_verifier':{'path':'improvements/symmetry19/verify_hexagons',
                                    'sha256':digest(ROOT/'improvements/symmetry19/verify_hexagons')}}
    output['totals'] = dict(sum(families.values(), Counter()))
    output['watchdogs'] = [event for event in supervisor['results'] if event.get('watchdog_stopped')]
    (QUEUE/'aggregate.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({key:output[key] for key in ('jobs_handled','queue_elapsed_seconds','families','arms','distinctness')},indent=2))
    print('Witness invariants:', [(x['queue_job'],x.get('convex6_count')) for x in accepted])


if __name__ == '__main__':
    main()
