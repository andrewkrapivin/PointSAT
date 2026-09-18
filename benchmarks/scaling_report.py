#!/usr/bin/env python3
"""Read-only aggregation of the19-point and four-paper-family scaling studies.

Writes a NEW report directory only. It never launches SAT, native search, audit,
or benchmark summarization, and never changes registrations/results databases.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAMILIES = ('symmetry19', 'mixed23', 'holes29', 'gons32', 'caps26')
TITLES = {'symmetry19': '19: no empty/3-interior hexagon', 'mixed23': '23: no7-gon / no6-hole',
          'holes29': '29: no6-hole', 'gons32': '32: no7-gon', 'caps26': '26: no7-gon / no5-cap'}
LABELS = {'original': 'Upstream', 'improved_fixed': 'v4 fixed target', 'improved_feedback': 'v4 feedback',
          'v6_plain': 'v6 plain', 'v6_line10': 'v6 line', 'v6_line10_pair10': 'v6 line+pair',
          'v6_feedback': 'v6 feedback'}
COLORS = {'original': '#333333', 'improved_fixed': '#2675b8', 'improved_feedback': '#c25316',
          'v6_plain': '#2675b8', 'v6_line10': '#248656', 'v6_line10_pair10': '#8660a5',
          'v6_feedback': '#c25316'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def first(data, *keys):
    return next((data[key] for key in keys if data.get(key) is not None), None)


def total_known(values):
    values = list(values)
    known = [value for value in values if value is not None]
    return math.fsum(known) if known else None


def fmt(value, places=2):
    if value is None:
        return 'not recorded'
    if isinstance(value, int):
        return str(value)
    return f'{value:.{places}f}'


def read_attempts(database):
    """Supplement summary denominators with ALL persisted attempts, read-only."""
    if not database.is_file():
        return None
    db = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)
    try:
        columns = {row[1] for row in db.execute('PRAGMA table_info(trials)')}
        if not {'complete', 'record'}.issubset(columns):
            return {'warning': 'Unrecognized trials schema; raw attempt counts unavailable'}
        identity_columns = [key for key in ('case_id', 'arm', 'budget', 'budget_seconds') if key in columns]
        query = 'SELECT complete,record'+''.join(','+key for key in identity_columns)+' FROM trials'
        if 'id' in columns:
            query += ' ORDER BY id'
        rows = []
        for stored in db.execute(query):
            row = json.loads(stored[1])
            for key, value in zip(identity_columns, stored[2:]):
                row.setdefault(key, value)
            rows.append((bool(stored[0]), row))
    finally:
        db.close()
    keys = [(row.get('case_id'), row.get('arm'), first(row, 'budget_seconds', 'budget')) for _, row in rows]
    errors = []
    for done, row in rows:
        audit_errors = [item for item in row.get('audits', []) if item.get('audit_error') or item.get('error')]
        if row.get('error') or audit_errors or row.get('status') in ('ERROR', 'MISSING_OUTPUT', 'NO_CHECKPOINT'):
            errors.append({'case_id': row.get('case_id'), 'arm': row.get('arm'),
                           'budget': first(row, 'budget_seconds', 'budget'), 'complete': done,
                           'status': row.get('status'), 'error': row.get('error'),
                           'audit_errors': [{key: item.get(key) for key in ('checkpoint', 'audit_error', 'error')} for item in audit_errors]})
    return {'persisted_attempts': len(rows), 'completed_attempts': sum(done for done, _ in rows),
            'incomplete_attempts': sum(not done for done, _ in rows),
            'repeated_case_arm_budget_attempts': len(rows)-len(set(keys)),
            'status_counts': dict(Counter(row.get('status', 'UNRECORDED') for _, row in rows)),
            'external_interruptions': sum(bool(first(row, 'externally_interrupted', 'external_interruption', 'interrupted')) for _, row in rows),
            'overhead_watchdogs': sum(bool(row.get('overhead_watchdog')) for _, row in rows),
            'audit_watchdogs': sum(bool(row.get('audit_watchdog')) for _, row in rows),
            'forced_native_kills': sum(bool(stage.get('forced_kill')) for _, row in rows for stage in row.get('stages', [])),
            'recorded_worker_cpu_seconds_all_attempts': total_known(first(row, 'parent_cpu_seconds', 'worker_observed_cpu_seconds') for _, row in rows),
            'recorded_worker_wall_seconds_all_attempts': total_known(first(row, 'parent_wall_seconds', 'worker_wall_seconds') for _, row in rows),
            'recorded_audit_cpu_seconds_all_attempts': total_known(row.get('audit_cpu_seconds') for _, row in rows),
            'cost_warning': 'Only persisted timing fields are counted; abrupt termination can leave additional unrecorded work.',
            'errors': errors}


def target_count(registration, family, group):
    cases = registration.get('cases', [])
    if family == 'symmetry19' and cases:
        return len(cases)
    matches = [case for case in cases if first(case, 'problem', 'family') == family]
    if matches:
        return len(matches)
    count = first(group, 'registered_targets', 'targets', 'unique_target_models', 'unique_targets')
    if count is None:
        count = first(registration, 'targets_per_family', 'targets')
        if isinstance(count, dict):
            count = count.get(family)
    return count if isinstance(count, int) else None


def normalize_family(name, registration, summary):
    raw = summary if name == 'symmetry19' else summary.get('families', {}).get(name, {})
    expected = target_count(registration, name, raw)
    configured_budgets = registration.get('budgets', [])
    budgets = sorted({float(value) for value in configured_budgets} |
                     {float(value) for value in raw.get('budgets', {})})
    registered_arms = registration.get('arms', [])
    if isinstance(registered_arms, dict):
        registered_arms = list(registered_arms)
    if registered_arms and isinstance(registered_arms[0], dict):
        registered_arms = [first(arm, 'id', 'name', 'arm') for arm in registered_arms]
    arms = list(registered_arms)
    for group in raw.get('budgets', {}).values():
        arms.extend(arm for arm in group.get('arms', {}) if arm not in arms)
    result = {'family': name, 'title': TITLES[name], 'registered_targets': expected, 'arms': arms, 'budgets': {}}
    for budget in budgets:
        data = next((value for key, value in raw.get('budgets', {}).items() if float(key) == budget), {})
        rows = {}
        for arm in arms:
            record = data.get('arms', {}).get(arm)
            if record is None:
                rows[arm] = {'available': False, 'registered_targets': expected}
                continue
            complete = int(record.get('trials', 0))
            valid = first(record, 'valid_final', 'valid_geometry_trials')
            gp = first(record, 'general_position_final', 'general_position_finals')
            if valid is not None and not 0 <= valid <= complete:
                raise ValueError(f'Impossible success denominator: {name}/{budget}/{arm}')
            if expected is not None and complete > expected:
                raise ValueError(f'Duplicate completed targets: {name}/{budget}/{arm}')
            rows[arm] = dict(record, available=True, trials=complete, valid_final=valid,
                             registered_targets=expected, pending_targets=expected-complete if expected is not None else None,
                             general_position_final=gp,
                             median_forbidden_in_GP=first(record, 'median_forbidden_count_in_GP', 'median_forbidden_hexagons_in_GP', 'median_forbidden_in_GP'),
                             median_target_violations_in_GP=first(record, 'median_orientation_violations_in_GP', 'median_target_violations_in_GP'))
        result['budgets'][str(budget)] = {'arms': rows, 'pairs': data.get('pairs', {})}
    return result


def load_study(registration_path, kind, draft):
    registration_path = registration_path.resolve()
    registration = json.loads(registration_path.read_text())
    summary_path = registration_path.parent/'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    if not draft and not summary.get('complete'):
        raise ValueError(f'Incomplete or missing summary: {summary_path}; use --draft for partial results')
    names = ('symmetry19',) if kind == 'nineteen' else FAMILIES[1:]
    families = [normalize_family(name, registration, summary) for name in names]
    if not draft:
        for family in families:
            if family['registered_targets'] is None or not family['arms'] or not family['budgets']:
                raise ValueError('Missing final registration denominators: '+family['family'])
            for group in family['budgets'].values():
                for record in group['arms'].values():
                    if not record['available'] or record.get('trials') != family['registered_targets']:
                        raise ValueError('Final summary lacks a complete arm: '+family['family'])
    sources = {'registration': {'path': str(registration_path), 'sha256': sha(registration_path)},
               'summary': {'path': str(summary_path), 'sha256': sha(summary_path)} if summary_path.is_file() else None}
    corpus = registration.get('corpus')
    corpus_metadata = None
    if isinstance(corpus, str):
        corpus_path = Path(corpus)
        if not corpus_path.is_absolute():
            candidate = registration_path.parent/corpus_path
            corpus_path = candidate if candidate.exists() else Path(registration.get('root', '.'))/corpus_path
        frozen_manifest = registration_path.parent/'frozen/corpus-manifest.json'
        corpus_manifest = frozen_manifest if frozen_manifest.is_file() else corpus_path/'manifest.json' if corpus_path.is_dir() else corpus_path
        if corpus_manifest.is_file() and corpus_manifest.suffix == '.json':
            value = json.loads(corpus_manifest.read_text())
            corpus_metadata = {key: value.get(key) for key in ('state', 'accepted_models', 'generation_child_cpu_seconds', 'generation_wall_seconds',
                                                               'canonical_supported', 'canonical_unsupported', 'supported_distinct_types',
                                                               'combine_validation_child_cpu_seconds', 'combine_controller_cpu_seconds',
                                                               'combine_wall_seconds', 'strata', 'exclusion_counts')}
            corpus_metadata['selection'] = value.get('registration', {}).get('selection')
            corpus_metadata['control_exclusion'] = value.get('registration', {}).get('control_canonicalization')
            sources['corpus_manifest'] = {'path': str(corpus_manifest.resolve()), 'sha256': sha(corpus_manifest)}
    rows = [record for family in families for group in family['budgets'].values()
            for record in group['arms'].values() if record.get('available')]
    totals = {key: total_known(row.get(key) for row in rows) for key in
              ('native_cpu_seconds', 'native_wall_seconds', 'worker_observed_cpu_seconds', 'worker_wall_seconds', 'audit_cpu_seconds', 'audit_wall_seconds')}
    totals.update({key: summary.get(key) for key in ('preparation_cpu_seconds', 'preparation_wall_seconds')})
    for key in ('generation_child_cpu_seconds', 'generation_wall_seconds', 'combine_validation_child_cpu_seconds',
                'combine_controller_cpu_seconds', 'combine_wall_seconds'):
        totals['corpus_'+key] = corpus_metadata.get(key) if corpus_metadata else None
    totals['worker_cpu_beyond_recorded_native'] = (
        totals['worker_observed_cpu_seconds']-totals['native_cpu_seconds']
        if totals['worker_observed_cpu_seconds'] is not None and totals['native_cpu_seconds'] is not None else None)
    totals['registered_native_allowance_seconds'] = (
        math.fsum(family['registered_targets']*len(family['arms'])*math.fsum(map(float, family['budgets'])) for family in families)
        if all(family['registered_targets'] is not None for family in families) else None)
    return {'kind': kind, 'sources': sources, 'complete': bool(summary.get('complete')), 'registration': registration,
            'registered_trials': summary.get('registered_trials'), 'completed_trials': summary.get('completed_trials'),
            'families': families, 'costs': totals, 'corpus': corpus_metadata,
            'cost_field_observations': {key: {'recorded_arm_budget_rows': sum(row.get(key) is not None for row in rows),
                                             'completed_arm_budget_rows': len(rows)} for key in
                                        ('native_cpu_seconds', 'native_wall_seconds', 'worker_observed_cpu_seconds', 'worker_wall_seconds', 'audit_cpu_seconds', 'audit_wall_seconds')},
            'attempts': read_attempts(registration_path.parent/'results.sqlite'),
            'summary_missing': not summary_path.is_file()}


def link(path, output, label):
    return f'[{label}](<{os.path.relpath(path, output)}>)'


def markdown(studies, output, draft, effects=None, machine=None, control=None):
    lines = ['# PointSAT checkpoint scaling study'+(' — DRAFT' if draft else ''), '',
             'Five geometric problems, fixed SAT-only targets, and independent registered native budgets. '
             'This report reads existing results; it does not run search or alter earlier reports.', '',
             'Primary endpoint: exact geometric validity of the final saved checkpoint. Any saved valid checkpoint is secondary. '
             'For19 points, numeric geometric validity is distinct from exact C3 reconstruction and from matching the original SAT target.', '',
             'Each problem uses its registered target count and one native seed per target. Targets are deliberately diverse, not an IID population sample. '
             'Results can be seed-sensitive; neither a universal success rate nor a statistically established speed multiplier is claimed. '
             'Budgets restart from the same frozen input; curves are descriptive checkpoint comparisons, not survival curves. '
             'No actual first-success time is observed or interpolated.', '']
    if draft:
        lines += ['**Incomplete snapshot:** pending targets are not failures. Plotted incomplete points are hollow; their certified counts are only current lower bounds. '
                  'A missing metric is never replaced by zero.', '']
    for study in studies:
        corpus = study.get('corpus') or {}
        if corpus.get('strata'):
            counts = ', '.join(f'{count} {name.replace("_", " ")}' for name, count in corpus['strata'].items())
            lines += [f"The {study['kind']} target corpus contains {counts}. Historical targets were selected in fixed source/line order "
                      'from initial SAT assignments, not coordinate or feedback outcomes. Historical proof-filtered generation and fresh generation are distinct strata; '
                      'the benchmark itself uses the original CNF without those additional cuts. The known positive-control canonical type was explicitly excluded. '
                      'This is not an all-fresh or IID sample.', '']
    lines += ['![Final checkpoint counts and actual geometric residuals](checkpoints.png)', '',
              '[Vector checkpoint figure](checkpoints.pdf)', '',
              'Residual medians include only general-position final checkpoints; their denominators are shown below. '
              'Residuals count actual forbidden polygons/caps, not orientation-target errors, and are not comparable in scale between problems.', '',
              '[Self-contained PDF report](scaling-report.pdf)', '']
    for study in studies:
        for family in study['families']:
            lines += ['## '+family['title'], '', f"Registered targets: {fmt(family['registered_targets'])} per arm/budget.", '',
                      '|Native budget s|Arm|Completed / registered|Valid final|Any saved valid|GP finals|Median forbidden in GP|Median target errors in GP|Errors|Overhead watchdogs|Audit errors|',
                      '|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
            for budget, group in family['budgets'].items():
                for arm, row in group['arms'].items():
                    values = [f'{float(budget):g}', LABELS.get(arm, arm),
                              f"{fmt(row.get('trials'))} / {fmt(family['registered_targets'])}",
                              fmt(row.get('valid_final')), fmt(row.get('valid_any_checkpoint')),
                              fmt(row.get('general_position_final')), fmt(row.get('median_forbidden_in_GP')),
                              fmt(row.get('median_target_violations_in_GP')),
                              fmt(row.get('error_trials')), fmt(row.get('watchdog_trials')), fmt(row.get('audit_errors'))]
                    lines.append('|'+ '|'.join(values)+'|')
            lines += ['', 'Paired final-checkpoint outcomes on the same completed targets:', '',
                      '|Budget s|First → second|Complete pairs|First only|Second only|Both|Neither|',
                      '|---:|---|---:|---:|---:|---:|---:|']
            for budget, group in family['budgets'].items():
                for names, pair in group['pairs'].items():
                    parts = names.split('__')
                    label = ' → '.join(LABELS.get(part, part) for part in parts)
                    lines.append('|'+ '|'.join([f'{float(budget):g}', label]+[fmt(pair.get(key)) for key in ('pairs', 'first_only', 'second_only', 'both', 'neither')])+'|')
            lines.append('')
            family_effects = (effects or {}).get('families', {}).get(family['family'])
            if family_effects:
                lines += ['Within-target effect of increasing the budget (same registered seed and initial SAT target):', '',
                          '|Arm|Budget change s|Complete pairs|Validity gains|Validity losses|Paired GP|Fewer / same / more forbidden|Median forbidden change|',
                          '|---|---:|---:|---:|---:|---:|---|---:|']
                for arm, arm_data in family_effects['arms'].items():
                    for change in arm_data['comparisons'].values():
                        residual = change['forbidden']
                        lines.append('|'+ '|'.join([LABELS.get(arm, arm),
                            f"{change['lower_budget']:g} → {change['higher_budget']:g}",
                            fmt(change['completed_pairs']), fmt(change['validity']['gains']),
                            fmt(change['validity']['losses']), fmt(residual['paired_GP']),
                            ' / '.join(fmt(residual[k]) for k in ('lower', 'equal', 'higher')),
                            fmt(residual['median_delta'])])+'|')
                lines += ['', 'Change means higher-budget minus lower-budget residual, computed per paired target—not subtraction of group medians. '
                          'Negative is better. Both final checkpoints need stored, hash/content-checked GP audit certificates for a residual pair. '
                          'Missing pair sides, audit exclusions, orientation-error changes, and snapshot timestamps are retained in report.json. '
                          'Longer runs can lose final-checkpoint validity; both gains and losses are shown.', '']
    lines += ['## Compute accounting', '', '![Recorded compute](costs.png)', '', '[Vector compute figure](costs.pdf)', '',
              'CPU seconds are measured processor consumption. Summed worker-wall seconds are not calendar duration. '
              'Native allowance is not whole-trial cost: SAT feedback, initial flippability, audits, and corpus generation are separate. '
              'The component below called “worker beyond native” includes initialization and any unclassified worker work; it is not a pure SAT-feedback timer.', '',
              '|Study|Native CPU s|Worker beyond native CPU s|Audit CPU s|Shared preparation CPU s|Fresh corpus generation CPU s|Combine validation CPU s|Search-worker wall s|Audit wall s|Preparation wall s|',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for study in studies:
        keys = ('native_cpu_seconds', 'worker_cpu_beyond_recorded_native', 'audit_cpu_seconds', 'preparation_cpu_seconds',
                'corpus_generation_child_cpu_seconds', 'corpus_combine_validation_child_cpu_seconds',
                'worker_wall_seconds', 'audit_wall_seconds', 'preparation_wall_seconds')
        lines.append('|'+ '|'.join([study['kind']]+[fmt(study['costs'][key]) for key in keys])+'|')
    lines += ['', 'Summary costs cover the summarized completed trials; fresh corpus generation includes its original validation work. '
              'Combined-corpus revalidation is separate; it is not added to the fresh generation timer. Historical source-generation sunk costs are not attributed to this batch. '
              'Combine-controller CPU and whole combine wall time are preserved separately in report.json. '
              'Shared preparation is counted once per study, not once per arm or budget. Unknown CPU measurements stay “not recorded”—wall time is never substituted. '
              'The machine-readable report includes per-arm costs and all persisted-attempt diagnostics.', '',
              '## Errors, interruptions, and incomplete work', '']
    allowance = total_known(study['costs']['registered_native_allowance_seconds'] for study in studies)
    if allowance is not None:
        position = lines.index('## Errors, interruptions, and incomplete work')
        lines[position:position] = [f'Registered native allowance: {allowance:,.0f} single-thread worker-seconds '
                                   f'({allowance/3600:.2f} worker-hours). At two fully occupied slots this alone corresponds to '
                                   f'{allowance/7200:.2f} elapsed hours; this is a scheduling estimate, not measured CPU or elapsed time, '
                                   'and excludes preparation, audits, generation, and save grace.', '']
    for study in studies:
        lines += [f"### {study['kind']}", '',
                  f"Summary complete: {study['complete']}; completed / registered trials: {fmt(study['completed_trials'])} / {fmt(study['registered_trials'])}.", '']
        attempts = study['attempts']
        if attempts and 'persisted_attempts' in attempts:
            lines += [f"Persisted attempts: {attempts['persisted_attempts']}; incomplete: {attempts['incomplete_attempts']}; "
                      f"repeated case/arm/budget attempts: {attempts['repeated_case_arm_budget_attempts']}; external interruptions: {attempts['external_interruptions']}; "
                      f"overhead watchdogs: {attempts['overhead_watchdogs']}; audit watchdogs: {attempts['audit_watchdogs']}; forced native kills: {attempts['forced_native_kills']}.", '',
                      'Statuses: `'+json.dumps(attempts['status_counts'], sort_keys=True)+'`.', '',
                      f"All persisted attempts recorded {fmt(attempts['recorded_worker_cpu_seconds_all_attempts'])} search-worker CPU seconds "
                      f"and {fmt(attempts['recorded_audit_cpu_seconds_all_attempts'])} audit CPU seconds. These totals may include attempts omitted from the completed-trial summary; do not add them to that summary again.", '']
        else:
            lines += ['Raw attempt accounting is unavailable; do not infer zero interruptions or overhead.', '']
    lines += ['Ordinary native-budget termination is expected, not an operational error. A failed or missing certificate is not an impossibility proof. '
              'Forced kills and interrupted/inflight attempts are retained separately; abrupt termination may leave unrecorded CPU time.', '',
              '## Protocol and reproducibility', '',
              'The19-point arms are upstream continuous, improved continuous, and improved split-budget target repair with a warm restart. '
              'That third arm changes the target, splits time, and restarts: it is a compound strategy, not an isolated SAT-feedback ablation. '
              'The four paper problems additionally isolate optional line and paired moves. Interpret each comparison using its frozen registration.', '']
    for study in studies:
        lines += [f"### {study['kind']} sources", '']
        for role, item in study['sources'].items():
            if item:
                lines.append('- '+link(item['path'], output, role)+f" — SHA256 `{item['sha256']}`")
        lines.append('')
    if machine:
        lines += ['Machine snapshot: '+link(machine['path'], output, 'hardware and runtime environment')+
                  f" — SHA256 `{machine['sha256']}`. This describes the recorded machine, not exclusive ownership of all its cores.", '']
    if control:
        lines += ['## Separate known positive control', '',
                  'One known realizable type, excluded from the diverse target corpus. These cold-start outcomes are a pipeline sanity check, '
                  'not additional benchmark targets or a representative solve-rate estimate.', '',
                  '|Arm|Valid final geometry|Native CPU s|Native wall s|Initial target errors|',
                  '|---|---|---:|---:|---:|']
        for row in control['arms']:
            lines.append('|'+ '|'.join([LABELS.get(row['arm'], row['arm']), str(row['valid_final']),
                         fmt(row['native_cpu_seconds']), fmt(row['native_wall_seconds']), fmt(row['orientation_violations'])])+'|')
        lines += ['', link(control['path'], output, 'Control source')+f" — SHA256 `{control['sha256']}`.", '']
    lines += ['[Machine-readable snapshot](report.json) preserves the source hashes, all normalized checkpoint metrics, pair counts, costs, and persisted errors. '
              'The PDF figures are vector graphics; PNGs are convenience previews.', '',
              'Rebuild into a fresh directory with:', '', '```sh',
              'direct/vendor/venv/bin/python benchmarks/scaling_report.py \\',
              f"  --nineteen-registration {studies[0]['sources']['registration']['path']} \\",
              f"  --paper-registration {studies[1]['sources']['registration']['path']} \\",
              '  --out NEW_REPORT_DIRECTORY'+(' --draft' if draft else ''), '```', '']
    return '\n'.join(lines)


def load_control(path):
    data = json.loads(path.read_text())
    arms = []
    for arm, row in data.get('arms', {}).items():
        search = row['search']
        audits = [a for a in row.get('audit', {}).get('audits', [])
                  if a.get('checkpoint') == search.get('final_checkpoint')]
        audit = audits[0] if len(audits) == 1 else None
        arms.append(dict(arm=arm, valid_final=audit.get('valid_geometry') if audit else None,
            orientation_violations=audit.get('orientation_violations') if audit else None,
            native_cpu_seconds=total_known(s.get('native_cpu_seconds') for s in search.get('stages', [])),
            native_wall_seconds=total_known(s.get('native_wall_seconds') for s in search.get('stages', []))))
    return dict(path=str(path.resolve()), sha256=sha(path), status=data.get('status'),
                excluded_from_prospective_corpus=data.get('excluded_from_prospective_corpus'), arms=arms)


def plots(studies, output, draft):
    # Avoid writing a font cache into the user's home or the frozen report inputs.
    with tempfile.TemporaryDirectory(prefix='pointsat-report-mpl-') as cache:
        previous = os.environ.get('MPLCONFIGDIR')
        os.environ['MPLCONFIGDIR'] = cache
        try:
            _plots(studies, output, draft)
        finally:
            if previous is None:
                os.environ.pop('MPLCONFIGDIR', None)
            else:
                os.environ['MPLCONFIGDIR'] = previous


def _plots(studies, output, draft):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({'pdf.fonttype': 42, 'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False})
    families = [family for study in studies for family in study['families']]
    figure, axes = plt.subplots(2, 5, figsize=(19, 7), squeeze=False)
    seen = []
    for column, family in enumerate(families):
        for arm in family['arms']:
            if arm not in seen:
                seen.append(arm)
            points = [(float(budget), group['arms'][arm]) for budget, group in family['budgets'].items()]
            color = COLORS.get(arm)
            for row_index, metric in ((0, 'valid_final'), (1, 'median_forbidden_in_GP')):
                valid = [(budget, record) for budget, record in points if record.get(metric) is not None]
                if not valid:
                    continue
                axis = axes[row_index, column]
                axis.plot([b for b, _ in valid], [r[metric] for _, r in valid], color=color, linewidth=1.2, linestyle=':')
                for budget, record in valid:
                    full = record.get('trials') == family['registered_targets']
                    axis.plot(budget, record[metric], marker='o', markersize=5, color=color,
                              markerfacecolor=color if full else 'white')
        axes[0, column].set_title(family['title'], fontsize=9)
        target = family['registered_targets']
        axes[0, column].set_ylim(-.4, (target if target is not None else 20)+.4)
        axes[1, column].set_yscale('symlog', linthresh=1)
        for axis in axes[:, column]:
            budgets = [float(key) for key in family['budgets']]
            axis.set_xticks(budgets)
            axis.set_xlabel('Native budget (s), fresh start')
            axis.grid(alpha=.2)
        axes[0, column].set_ylabel('Certified final checkpoints')
        axes[1, column].set_ylabel('Median forbidden count (GP only)')
    handles = [Line2D([0], [0], color=COLORS.get(arm), marker='o', linestyle=':', label=LABELS.get(arm, arm)) for arm in seen]
    figure.legend(handles=handles, loc='lower center', ncol=min(len(handles), 7), frameon=False)
    figure.suptitle(('DRAFT — ' if draft else '')+'Final-checkpoint scaling; small non-IID target corpus, one seed per target', fontsize=13)
    figure.tight_layout(rect=(0, .07, 1, .94))
    for suffix in ('pdf', 'png'):
        figure.savefig(output/f'checkpoints.{suffix}', dpi=170)
    plt.close(figure)
    figure, axes = plt.subplots(1, 2, figsize=(11, 5))
    cpu_fields = [('native_cpu_seconds', 'Native'), ('worker_cpu_beyond_recorded_native', 'Other/unclassified worker'),
                  ('audit_cpu_seconds', 'Audit'), ('preparation_cpu_seconds', 'Shared preparation'),
                  ('corpus_generation_child_cpu_seconds', 'Fresh corpus generation'),
                  ('corpus_combine_validation_child_cpu_seconds', 'Combine validation'),
                  ('corpus_combine_controller_cpu_seconds', 'Combine controller')]
    wall_fields = [('worker_wall_seconds', 'Search workers'), ('audit_wall_seconds', 'Audits'),
                   ('preparation_wall_seconds', 'Shared preparation'), ('corpus_generation_wall_seconds', 'Fresh corpus generation'),
                   ('corpus_combine_wall_seconds', 'Corpus combination')]
    for axis, fields, title in ((axes[0], cpu_fields, 'Recorded CPU'), (axes[1], wall_fields, 'Summed recorded worker wall (not elapsed)')):
        bottom = [0., 0.]
        for key, label in fields:
            values = [max(0, study['costs'].get(key) or 0)/3600 for study in studies]
            if any(values):
                axis.bar([0, 1], values, bottom=bottom, label=label)
                bottom = [x+y for x,y in zip(bottom,values)]
        axis.set_xticks([0,1], ['19-point', 'Four paper families'])
        axis.set_ylabel('Hours')
        axis.set_title(title)
        if axis.get_legend_handles_labels()[0]:
            axis.legend(fontsize=8)
        else:
            axis.text(.5, .5, 'No recorded cost components', ha='center', transform=axis.transAxes)
        axis.grid(axis='y', alpha=.2)
    figure.suptitle(('DRAFT — ' if draft else '')+'Known cost components only; missing components are not measured zeros')
    figure.tight_layout(rect=(0,0,1,.93))
    for suffix in ('pdf', 'png'):
        figure.savefig(output/f'costs.{suffix}', dpi=170)
    plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nineteen-registration', type=Path, required=True)
    parser.add_argument('--paper-registration', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--draft', action='store_true', help='allow missing/incomplete summaries; clearly label pending outcomes')
    parser.add_argument('--machine-info', type=Path, help='optional existing hardware/runtime JSON snapshot')
    parser.add_argument('--positive-control-result', type=Path, help='optional separate known-control result JSON, never pooled with study targets')
    args = parser.parse_args(argv)
    studies = [load_study(args.nineteen_registration, 'nineteen', args.draft),
               load_study(args.paper_registration, 'paper', args.draft)]
    from benchmarks.scaling_effects import analyze
    effects = analyze([args.nineteen_registration, args.paper_registration])
    machine = ({'path': str(args.machine_info.resolve()), 'sha256': sha(args.machine_info),
                'snapshot': json.loads(args.machine_info.read_text())} if args.machine_info else None)
    control = load_control(args.positive_control_result) if args.positive_control_result else None
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plots(studies, output, args.draft)
    (output/'README.md').write_text(markdown(studies, output, args.draft, effects, machine, control))
    from benchmarks.scaling_pdf import build_pdf
    pdf = build_pdf(studies, output, args.draft, effects, LABELS, TITLES, machine, control)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'draft': args.draft,
              'report_generator_sha256': sha(__file__), 'scaling_effects_sha256': sha(ROOT/'benchmarks/scaling_effects.py'),
              'studies': studies, 'within_target_budget_effects': effects, 'machine': machine, 'positive_control': control,
              'pdf': pdf, 'pdf_generator_sha256': sha(ROOT/'benchmarks/scaling_pdf.py'),
              'outputs': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}}
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'report_directory': str(output), 'draft': args.draft,
                      'complete': all(study['complete'] for study in studies)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
