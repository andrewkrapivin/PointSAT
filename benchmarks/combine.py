#!/usr/bin/env python3
"""Combine disjoint, unchanged-policy cohorts; retain their separate outcomes."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from report import calculate, load

NAMES = [('mixed23', '23: no convex 7 / no empty 6'),
         ('holes29', '29: no empty 6'), ('gons32', '32: no convex 7'),
         ('caps26', '26: no convex 7 / no 5-cap')]


def figures(rows, prefix):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(9, 7.8))
    index = {(r['phase'], r['job']['case']['id'], r['job']['seed'], r['job']['arm']): r
             for r in rows if not r['externally_interrupted']}
    for ax, (family, title) in zip(axes.flat, NAMES):
        pairs = []
        for (phase, case, seed, arm), a in index.items():
            b = index.get((phase, case, seed, 'core_feedback'))
            if arm != 'warm_retry' or b is None or a['job']['case']['problem'] != family:
                continue
            x, y = (r['posthoc']['minimum_forbidden_count'] for r in (a, b))
            if x is not None and y is not None:
                pairs.append((phase, x, y))
        maximum = max([max(x, y) for _, x, y in pairs]+[1])
        extent = math.log1p(maximum)*1.08
        ax.plot([0, extent], [0, extent], '--', color='#999999', linewidth=1)
        for phase, marker in [('pilot', 'o'), ('extension', '^')]:
            selected = [(x, y) for p, x, y in pairs if p == phase]
            ax.scatter([math.log1p(x) for x, y in selected],
                       [math.log1p(y) for x, y in selected],
                       c=['#147c68' if y < x else '#b34c34' if y > x else '#4c6584'
                          for x, y in selected], marker=marker, s=46,
                       alpha=.8, edgecolors='white', linewidths=.7, label=phase)
        ticks = [v for v in (0, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000) if v <= maximum]
        ax.set_xticks([math.log1p(v) for v in ticks], labels=ticks)
        ax.set_yticks([math.log1p(v) for v in ticks], labels=ticks)
        ax.set_xlim(-extent*.025, extent); ax.set_ylim(-extent*.025, extent)
        ax.set_aspect('equal'); ax.tick_params(labelsize=8)
        ax.set_title(f'{title} ({len(pairs)} pairs)', fontsize=11)
        ax.set_xlabel('Warm-retry forbidden count (log1p)', fontsize=9)
        ax.set_ylabel('Feedback forbidden count (log1p)', fontsize=9)
        ax.grid(alpha=.12)
    axes.flat[0].legend(fontsize=8, loc='upper left')
    fig.suptitle('Matched 60-second budgets: exact geometry at saved checkpoints', fontsize=13)
    fig.text(.5, .018, 'Below diagonal favors feedback; zero is a solution. Residual counts are diagnostic, not proof of general superiority.',
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .045, 1, .96))
    for extension in ('svg', 'pdf'):
        fig.savefig(str(prefix)+'_paired_geometry.'+extension)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pilot', default='benchmarks/pilot_20260906/results.sqlite')
    p.add_argument('--extension', default='benchmarks/extension_20260906/results.sqlite')
    p.add_argument('--output', default='benchmarks/combined_20260906.json')
    args = p.parse_args()
    rows, jobs, cohorts, registrations = [], [], {}, {}
    prior = None
    for phase, database in [('pilot', Path(args.pilot)), ('extension', Path(args.extension))]:
        registration = database.parent/'registration.json'
        config = json.loads(registration.read_text())
        current = load(database)
        for row in current:
            row['phase'] = phase
        if prior is not None:
            for key in ('budget_seconds', 'native_chunk_seconds', 'feedback_seconds',
                        'native_binary', 'binary_sha256', 'frozen_sha256', 'seeds',
                        'caps_ordered_x', 'initial_flippability', 'feedback_flippability', 'feedback_policy'):
                assert prior[key] == config[key], ('Policy differs', key)
            assert not {c['orientation_sha256'] for c in prior['cases']}.intersection(
                       c['orientation_sha256'] for c in config['cases'])
            assert config['parent_registration_sha256'] == hashlib.sha256(
                Path(args.pilot).with_name('registration.json').read_bytes()).hexdigest()
        prior = config
        cohorts[phase] = calculate(current, config)
        registrations[phase] = str(registration)
        rows.extend(current); jobs.extend(config['jobs'])
    combined = calculate(rows, dict(jobs=jobs, budget_seconds=prior['budget_seconds']))
    combined.update(cohorts=cohorts, registrations=registrations,
                    comparison='Same frozen binary, helpers, policy, seeds, and total budget; disjoint target models.',
                    caveat='Reused SAT-generated targets: SAT generation excluded, and not a new unseen corpus. '
                           'Extension registered after pilot but with unchanged policy. Small clustered sample; no universal superiority claim.')
    output = Path(args.output)
    output.write_text(json.dumps(combined, indent=2)+'\n')
    lines = ['# Matched feedback benchmark: pilot and prospective extension', '',
             f'{combined["completed_trials"]}/{combined["registered_trials"]} trials complete. '
             'Each arm receives a 60-second whole-trial wall budget, including imports, CNF setup, '
             'initial flippability, Localizer, feedback and operational checks. Both arms use frozen v6 '
             'with the same target and seed; caps26 enforces ordered x in both. Independent post-hoc '
             'exact audits are separately timed and never steer the search.', '',
             'The pilot selected four unique target models per family. The prospectively registered '
             'extension selected the next four, changing no policy or binary. Each target has two '
             'native seeds. These are reused SAT-generated models, not freshly held-out models; SAT '
             'generation is outside this realization-only benchmark.', '',
             '## Exact geometric success, paired by target and native seed', '',
             '| Cohort | Family | Models | Pairs | Retry only | Feedback only | Both | Neither |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for phase, report in list(cohorts.items())+[('combined', combined)]:
        for family, _ in NAMES:
            g = report['families'][family]
            lines.append(f'| {phase} | {family} | {g["unique_target_models"]} | {g["paired_trials"]} | '
                         f'{g["retry_only_successes"]} | {g["feedback_only_successes"]} | '
                         f'{g["both_successes"]} | {g["neither_success"]} |')
    lines += ['', '## Combined exposure and secondary residual', '',
              '| Family | Arm | Trials | Successes | Solved target models | Shared-initial successes | Mean wall / CPU / native CPU (s) | Median forbidden count |',
              '| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |']
    for family, _ in NAMES:
        for arm, a in combined['families'][family]['arms'].items():
            if not a['trials']:
                continue
            lines.append(f'| {family} | {arm} | {a["trials"]} | {a["valid_geometry_trials"]} | '
                         f'{a["valid_geometry_target_clusters"]} | {a["successes_in_shared_initial_stage"]} | {a["mean_wall_seconds"]:.2f} / '
                         f'{a["mean_cpu_seconds"]:.2f} / {a["mean_native_cpu_seconds"]:.2f} | '
                         f'{a["median_best_forbidden_count"]} |')
    lines += ['', '## Model-level outcomes (either native seed may succeed)', '',
              '| Family | Fully evaluated models | Retry only | Feedback only | Both | Neither |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    for family,_ in NAMES:
        m=combined['families'][family]['target_cluster_outcomes']
        lines.append(f'| {family} | {m["complete_models"]} | {m["retry_only"]} | {m["feedback_only"]} | {m["both"]} | {m["neither"]} |')
    t=combined['totals']
    lines+=['','## Resource accounting and exit audit','',
            f'Parent-observed search CPU: {t["parent_observed_search_cpu_seconds"]:.6f} seconds '
            f'({t["parent_observed_search_cpu_seconds"]/3600:.4f} core-hours); native-only CPU: '
            f'{t["native_cpu_seconds"]:.6f} seconds. Sum of worker wall time: '
            f'{t["search_worker_wall_seconds"]:.6f} seconds (not elapsed time with three concurrent workers). '
            f'Independent post-hoc auditing took {t["posthoc_audit_wall_seconds"]:.3f} summed wall seconds, '
            'separately from the search budget; its CPU was not measured in this search-CPU total.', '',
            f'Budget-signalled worker exits after saved checkpoints: {t["budget_signal_exit_trials"]}; '
            f'unexpected worker exits: {t["unexpected_nonzero_exit_trials"]}; '
            f'nonzero native-stage exits: {t["native_nonzero_exit_stages"]}; '
            f'operational inspection errors: {t["operational_inspection_errors"]}; '
            f'independent audit errors: {t["posthoc_audit_errors"]}; '
            f'external interruptions: {t["external_interruptions"]}. '
            f'The raw CPU-accounting flag is set on {t["cpu_accounting_flagged_trials"]} signal-killed worker(s): '
            'parent-observed CPU may omit an unreaped descendant, so the total is labelled observed CPU, not an '
            'unqualified all-descendant CPU measurement. Raw exits and checkpoint counts are retained in JSON.', '',
            'In the pilot, caps26 trial31 exited on watchdog SIGINT (-2) at 60.034494 seconds, after recording '
            'four native stages and saving all four audited checkpoints. Its nonzero_exit_trials=1 is '
            'a budget-censored shutdown, not an unexplained solver failure. Extension caps26 trial20 '
            'likewise exited on SIGINT at 60.042388 seconds with all four checkpoints saved. All four '
            'recorded native subprocesses returned zero in each flagged case; there is no evidence '
            'that native CPU was actually omitted by the conservative accounting flag.']
    lines += ['', 'Success in the shared initial stage precedes either strategy and is not evidence for '
              'feedback. A failure here is a budget-censored search, not a nonrealizability proof. '
              'Saved-checkpoint discovery times are upper bounds. Two seeds from one orientation model '
              'are not independent target clusters. With few events, the paired raw counts support '
              'only a limited conclusion; no broad success-rate or speedup claim is justified.', '',
              'Residuals count actual forbidden polygons, not errors against the changing feedback target. '
              'Only zero certifies success; compare nonzero counts within a family. Geometry checks include '
              'general position and the geometric cap condition; full-CNF acceptance alone is insufficient.', '',
              'The fixed budgets deliberately include feedback overhead, so native search work need not '
              'be equal. This is not the earlier evaluator fixed-work speed test or the optional-move '
              'default/line/pair benchmark. Completed trials, audit errors, watchdog censoring, and CPU '
              'accounting flags remain available in the separate immutable SQLite records.', '',
              f'Machine-readable output: [{output.name}]({output.name}). '
              f'Plot: [{output.stem}_paired_geometry.pdf]({output.stem}_paired_geometry.pdf).', '',
              '```sh', f'python3 benchmarks/combine.py --pilot {args.pilot} --extension {args.extension} --output {output}', '```']
    output.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    figures(rows, output.with_suffix(''))
    print(json.dumps({'output': str(output), 'completed': len(rows), 'registered': len(jobs)}))


if __name__ == '__main__':
    main()
