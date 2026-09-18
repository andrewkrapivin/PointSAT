#!/usr/bin/env python3
"""Read-only log aggregation; no SAT, geometry search, or proof solver runs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'improvements/lazy19/overnight'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    final_path = OUT/'supervisor/summary.json'
    if args.final and (now < datetime(2026,9,5,14,tzinfo=timezone.utc) or not final_path.exists()):
        raise SystemExit('Final report requires14UTC cutoff and completed supervisor summary')
    corpus = OUT/'corpus'
    events = [json.loads(line) for line in (corpus/'events.jsonl').read_text().splitlines()]
    counts = Counter(event['event'] for event in events)
    proofs, statuses, incomplete = [], Counter(), []
    for target in sorted((corpus/'bfp').glob('*.or')):
        proof_path, checked_path = target.with_suffix('.proof.json'), target.with_suffix('.checked.json')
        if not proof_path.exists():
            incomplete.append(str(target.relative_to(ROOT)))
            continue
        try:
            proof = read(proof_path)
        except json.JSONDecodeError:
            incomplete.append(str(target.relative_to(ROOT)))
            continue
        status = proof['status']
        statuses[status] += 1
        checked = read(checked_path) if checked_path.exists() else None
        verified = status == 'PROVED_NONREALIZABLE' and checked is not None and checked.get('verified') is True
        if verified:
            assert Path(checked['source_proof']).resolve() == proof_path.resolve()
            assert checked['blocking_literals'] == len(proof['blocking_clause'])
        proofs.append({'proof':str(proof_path.relative_to(ROOT)), 'proof_sha256':sha(proof_path),
                       'status':status, 'independently_verified':verified,
                       'checker':str(checked_path.relative_to(ROOT)) if checked else None,
                       'checker_sha256':sha(checked_path) if checked else None,
                       'seconds':proof.get('seconds'),
                       'blocking_literals':len(proof.get('blocking_clause') or [])})
    reused = []
    for event in events:
        if event['event']=='loaded_realizability_cut':
            proof = Path(event['file'])
            checked = corpus/('loaded-'+proof.stem+'.checked.json')
            assert read(checked)['verified'] is True
            reused.append({'proof':str(proof.relative_to(ROOT)), 'checker':str(checked.relative_to(ROOT)),
                           'literals':event['literals']})
    models = [dict(path=str(path.relative_to(ROOT)), **read(path)) for path in sorted(corpus.glob('model*.json'))]
    attempts = []
    for path in sorted((OUT/'consumer/models').glob('*/result.json')):
        data = read(path)
        for run in data['runs']:
            cert = run.get('independent_certificate',{})
            geometry = cert.get('numeric_geometry',{})
            attempts.append({'model':path.parent.name, 'label':run['label'], 'complete':data['complete'],
                             'bfp_status':data['bfp_status'], 'wall_seconds':run['wall_seconds'],
                             'cpu_seconds':run['cpu_seconds'], 'timed_out':run['timed_out'],
                             'interrupted':run['interrupted'], 'accepted':cert.get('accepted',False),
                             'orientation_violations':cert.get('original_orientation_violations'),
                             'histogram':geometry.get('interior_histogram'),
                             'certificate':cert.get('certificate')})
    fallbacks = []
    for path in sorted((OUT/'consumer/fallback').glob('*/result.json')):
        run = read(path)
        fallbacks.append({'path':str(path.relative_to(ROOT)), 'wall_seconds':run['wall_seconds'],
                          'cpu_seconds':run['cpu_seconds'], 'timed_out':run['timed_out'],
                          'interrupted':run['interrupted'], 'returncode':run['returncode'],
                          'objective':run.get('independent_verification',{}).get('raw_objective'),
                          'accepted':run.get('independent_verification',{}).get('valid',False)})
    checkpoint = read(OUT/'consumer/checkpoint.json')
    verified = sum(proof['independently_verified'] for proof in proofs)
    assert verified >= counts['proved_nonrealizable']
    data = {'as_of_utc':now.isoformat(), 'final_after_cutoff':args.final,
            'supervisor':read(final_path) if final_path.exists() else read(OUT/'supervisor/supervisor.json'),
            'producer_event_counts':dict(counts), 'new_independently_verified_proofs':verified,
            'proof_status_counts':dict(statuses), 'new_proofs':proofs, 'reused_cuts':reused,
            'incomplete_or_missing_proof_outputs':incomplete,
            'producer_reported_proof_seconds':sum(proof['seconds'] or 0 for proof in proofs),
            'producer_proof_seconds_note':'Per-proof elapsed time, not CPU; includes LP and rational certificate work. No overall producer CPU accounting is logged.',
            'exported_models':models, 'consumer_model_runs':attempts,
            'consumer_model_cpu_seconds':sum(run['cpu_seconds'] for run in attempts),
            'consumer_model_wall_seconds':sum(run['wall_seconds'] for run in attempts),
            'geometry_fallbacks':fallbacks,
            'fallback_cpu_seconds':sum(run['cpu_seconds'] for run in fallbacks),
            'fallback_wall_seconds':sum(run['wall_seconds'] for run in fallbacks),
            'consumer_checkpoint':checkpoint}
    output = OUT/('aggregate.json' if args.final else 'aggregate_draft.json')
    output.write_text(json.dumps(data,indent=2)+'\n')
    if args.final:
        success = any(run['accepted'] for run in attempts+fallbacks) or bool(checkpoint['successes'])
        if success:
            raise RuntimeError('Unexpected success: inspect certificates before preparing a negative report')
        hist = checkpoint['best_verification']['interior_histogram']
        model_rows = '\n'.join(f"|{run['model']} /{run['label']}|{run['orientation_violations']}|{run['histogram'][0]}|{run['histogram'][3]}|"
                               for run in attempts)
        text = f'''# Proof-filtered symmetry-free 19-point search: final results

This arm **did not find a 19-point geometric solution**. The successful exact-C3
configuration came from the separate SAT-guided symmetry-constrained pipeline:
[witness and certificates](../../success19/README.md). Nonrealizability of
individual abstract targets does not imply nonexistence for the geometric problem.

## Exact proof filtering

- **{verified} new independently verified nonrealizability certificates** were
  saved, separately from **{len(reused)} previously verified cuts reused at startup**.
- Proof-file statuses: `{dict(statuses)}`. There are {len(incomplete)} candidate
  orientation files without a complete proof output at cutoff; these are not
  counted as impossibility proofs.
- {len(models)} abstract targets survived the filter with UNKNOWN status and were
  exported. UNKNOWN is not a realizability certificate.
- The producer used 969 orientation variables, 937992 base clauses, no C3
  constraints, geometric phase preferences, lazy forbidden-hexagon cuts, and
  increasing Hamming balls with configured maximum distance 60. Every proof cut
  was independently checked with exact integer arithmetic before use.

The configured BFP LP limit was 30 seconds per target. Complete proof output can
take longer because rational certificate reconstruction and checking are
additional stages; the subprocess allowance was 120 seconds. Summed reported
proof-stage elapsed time was {data['producer_reported_proof_seconds']:.3f}s.
This is not CPU time; overall producer CPU usage was not logged.

## Two surviving targets and geometric fallback

The consumer processed {len(checkpoint['processed_hashes'])} targets, with
{len(attempts)} native runs total: 45 seconds of cold native v1 and 45 seconds of
warm native v6 plus line search per target. These were exploratory treatments,
not matched cold-start or fixed-work speed comparisons. All saved
coordinate outputs failed independent geometric validation.

|Target /native treatment|Orientation errors|Empty hexagons|Hexagons containing 3 points|
|---|---:|---:|---:|
{model_rows}

Logged native totals were {data['consumer_model_wall_seconds']:.3f}s
wall and {data['consumer_model_cpu_seconds']:.3f}s CPU. No success was obtained.

While waiting for proof-screened targets, the consumer started
{checkpoint['fallbacks']} bounded actual-geometry fallbacks; {len(fallbacks)} have
saved result records. They used 60-second nominal budgets, except at cutoff.
Their logged totals were {data['fallback_wall_seconds']:.3f}s wall and
{data['fallback_cpu_seconds']:.3f}s CPU. The best independently checked geometry
still contains **{hist[0]} empty hexagons and {hist[3]} hexagons with exactly three
interior points**, so it is a near-miss, not a witness. Its full histogram is
`{hist}`. No geometric solution was found (`success={success}`).

## Cutoff and artifacts

Both one-core jobs shared the 14:00UTC supervisor deadline and were budgeted
for 30000 seconds internally. Shutdown grace reserves time before that deadline;
unfinished work is **cutoff-censored**, not an UNSAT or exhaustive-search result.
The producer ended with SIGTERM (exit -15); the consumer saved its checkpoint
and exited 0. Both deadline-stop records show no remaining tagged children.
One final geometry fallback was interrupted and retained its result record.
The two exported UNKNOWN models and any incomplete last proof remain unresolved.
Producer counts above require both a claimed proof file and an existing
independent checker report; no numerical LP candidate alone is counted.

[aggregate.json](aggregate.json) records proof/checker paths and hashes, status
counts, all consumer results, CPU/wall totals, the final checkpoint, and the
supervisor's termination records. [corpus/events.jsonl](corpus/events.jsonl)
records sound-cut insertion; [consumer/checkpoint.json](consumer/checkpoint.json)
locates the best near-miss and its exact verification. Frozen sources,
parameters, and startup proofs are in [freeze.json](freeze.json) and [jobs.json](jobs.json).
This report only reads existing logs; no new search or proof runs were launched.
'''
        (OUT/'RESULTS.md').write_text(text)
    print(json.dumps({'final':args.final,'verified_new_proofs':verified,'reused':len(reused),
                      'statuses':dict(statuses),'incomplete':len(incomplete),'exported':len(models),
                      'model_runs':len(attempts),'fallback_records':len(fallbacks),
                      'fallbacks_started':checkpoint['fallbacks'],'output':str(output)}))


if __name__=='__main__':
    main()
