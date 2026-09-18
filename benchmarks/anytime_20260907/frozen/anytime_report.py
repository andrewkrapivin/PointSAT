#!/usr/bin/env python3
"""Read-only equal-total-time reporting; never import native-budget outcomes.

The event clock is completed online verification, not native discovery or a
posthoc audit. All registered targets remain in empirical-curve denominators.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAMILIES = ('symmetry19', 'mixed23', 'holes29', 'gons32', 'caps26')
TITLES = {'symmetry19': '19: no empty/3-interior hexagon', 'mixed23': '23: no7-gon / no6-hole',
          'holes29': '29: no6-hole', 'gons32': '32: no7-gon', 'caps26': '26: no7-gon / no5-cap'}
LABELS = {'original': 'Upstream', 'v4_fixed': 'v4 continuous', 'v4_retry': 'v4 retry only',
          'v4_feedback': 'v4 SAT feedback', 'v6_plain': 'v6 plain', 'v6_line': 'v6 line',
          'v6_pair': 'v6 line+pair', 'v6_retry': 'v6 retry only', 'v6_feedback': 'v6 SAT feedback'}
COLORS = {'original': '#333333', 'v4_fixed': '#2675b8', 'v4_retry': '#8660a5', 'v4_feedback': '#c25316',
          'v6_plain': '#2675b8', 'v6_line': '#248656', 'v6_pair': '#ab7f17', 'v6_retry': '#8660a5', 'v6_feedback': '#c25316'}
KINDS = ('preparation', 'native', 'feedback', 'online_audit')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def is_number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def known_sum(values):
    values = [value for value in values if is_number(value)]
    return math.fsum(values) if values else None


def fmt(value):
    if value is None:
        return 'not recorded'
    return str(value) if isinstance(value, int) else f'{value:.2f}' if is_number(value) else str(value)


def read_artifacts(db, trial_id):
    result = {}
    for name, digest, compressed in db.execute('SELECT name,sha256,data FROM artifacts WHERE trial_id=?', (trial_id,)):
        if not name.endswith('certificate.json'):
            continue
        try:
            data = zlib.decompress(compressed)
        except zlib.error as exc:
            raise ValueError(f'Corrupt certificate compression in trial{trial_id}: {name}') from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Certificate hash mismatch in trial{trial_id}: {name}')
        result[name] = (digest, json.loads(data))
    return result


def verified_times(db, trial_id, row):
    """Associate each online accepted time with an immutable stored certificate.

    Posthoc fields are intentionally never considered here. The small adapter
    accepts explicit certificate/path/hash naming, not inferred geometry times.
    """
    result = []
    entries = row.get('certificates', [])
    if not entries:
        return result
    artifacts = read_artifacts(db, trial_id)
    for entry in entries:
        elapsed = entry.get('accepted_elapsed_seconds')
        if elapsed is None:
            if entry.get('accepted') is True:
                raise ValueError(f'Accepted online certificate lacks its elapsed time in trial{trial_id}')
            continue
        if not is_number(elapsed) or elapsed < 0:
            raise ValueError(f'Invalid online verification time in trial{trial_id}')
        if entry.get('accepted') is not True:
            raise ValueError(f'Timed certificate is not explicitly accepted in trial{trial_id}')
        expected = entry.get('certificate_sha256', entry.get('sha256'))
        filename = entry.get('certificate_artifact', entry.get('certificate', entry.get('certificate_path')))
        matches = [(name, digest, data) for name, (digest, data) in artifacts.items()
                   if (expected is not None and digest == expected) or
                   (expected is None and filename is not None and
                    (name == filename or name.endswith('/'+str(filename).lstrip('/'))))]
        if not matches:
            # Some helper reports are serialized directly, with the elapsed
            # field added only in the trial record. Match full content exactly.
            payload = {key: value for key, value in entry.items() if key != 'accepted_elapsed_seconds'}
            matches = [(name, digest, data) for name, (digest, data) in artifacts.items() if data == payload]
        if not matches or len({digest for _, digest, _ in matches}) != 1:
            raise ValueError(f'Online event lacks an unambiguous stored certificate in trial{trial_id}')
        name, digest, certificate = matches[0]
        if certificate.get('valid_geometry') is not True or certificate.get('general_position') is not True:
            raise ValueError(f'Stored online certificate does not verify GP valid geometry in trial{trial_id}')
        if filename is not None and filename != name:
            raise ValueError(f'Certificate artifact name/hash disagree in trial{trial_id}')
        timestamp = entry.get('accepted_timestamp_monotonic')
        validated = certificate.get('certificate_validated_monotonic')
        start = row.get('started_monotonic')
        if not all(is_number(value) for value in (timestamp, validated, start)):
            raise ValueError(f'Nonfinite or missing absolute verification clock in trial{trial_id}')
        if validated > timestamp+1e-7:
            raise ValueError(f'Acceptance precedes certificate validation in trial{trial_id}')
        if abs(timestamp-start-elapsed) > 1e-7:
            raise ValueError(f'Elapsed acceptance differs from the trial clock in trial{trial_id}')
        if certificate.get('family') not in (None, row.get('family')):
            raise ValueError(f'Certificate belongs to a different family in trial{trial_id}')
        result.append(dict(seconds=float(elapsed), artifact=name, sha256=digest))
    return sorted(result, key=lambda item: item['seconds'])


def normalize_trial(db, trial_id, complete, row, case, arm, horizon):
    if row.get('case_id', case['id']) != case['id'] or row.get('family', case['family']) != case['family']:
        raise ValueError(f'Registration identity mismatch in trial{trial_id}')
    if row.get('arm', arm) != arm:
        raise ValueError(f'Registration arm mismatch in trial{trial_id}')
    if row.get('seed', case['seed']) != case['seed']:
        raise ValueError(f'Registration seed mismatch in trial{trial_id}')
    if row.get('initial_full_sha256', case.get('initial_full_sha256')) != case.get('initial_full_sha256'):
        raise ValueError(f'Registered full target mismatch in trial{trial_id}')
    initial = row.get('initial_target_sha256')
    if initial is not None and not is_digest(initial):
        raise ValueError(f'Invalid initial-target hash in trial{trial_id}')
    events = verified_times(db, trial_id, row)
    timely = [event for event in events if event['seconds'] <= horizon]
    first = row.get('first_verified_seconds')
    if first is not None:
        if not is_number(first) or first < 0 or first > horizon:
            raise ValueError(f'Claimed first verification is outside the total-time horizon in trial{trial_id}')
        if not timely or abs(first-timely[0]['seconds']) > 1e-7:
            raise ValueError(f'First-verification summary disagrees with stored online events in trial{trial_id}')
    elif timely:
        raise ValueError(f'Timely accepted online event omitted from primary result in trial{trial_id}')
    observed, censor = row.get('observed_seconds'), row.get('censor_seconds')
    for label, value in (('observed', observed), ('censor', censor)):
        if value is not None and (not is_number(value) or value < 0):
            raise ValueError(f'Invalid {label} time in trial{trial_id}')
    if first is not None and observed is not None and first > observed+1e-7:
        raise ValueError(f'Verification later than recorded observation in trial{trial_id}')
    if row.get('status') == 'SOLVED' and first is None:
        raise ValueError(f'SOLVED trial lacks a timely certificate in trial{trial_id}')
    normalized = dict(row, trial_id=trial_id, complete=complete, case_id=case['id'], arm=arm,
                      family=case['family'], seed=case['seed'], first_verified_seconds=first,
                      initial_target_sha256=initial, observed_seconds=observed, censor_seconds=censor,
                      online_events=events, late_verified_events=len(events)-len(timely))
    return normalized


def measure(rows):
    components = {}
    for kind in KINDS:
        selected = [part for row in rows for part in row.get('components', []) if part.get('kind') == kind]
        components[kind] = dict(cpu_seconds=known_sum(p.get('cpu_seconds') for p in selected),
                               wall_seconds=known_sum(p.get('wall_seconds') for p in selected),
                               recorded_components=len(selected),
                               cpu_recorded_components=sum(is_number(p.get('cpu_seconds')) for p in selected),
                               wall_recorded_components=sum(is_number(p.get('wall_seconds')) for p in selected))
    return dict(attempts=len(rows), components=components,
                parent_cpu_seconds=known_sum(row.get('parent_cpu_seconds') for row in rows),
                parent_wall_seconds=known_sum(row.get('parent_wall_seconds') for row in rows),
                posthoc_cpu_seconds=known_sum(row.get('posthoc_cpu_seconds') for row in rows),
                posthoc_wall_seconds=known_sum(row.get('posthoc_wall_seconds') for row in rows),
                cpu_accounting_flags=sum(bool(row.get('cpu_accounting_flag')) for row in rows),
                cpu_lower_bound_attempts=sum(bool(row.get('cpu_accounting_lower_bound')) for row in rows),
                posthoc_cpu_lower_bound_attempts=sum(bool(row.get('posthoc_cpu_accounting_lower_bound')) for row in rows),
                cpu_recorded_attempts=sum(is_number(row.get('parent_cpu_seconds')) for row in rows),
                unknown_component_kinds=dict(Counter(p.get('kind', 'MISSING') for row in rows for p in row.get('components', []) if p.get('kind') not in KINDS)))


def endpoint_at(row, seconds):
    if row is None:
        return dict(solved=False, observed=False, state='not_started')
    first = row.get('first_verified_seconds')
    if first is not None and first <= seconds:
        return dict(solved=True, observed=True, state='solved')
    # A later actual success proves the trajectory was observed through this
    # earlier milestone, even if it has no failure-censor timestamp.
    through = first if first is not None else row.get('censor_seconds')
    if through is None:
        through = row.get('observed_seconds')
    observed = through is not None and through >= seconds
    state = 'observed_unsolved' if observed else 'early_censored' if row['complete'] else 'inflight_before_milestone'
    return dict(solved=False, observed=observed, state=state)


def summarize_family(name, cases, arms, horizon, milestones, selected, attempts):
    result = dict(family=name, title=TITLES.get(name, name), registered_targets=len(cases),
                  horizon_seconds=horizon, milestones=milestones, arms={}, pairs={})
    for arm in arms:
        rows = [selected[(case['id'], arm)] for case in cases if (case['id'], arm) in selected]
        all_rows = [row for row in attempts if row['family'] == name and row['arm'] == arm]
        events = sorted((dict(case_id=row['case_id'], seconds=row['first_verified_seconds'],
                             trial_id=row['trial_id']) for row in rows if row['first_verified_seconds'] is not None),
                        key=lambda item: (item['seconds'], item['case_id']))
        curve = [dict(seconds=0., solved=0, registered=len(cases))]
        for seconds in sorted({event['seconds'] for event in events}):
            curve.append(dict(seconds=seconds, solved=sum(e['seconds'] <= seconds for e in events), registered=len(cases)))
        if curve[-1]['seconds'] != horizon:
            curve.append(dict(seconds=horizon, solved=len(events), registered=len(cases)))
        checkpoints = {}
        for seconds in milestones:
            points = [endpoint_at(selected.get((case['id'], arm)), seconds) for case in cases]
            counts = Counter(point['state'] for point in points)
            checkpoints[str(float(seconds))] = dict(solved=sum(p['solved'] for p in points),
                registered_targets=len(cases), observed_targets=sum(p['observed'] for p in points),
                unobserved_targets=sum(not p['observed'] for p in points), statuses=dict(counts))
        result['arms'][arm] = dict(milestones=checkpoints, events=events, curve=curve,
            selected_trials=len(rows), completed_trials=sum(row['complete'] for row in rows),
            missing_trials=len(cases)-len(rows), status_counts=dict(Counter(row.get('status', 'UNRECORDED') for row in rows)),
            censoring=[dict(case_id=row['case_id'], trial_id=row['trial_id'], status=row.get('status'),
                           complete=row['complete'], observed_seconds=row.get('observed_seconds'),
                           censor_seconds=row.get('censor_seconds')) for row in rows if row['first_verified_seconds'] is None],
            selected_costs=measure(rows), all_attempt_costs=measure(all_rows))
    for first, second in itertools.combinations(arms, 2):
        comparisons = {}
        for seconds in milestones:
            counts = Counter()
            details = []
            for case in cases:
                a, b = endpoint_at(selected.get((case['id'], first)), seconds), endpoint_at(selected.get((case['id'], second)), seconds)
                # Include every target in the paired count, but mark unfinished
                # exposure explicitly so neither/one-only are provisional.
                outcome = 'both' if a['solved'] and b['solved'] else 'first_only' if a['solved'] else 'second_only' if b['solved'] else 'neither'
                counts[outcome] += 1
                comparable = a['observed'] and b['observed']
                counts['fully_observed_pairs'] += comparable
                details.append(dict(case_id=case['id'], outcome=outcome, fully_observed=comparable))
            comparisons[str(float(seconds))] = dict(registered_pairs=len(cases),
                **{key: counts[key] for key in ('both', 'first_only', 'second_only', 'neither', 'fully_observed_pairs')},
                provisional_pairs=len(cases)-counts['fully_observed_pairs'], cases=details)
        result['pairs'][first+'__'+second] = comparisons
    return result


def load_study(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    horizon = config['horizon_seconds']
    milestones = sorted(config['milestones'])
    if not is_number(horizon) or horizon <= 0 or not milestones or any(not is_number(t) or not 0 < t <= horizon for t in milestones):
        raise ValueError('Invalid total-time horizon or milestones')
    cases = {case['id']: case for case in config['cases']}
    if len(cases) != len(config['cases']):
        raise ValueError('Duplicate registered case identifier')
    for case in cases.values():
        if case['family'] not in config['arms_for_family']:
            raise ValueError('Missing registered family arms')
    database = path.parent/'results.sqlite'
    attempts, selected, max_id = [], {}, None
    if database.is_file():
        db = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            for trial_id, case_id, arm, complete, raw in db.execute('SELECT id,case_id,arm,complete,record FROM trials ORDER BY id'):
                if case_id not in cases or arm not in config['arms_for_family'][cases[case_id]['family']]:
                    raise ValueError(f'Unregistered trial identity {trial_id}')
                row = normalize_trial(db, trial_id, bool(complete), json.loads(raw), cases[case_id], arm, horizon)
                attempts.append(row)
                key = (case_id, arm)
                if complete and key in selected and selected[key]['complete']:
                    raise ValueError(f'Duplicate COMPLETE trajectory for case/arm {key}')
                if complete or key not in selected or not selected[key]['complete']:
                    selected[key] = row
                max_id = trial_id
        finally:
            db.close()
    for case_id in cases:
        hashes = {row['initial_target_sha256'] for row in attempts if row['case_id'] == case_id and row.get('initial_target_sha256')}
        if len(hashes) > 1:
            raise ValueError(f'Compared arms/retries used different initial target hashes for {case_id}')
    families = {}
    for name in dict.fromkeys(case['family'] for case in cases.values()):
        members = [case for case in cases.values() if case['family'] == name]
        families[name] = summarize_family(name, members, config['arms_for_family'][name], horizon, milestones, selected, attempts)
    expected = sum(len(config['arms_for_family'][case['family']]) for case in cases.values())
    complete = len(selected) == expected and all(row['complete'] for row in selected.values())
    ledger = dict(registered_trajectories=expected, selected_trajectories=len(selected),
                  completed_selected_trajectories=sum(row['complete'] for row in selected.values()),
                  persisted_attempts=len(attempts), incomplete_attempts=sum(not row['complete'] for row in attempts),
                  repeated_attempts=len(attempts)-len({(row['case_id'], row['arm']) for row in attempts}),
                  status_counts=dict(Counter(row.get('status', 'UNRECORDED') for row in attempts)),
                  late_verified_events=sum(row['late_verified_events'] for row in attempts),
                  online_deadline_exceeded_checks=sum(c.get('status') == 'DEADLINE_EXCEEDED' for row in attempts for c in row.get('certificates', [])),
                  online_check_errors=sum(c.get('status') == 'CHECK_ERROR' for row in attempts for c in row.get('certificates', [])),
                  all_attempt_costs=measure(attempts),
                  errors=[{k: row.get(k) for k in ('trial_id', 'case_id', 'arm', 'status', 'error')} for row in attempts if row.get('error') or row.get('status') == 'ERROR'])
    sources = dict(registration=dict(path=str(path), sha256=sha(path)),
                   database=dict(path=str(database), snapshot_max_trial_id=max_id))
    integrity = path.parent/'integrity.json'
    if integrity.is_file():
        sources['coordinator_integrity'] = dict(path=str(integrity), sha256=sha(integrity), data=json.loads(integrity.read_text()))
    corpus = []
    for candidate in sorted((path.parent/'frozen').glob('*corpus*manifest*.json')):
        payload = json.loads(candidate.read_text())
        corpus.append(dict(path=str(candidate), sha256=sha(candidate), data=payload))
    return dict(registration=config, sources=sources, complete=complete, families=families,
                ledger=ledger, corpus=corpus,
                selection='One complete attempt per case/arm; duplicate complete records are an integrity error. Otherwise latest incomplete attempt. Every persisted attempt is retained in compute/error accounting.')


def analyze(registrations, draft=False):
    studies = [load_study(path) for path in registrations]
    families = {}
    for study in studies:
        overlap = set(families) & study['families'].keys()
        if overlap:
            raise ValueError('Duplicate family registrations: '+str(sorted(overlap)))
        families.update(study['families'])
    if not draft and not all(study['complete'] for study in studies):
        raise ValueError('Study incomplete; use --draft to preserve censoring/pending diagnostics')
    return dict(schema_version=1, observed_utc=datetime.now(timezone.utc).isoformat(), draft=draft,
        endpoint='First completed, accepted ONLINE verification within the total wall-time horizon. Posthoc-only successes are excluded.',
        denominator='Every registered target per family/arm; empirical verified-return fraction, not Kaplan-Meier or an IID population estimate.',
        censoring='No success event for failures; explicit censor timestamps and incomplete exposure retained. Draft counts are lower bounds, not imputed failures.',
        clock='Preparation/import, native work, feedback, and online verification share one wall clock. Actual accepted completion timestamps, no interpolation.',
        old_protocol='Earlier native-only-budget experiments are separate partial diagnostics and are never normalized or pooled into these equal-total-time curves.',
        families=families, studies=studies)


def markdown(report, output):
    lines = ['# Equal-total-time PointSAT study'+(' — DRAFT' if report['draft'] else ''), '',
        'Primary endpoint: first accepted solution returned by completed online verification within the total wall-time limit. '
        'The clock includes runtime preparation/import, native search, feedback, and online verification. SAT target sampling is outside it. '
        'Posthoc audits do not create or backdate primary success events.', '',
        'Every registered target remains in each empirical success-curve denominator. Failures have no success event and retain censoring times. '
        'These are deliberately diverse, non-IID SAT targets with one seed each; no population success rate or universal speed multiplier is claimed. '
        'Retry-only arms help distinguish repeated geometric attempts from the additional SAT-feedback step. Exact settings remain in the registration.', '',
        'This is a **cold realization-workflow comparison**, not the literal untouched PointSAT driver or steady-state batch throughput. '
        'The original arm combines the frozen original flippability implementation with the untouched native solver. Updated arms use the revised checker, '
        'persistent only within that trajectory. Conversion, required mapping, storage and geometry acceptance are common; no solver/cache is shared across targets or arms. '
        'Original → updated continuous includes both preparation and native-package changes. Updated plain/line/pair comparisons isolate those optional native flags; '
        'retry-only → feedback adds retargeting and its SAT overhead under the same segmented check schedule. Cold preparation can dominate short runs, especially for19 points.', '',
        'Earlier native-budget runs are a distinct, partially completed diagnostic study—not equal-total-time controls and not pooled here.', '',
        'The same fixed targets are reused after that diagnostic study; this is not an unseen holdout evaluation. Target-selection provenance is preserved below.', '',
        '[Self-contained PDF](anytime-report.pdf)', '', '![Verified-return curves](verified-returns.png)', '',
        '[Vector figure](verified-returns.pdf)', '']
    if report['draft']:
        lines += ['**Partial snapshot:** unstarted, early-censored, and inflight targets remain explicit. Their absence of a logged return is not an invented complete observation. '
                  'Counts are current lower bounds. Paired outcomes with incomplete exposure are provisional.', '']
    for family in report['families'].values():
        lines += ['## '+family['title'], '',
            f"Registered targets: {family['registered_targets']} per arm; total-time horizon: {family['horizon_seconds']:g} s.", '',
            '|Arm|Elapsed wall s|Verified returns / all targets|Observed through milestone or solved|Unobserved/early censored|',
            '|---|---:|---:|---:|---:|']
        for arm, data in family['arms'].items():
            for seconds, values in data['milestones'].items():
                lines.append('|'+ '|'.join([LABELS.get(arm, arm), f'{float(seconds):g}',
                    f"{values['solved']} / {values['registered_targets']}", str(values['observed_targets']), str(values['unobserved_targets'])])+'|')
        lines += ['', 'Matched outcomes on the same registered targets (all arm pairs are retained in JSON):', '',
                  '|First → second|Wall s|First only|Second only|Both|Neither|Provisional pairs|',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for pair, comparisons in family['pairs'].items():
            a, b = pair.split('__')
            if a != 'original' and not (a.endswith('_retry') and b.endswith('_feedback')):
                continue
            for seconds, values in comparisons.items():
                lines.append('|'+ '|'.join([LABELS.get(a, a)+' → '+LABELS.get(b, b), f'{float(seconds):g}']+
                    [str(values[key]) for key in ('first_only', 'second_only', 'both', 'neither', 'provisional_pairs')])+'|')
        lines.append('')
    lines += ['## Compute and interruptions', '',
        'All recorded attempts are counted below, including failed and interrupted attempts—not only successes. '
        'Component CPU is measured processor consumption; wall is not a CPU substitute. Summed worker wall is not calendar duration. '
        'Parent totals and component totals overlap and must not be added. Posthoc audit costs are outside the primary clock and separate.', '',
        '|Family|Arm|Attempts|Preparation CPU s|Native CPU s|Feedback CPU s|Online verification CPU s|Parent CPU s|Posthoc CPU s|Parent wall s|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for family in report['families'].values():
        for arm, data in family['arms'].items():
            cost = data['all_attempt_costs']
            lines.append('|'+ '|'.join([family['family'], LABELS.get(arm, arm), str(cost['attempts'])]+
                [fmt(cost['components'][kind]['cpu_seconds']) for kind in KINDS]+
                [fmt(cost[key]) for key in ('parent_cpu_seconds', 'posthoc_cpu_seconds', 'parent_wall_seconds')])+'|')
    for study in report['studies']:
        ledger = study['ledger']
        lines += ['', f"Persisted attempts: {ledger['persisted_attempts']}; incomplete attempts: {ledger['incomplete_attempts']}; "
            f"repeated case/arm attempts: {ledger['repeated_attempts']}; verified events after the horizon (excluded): {ledger['late_verified_events']}.", '',
            'Statuses: `'+json.dumps(ledger['status_counts'], sort_keys=True)+'`.', '',
            f"Online deadline-exceeded checks: {ledger['online_deadline_exceeded_checks']}; online checker errors: {ledger['online_check_errors']}. "
            f"Search CPU lower-bound attempts: {ledger['all_attempt_costs']['cpu_lower_bound_attempts']}; "
            f"posthoc CPU lower-bound attempts: {ledger['all_attempt_costs']['posthoc_cpu_lower_bound_attempts']}. "
            'Abruptly killed descendants can leave unrecorded CPU; these are explicitly lower bounds, not exact complete totals.', '',
            'Source registration: ['+str(Path(study['sources']['registration']['path']).name)+'](<'+
            os.path.relpath(study['sources']['registration']['path'], output)+'>), SHA256 `'+study['sources']['registration']['sha256']+'`.', '']
        for corpus in study['corpus']:
            data = corpus['data']
            lines += ['Corpus provenance: `'+json.dumps(data.get('strata', {}), sort_keys=True)+'`. '
                      'Fresh and reused/proof-filtered SAT target strata remain distinct. Historical selection did not inspect realization outcomes. '
                      'The known positive-control type is excluded. The original benchmark CNF does not acquire generation-only cuts.', '']
            lines += ['Outside-clock corpus construction: '+fmt(data.get('generation_child_cpu_seconds'))+' fresh-generation CPU s; '+
                fmt(data.get('combine_validation_child_cpu_seconds'))+' combined-corpus revalidation CPU s; '+
                fmt(data.get('combine_controller_cpu_seconds'))+' combine-controller CPU s. '
                'Fresh and combine timers are separate; historical generation sunk costs are not attributed to this batch.', '']
    if report.get('positive_control'):
        item = report['positive_control']
        lines += ['## Separate earlier positive control', '',
            'The known realizable control is excluded from the main target corpus. Its earlier native-budget diagnostic is not an equal-total-time trial; '
            'native timings are not interpreted as first verified-return times or pooled into these curves.', '',
            '[Control provenance](<'+os.path.relpath(item['path'], output)+'>), SHA256 `'+item['sha256']+'`.', '']
    if report.get('machine'):
        item = report['machine']
        lines += ['Machine snapshot: [reported hardware and environment](<'+os.path.relpath(item['path'], output)+'>), SHA256 `'+item['sha256']+'`. '
            'The recorded environment is virtualized; CPU topology is not evidence of dedicated physical cores. The benchmark has a two-worker limit.', '']
    lines += ['The complete JSON retains event timestamps and certificate hashes, per-target censoring, all matched pairs, component timing coverage, and errors. '
              'No first-success time is inferred from a final coordinate file or posthoc audit. Operational failure is not an impossibility proof.', '',
              '[Machine-readable report](report.json)', '']
    return '\n'.join(lines)


def plots(report, output):
    previous = os.environ.get('MPLCONFIGDIR')
    with tempfile.TemporaryDirectory(prefix='pointsat-anytime-mpl-') as cache:
        os.environ['MPLCONFIGDIR'] = cache
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            plt.rcParams['pdf.fonttype'] = 42
            families = list(report['families'].values())
            figure, axes = plt.subplots(1, len(families), figsize=(max(6, 3.8*len(families)), 4.5), squeeze=False)
            for axis, family in zip(axes[0], families):
                for arm, data in family['arms'].items():
                    curve = data['curve']
                    axis.step([p['seconds'] for p in curve], [100*p['solved']/family['registered_targets'] for p in curve],
                              where='post', label=LABELS.get(arm, arm), color=COLORS.get(arm))
                    for seconds, point in data['milestones'].items():
                        axis.plot(float(seconds), 100*point['solved']/point['registered_targets'], 'o', markersize=4,
                                  color=COLORS.get(arm), markerfacecolor='white' if point['unobserved_targets'] else COLORS.get(arm))
                axis.set_title(family['title']+'\n'+f"{family['registered_targets']} registered targets", fontsize=10)
                axis.set_xlim(0, family['horizon_seconds'])
                axis.set_ylim(-1, 101)
                axis.set_xticks(family['milestones'])
                axis.set_xlabel('Total elapsed wall seconds')
                axis.grid(alpha=.2)
                axis.legend(fontsize=7, loc='upper left')
            axes[0][0].set_ylabel('Verified returns / all targets (%)')
            figure.suptitle(('DRAFT — ' if report['draft'] else '')+'Actual online-verification returns; no posthoc backdating', fontsize=12)
            figure.tight_layout(rect=(0, 0, 1, .94))
            for suffix in ('pdf', 'png'):
                figure.savefig(output/f'verified-returns.{suffix}', dpi=170)
            plt.close(figure)
        finally:
            if previous is None:
                os.environ.pop('MPLCONFIGDIR', None)
            else:
                os.environ['MPLCONFIGDIR'] = previous


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--draft', action='store_true')
    parser.add_argument('--machine-info', type=Path)
    parser.add_argument('--positive-control-result', type=Path)
    args = parser.parse_args(argv)
    report = analyze(args.registration, args.draft)
    for name, path in (('machine', args.machine_info), ('positive_control', args.positive_control_result)):
        report[name] = dict(path=str(path.resolve()), sha256=sha(path), data=json.loads(path.read_text())) if path else None
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plots(report, output)
    (output/'README.md').write_text(markdown(report, output))
    from anytime_pdf import build_pdf
    report['pdf'] = build_pdf(report, output, LABELS)
    report['reporter_sha256'] = sha(__file__)
    report['pdf_helper_sha256'] = sha(HERE/'anytime_pdf.py')
    report['outputs'] = {path.name: sha(path) for path in output.iterdir() if path.is_file()}
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output), draft=args.draft, complete=all(s['complete'] for s in report['studies']))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
