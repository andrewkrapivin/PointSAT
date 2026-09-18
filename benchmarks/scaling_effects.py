#!/usr/bin/env python3
"""Read-only, within-target native-budget scaling effects for frozen studies.

No searches or exact verifier reruns. SQLite certificates are hash/content
checked before using their residuals. A lower delta means fewer violations;
delta is ALWAYS higher-budget minus lower-budget, never a ratio of medians.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import sqlite3
import statistics
import zlib


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _certificate(db, trial_id, audit):
    """Match the final audit to an immutable compressed certificate artifact."""
    expected = {key: value for key, value in audit.items() if key != 'checkpoint'}
    for name, expected_sha, compressed in db.execute(
            "SELECT name,sha256,data FROM artifacts WHERE trial_id=? AND name LIKE '%/certificate.json'", (trial_id,)):
        try:
            data = zlib.decompress(compressed)
        except zlib.error as error:
            raise ValueError(f'Corrupt compressed certificate: trial {trial_id}/{name}') from error
        if sha(data) != expected_sha:
            raise ValueError(f'Certificate hash mismatch: trial {trial_id}/{name}')
        certificate = json.loads(data)
        if certificate == expected:
            return certificate
    return None


def _endpoint(db, trial_id, row):
    """A missing/error final checkpoint is a recorded primary failure, not GP."""
    valid = row.get('primary_valid_geometry')
    if not isinstance(valid, bool):
        raise ValueError(f'Missing primary endpoint in completed trial {trial_id}')
    candidates = [a for a in row.get('audits', [])
                  if row.get('final_checkpoint') and a.get('checkpoint') == row['final_checkpoint']]
    if len(candidates) > 1:
        raise ValueError(f'Duplicate final checkpoint audit: trial {trial_id}')
    result = {'valid': valid, 'reading': None, 'reason': 'missing_final_checkpoint'}
    if not candidates:
        if valid:
            raise ValueError(f'Positive endpoint without final audit: trial {trial_id}')
        return result
    audit = candidates[0]
    if bool(audit.get('valid_geometry')) != valid:
        raise ValueError(f'Primary/final audit disagreement: trial {trial_id}')
    if audit.get('audit_error') or audit.get('error'):
        result['reason'] = 'audit_error'
    else:
        certificate = _certificate(db, trial_id, audit)
        if certificate is None:
            result['reason'] = 'missing_or_mismatched_certificate'
        elif not isinstance(certificate.get('general_position'), bool):
            result['reason'] = 'missing_general_position_status'
        elif not certificate['general_position']:
            result['reason'] = 'not_general_position'
        else:
            residual = certificate.get('forbidden_polygons', certificate.get('forbidden_hexagons'))
            if not count(residual):
                result['reason'] = 'missing_or_invalid_forbidden_count'
            else:
                if (residual == 0) != valid:
                    raise ValueError(f'GP forbidden count/validity disagreement: trial {trial_id}')
                result.update(reading=certificate, reason=None)
    if valid and result['reading'] is None:
        raise ValueError(f'Positive endpoint lacks a usable GP certificate: trial {trial_id}')
    return result


def _metric(pairs, orientation=False):
    deltas = []
    excluded = Counter()
    missing_sides = Counter()
    for lower, higher in pairs:
        readings = [lower['reading'], higher['reading']]
        reasons = [lower['reason'], higher['reason']]
        values = []
        for i, reading in enumerate(readings):
            if reading is None:
                values.append(None)
                continue
            value = reading.get('orientation_violations') if orientation else reading.get(
                'forbidden_polygons', reading.get('forbidden_hexagons'))
            if not count(value):
                reasons[i] = 'missing_or_invalid_orientation_count' if orientation else 'missing_or_invalid_forbidden_count'
                value = None
            if orientation and value is not None and (not count(reading.get('constraint_count')) or value > reading['constraint_count']):
                reasons[i] = 'missing_or_invalid_constraint_count'
                value = None
            values.append(value)
        if orientation and all(value is not None for value in values):
            hashes = [r.get('source_full_target_sha256', r.get('input_signature', {}).get('target_sha256'))
                      for r in readings]
            if not all(digest(h) for h in hashes):
                for i, h in enumerate(hashes):
                    if not digest(h):
                        reasons[i] = 'missing_orientation_target_hash'; values[i] = None
            elif hashes[0] != hashes[1] or readings[0].get('constraint_count') != readings[1].get('constraint_count'):
                raise ValueError('Orientation residuals refer to different full targets/constraint counts')
        if all(value is not None for value in values):
            deltas.append(values[1]-values[0])
        else:
            missing_sides['both' if all(value is None for value in values) else 'lower' if values[0] is None else 'higher'] += 1
            for label, reason in zip(('lower', 'higher'), reasons):
                if reason:
                    excluded[label+':'+reason] += 1
    return {'paired_GP': len(deltas), 'lower': sum(d < 0 for d in deltas),
            'equal': sum(d == 0 for d in deltas), 'higher': sum(d > 0 for d in deltas),
            'median_delta': statistics.median(deltas) if deltas else None,
            'missing': len(pairs)-len(deltas),
            'missing_lower': missing_sides['lower'], 'missing_higher': missing_sides['higher'],
            'missing_both': missing_sides['both'], 'reasons': dict(sorted(excluded.items()))}


def _study(registration_path, include_orientation, include_pairs):
    path = Path(registration_path).resolve()
    raw = path.read_bytes(); config = json.loads(raw)
    cases = {c['id']: c for c in config['cases']}
    if len(cases) != len(config['cases']):
        raise ValueError('Duplicate registered case ID')
    budgets = sorted(config['budgets'])
    if len(set(budgets)) != len(budgets) or any(not number(b) or b <= 0 for b in budgets):
        raise ValueError('Invalid registered budgets')
    arms = config['arms']
    if len(set(arms)) != len(arms):
        raise ValueError('Duplicate registered arm')
    database = path.parent/'results.sqlite'
    latest = {}; ledger = Counter(); source = {'registration': str(path), 'registration_sha256': sha(raw),
        'database': str(database), 'snapshot_max_trial_id': None, 'database_present': database.is_file()}
    if database.is_file():
        db = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
            # A single read transaction includes both ledger and certificate blobs.
            for trial_id, case_id, arm, budget, complete, record in db.execute(
                    'SELECT id,case_id,arm,budget,complete,record FROM trials ORDER BY id'):
                ledger['attempts'] += 1; source['snapshot_max_trial_id'] = trial_id
                if not complete:
                    ledger['incomplete_attempts'] += 1; continue
                row = json.loads(record)
                if case_id not in cases or arm not in arms or budget not in budgets:
                    raise ValueError(f'Unregistered completed trial {trial_id}')
                case = cases[case_id]
                if row.get('case_id') != case_id or row.get('arm') != arm or row.get('budget', row.get('budget_seconds')) != budget:
                    raise ValueError(f'SQLite/record identity disagreement: trial {trial_id}')
                if row.get('seed') != case['seed']:
                    raise ValueError(f'Registered seed mismatch: trial {trial_id}')
                input_sha = row.get('initial_target_sha256', row.get('input_sha256'))
                if not digest(input_sha):
                    raise ValueError(f'Missing/invalid initial target hash: trial {trial_id}')
                family = case.get('family', 'symmetry19')
                if row.get('family', family) != family:
                    raise ValueError(f'Family mismatch: trial {trial_id}')
                key = (case_id, arm, budget)
                if key in latest:
                    ledger['superseded_completed_attempts'] += 1
                ledger['completed_attempts'] += 1
                latest[key] = {'trial_id': trial_id, 'seed': row['seed'], 'input_sha256': input_sha,
                               'endpoint': _endpoint(db, trial_id, row)}
        finally:
            db.close()
    source['ledger'] = {key: ledger[key] for key in ('attempts', 'incomplete_attempts',
        'completed_attempts', 'superseded_completed_attempts')}
    source['selected_completed_trials'] = len(latest)
    result = {}
    for family in sorted({c.get('family', 'symmetry19') for c in cases.values()}):
        selected = [c for c in cases.values() if c.get('family', 'symmetry19') == family]
        result[family] = {'registered_targets': len(selected), 'arms': {}}
        for arm in arms:
            comparisons = {}
            for low, high in itertools.combinations(budgets, 2):
                stats = {'lower_budget': low, 'higher_budget': high,
                    'adjacent': budgets.index(high) == budgets.index(low)+1,
                    'registered_targets': len(selected), 'completed_pairs': 0,
                    'missing_lower': 0, 'missing_higher': 0, 'missing_both': 0,
                    'validity': {'gains': 0, 'losses': 0, 'both': 0, 'neither': 0}}
                paired = []; details = []
                for case in selected:
                    lower = latest.get((case['id'], arm, low)); higher = latest.get((case['id'], arm, high))
                    if lower is None or higher is None:
                        stats['missing_both' if lower is None and higher is None else 'missing_lower' if lower is None else 'missing_higher'] += 1
                        continue
                    if lower['seed'] != higher['seed'] or lower['input_sha256'] != higher['input_sha256']:
                        raise ValueError(f'Unmatched seed/initial target across budgets: {family}/{case["id"]}/{arm}/{low}/{high}')
                    a, b = lower['endpoint'], higher['endpoint']
                    stats['completed_pairs'] += 1; paired.append((a, b))
                    outcome = 'both' if a['valid'] and b['valid'] else 'losses' if a['valid'] else 'gains' if b['valid'] else 'neither'
                    stats['validity'][outcome] += 1
                    if include_pairs:
                        details.append({'case_id': case['id'], 'seed': lower['seed'],
                            'input_sha256': lower['input_sha256'], 'canonical_sha256': case.get('canonical_sha256'),
                            'lower_trial_id': lower['trial_id'], 'higher_trial_id': higher['trial_id'],
                            'lower_valid': a['valid'], 'higher_valid': b['valid'], 'outcome': outcome,
                            'forbidden': _metric([(a, b)]),
                            **({'orientation': _metric([(a, b)], True)} if include_orientation else {})})
                stats['forbidden'] = _metric(paired)
                if include_orientation:
                    stats['orientation'] = _metric(paired, True)
                if include_pairs:
                    stats['pairs'] = details
                comparisons[str(float(low))+'__'+str(float(high))] = stats
            result[family]['arms'][arm] = {'comparisons': comparisons}
    return source, result


def analyze(registrations, include_orientation=True, include_pairs=False):
    """Read registrations plus results.sqlite; return JSON-serializable effects.

    Uses the latest complete attempt per registered case/arm/budget. Missing
    or interrupted attempts are not manufactured into completed observations.
    A completed missing/error output remains a failure under the frozen primary
    endpoint, while its absent residual is explicitly excluded from GP pairs.
    """
    if isinstance(registrations, (str, Path)):
        registrations = [registrations]
    output = {'schema_version': 1, 'observed_utc': datetime.now(timezone.utc).isoformat(),
        'sources': [], 'families': {}, 'primary': 'Final checkpoint only, paired within target and arm.',
        'delta_definition': 'Higher-budget residual minus lower-budget residual; negative means fewer violations.',
        'residual_scope': 'Both final checkpoints must have a hash/content-checked stored audit certificate, general position, and a nonnegative integer residual. No verifier rerun is performed.',
        'missing_scope': 'Missing budget trials are separated from completed primary failures. Non-GP/missing/error certificate readings are excluded only from residual comparisons.',
        'interpretation': 'Fresh starts at each native budget with the same registered case seed and identical initial-target SHA. These are paired outcomes, not continuations or an IID population estimate; gains and losses are both reported.'}
    for path in registrations:
        source, families = _study(path, include_orientation, include_pairs)
        overlap = set(output['families']) & set(families)
        if overlap:
            raise ValueError('Duplicate family registrations: '+str(sorted(overlap)))
        output['sources'].append(source); output['families'].update(families)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', action='append', required=True)
    parser.add_argument('--output', help='Write a NEW JSON file; default stdout.')
    parser.add_argument('--no-orientation', action='store_true')
    parser.add_argument('--include-pairs', action='store_true')
    args = parser.parse_args()
    output = json.dumps(analyze(args.registration, not args.no_orientation, args.include_pairs), indent=2, allow_nan=False)+'\n'
    if args.output:
        with Path(args.output).open('x') as stream:
            stream.write(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
