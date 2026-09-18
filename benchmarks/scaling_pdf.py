"""Concise self-contained PDF from already aggregated scaling records only."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def tex(value):
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
                    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
                    '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
                    '→': r'$\to$', '—': '---', '–': '--', '×': r'$\times$'}
    return ''.join(replacements.get(c, c) for c in str(value))


def number(value):
    if value is None:
        return '--'
    return str(value) if isinstance(value, int) else f'{value:.2f}'


def table(headers, rows, align=None):
    align = align or 'l'+'r'*(len(headers)-1)
    header = ' & '.join(tex(c) for c in headers)+r' \\'
    return (r'\begin{center}\small\begin{longtable}{'+align+'}\n'+r'\toprule'+ '\n'+header+'\n'+
            r'\midrule\endhead'+'\n'+ '\n'.join(' & '.join(tex(c) for c in row)+r' \\' for row in rows)+
            '\n'+r'\bottomrule\end{longtable}\end{center}'+'\n')


def build_pdf(studies, output, draft, effects, labels, titles, machine=None, control=None):
    """LaTeX is local and bounded; no shell escape, network, SAT, or auditing."""
    if shutil.which('pdflatex') is None:
        raise RuntimeError('Self-contained PDF requires pdflatex (already used by reports/build_report.py)')
    title = 'PointSAT checkpoint scaling study'+(' --- DRAFT' if draft else '')
    budgets = sorted({float(b) for study in studies for family in study['families'] for b in family['budgets']})
    changes = list(zip(budgets, budgets[1:]))[:2]
    sections = [r'\documentclass[10pt,a4paper]{article}',
        r'\usepackage[margin=18mm]{geometry}', r'\usepackage[T1]{fontenc}',
        r'\usepackage{lmodern,booktabs,longtable,graphicx,pdflscape,hyperref}',
        r'\hypersetup{colorlinks=true,urlcolor=blue}', r'\setlength{\parindent}{0pt}',
        r'\setlength{\parskip}{5pt}', r'\setlength{\emergencystretch}{2em}', r'\begin{document}',
        r'\begin{center}{\Large\bfseries '+tex(title)+r'}\end{center}',
        r'\section*{Protocol and interpretation}',
        'Five geometric families; the registered number of diverse SAT-only targets per family; one registered native seed per target. '
        'Every arm/budget starts afresh from the same frozen target and seed. Native allowances are '+tex(', '.join(f'{b:g}' for b in budgets))+' seconds, '
        'not whole-trial wall or CPU budgets. This is a small, deliberately selected, non-IID corpus, not a population success-rate estimate.',
        'The primary endpoint is exact geometric validity of the final saved checkpoint. Any saved valid point set is secondary. '
        'For 19 points, printed-coordinate geometric validity is distinct from exact threefold-symmetry reconstruction and from realizing the initial SAT target. '
        'For the cap problem, caps are counted in the actual coordinate x direction.',
        'The 19-point arms compare upstream continuous search, v4 continuous search, and v4 split-budget target repair plus warm restart. '
        'The last is a compound strategy, not an isolated feedback effect. Paper-family arms use upstream, v6 plain, v6 line, v6 line+pair, and v6 feedback. '
        'No time of actual first success is observed or interpolated. Solve-rate differences are not fixed-work kernel speedups.']
    if draft:
        sections.append(r'\textbf{Incomplete snapshot.} Pending targets are not failures; hollow plot points are incomplete. '
                        'Missing measurements remain unknown. SQL budget-effects and saved-summary snapshots can have slightly different cutoff times while workers run.')
    for study in studies:
        corpus = study.get('corpus') or {}
        if corpus.get('strata'):
            strata = ', '.join(f'{count} {name.replace("_", " ")}' for name, count in corpus['strata'].items())
            sections.append(tex(f"The {study['kind']} corpus contains {strata}. ")+
                'All committed fresh targets are considered first, followed by historical initial SAT assignments in frozen source/line order. '
                'No coordinate-success or feedback-outcome selection is used. Historical proof-filtered targets are a reused stratum, '
                'not all-fresh generation. The known positive-control canonical type is excluded; retained targets satisfy '
                'the original CNF and the registered canonical/distance checks. Benchmark checks use the original CNF, not the extra generation cuts.')
    sections += [r'\section*{Final-checkpoint success counts}',
                 'Each cell is valid final outputs / completed trials. The planned count is listed per problem/arm. Missing entries are not measured zeroes.']
    rows = []
    for study in studies:
        for family in study['families']:
            for arm in family['arms']:
                cells = []
                for budget in budgets:
                    record = family['budgets'].get(str(budget), {}).get('arms', {}).get(arm, {})
                    cells.append(number(record.get('valid_final'))+' / '+number(record.get('trials')))
                rows.append([family['family'], labels.get(arm, arm), number(family['registered_targets'])]+cells)
    sections.append(table(['Problem', 'Arm', 'Planned']+[f'{b:g} s' for b in budgets], rows, 'll'+'r'*(1+len(budgets))))
    sections += [r'\clearpage\begin{landscape}', r'\section*{Checkpoint scaling and actual residuals}',
                 r'\includegraphics[width=\linewidth]{checkpoints.pdf}',
                 'Top: valid final checkpoints. Bottom: median actual forbidden polygon/cap count among general-position (GP) finals only. '
                 'GP denominators and target-orientation errors are in README.md and report.json. Scales differ between families. '
                 'Dotted connections describe independent budget starts, not continuous survival curves. Coincident arm values can overlap.',
                 r'\end{landscape}\clearpage', r'\section*{Paired effect of more native time}',
                 'Gains/losses compare validity of the same target and seed. The residual delta is higher-budget minus lower-budget '
                 'forbidden count, then a median across paired GP targets. It is not the difference of group medians. '
                 'Both endpoints need a hash/content-checked stored audit certificate for inclusion in residual changes. '
                 'Negative deltas are improvements; longer runs can lose final-checkpoint validity.']
    rows = []
    for family, family_data in effects.get('families', {}).items():
        for arm, arm_data in family_data['arms'].items():
            cells = []
            for low, high in changes:
                key = str(float(low))+'__'+str(float(high))
                change = arm_data['comparisons'].get(key, {})
                validity, forbidden = change.get('validity', {}), change.get('forbidden', {})
                cells.extend([number(change.get('completed_pairs')),
                    number(validity.get('gains'))+'/'+number(validity.get('losses')),
                    number(forbidden.get('median_delta'))+' ('+number(forbidden.get('paired_GP'))+')'])
            rows.append([family, labels.get(arm, arm)]+cells)
    headers = ['Problem', 'Arm']
    for low, high in changes:
        headers.extend(['Pairs', f'{low:g}→{high:g} G/L', 'Delta (GP)'])
    sections.append(table(headers, rows, 'll'+'r'*(3*len(changes))))
    sections.append('All registered budget comparisons, fewer/same/more counts, missing pair sides, non-GP/audit exclusions, '
                    'and secondary orientation-error changes are preserved in report.json and the Markdown report.')
    sections += [r'\clearpage', r'\section*{Compute accounting}',
                 'CPU seconds measure processor consumption; summed worker-wall seconds are not elapsed calendar time. '
                 'Native allowance excludes SAT feedback, initial flippability/preparation, and exact audits. '
                 'Worker CPU beyond native includes initialization and unclassified work; it is not a pure SAT timer.']
    rows = []
    for study in studies:
        costs = study['costs']
        for label, cpu, wall in (
            ('Native', 'native_cpu_seconds', 'native_wall_seconds'),
            ('Other/unclassified search worker', 'worker_cpu_beyond_recorded_native', None),
            ('Exact audits', 'audit_cpu_seconds', 'audit_wall_seconds'),
            ('Shared preparation', 'preparation_cpu_seconds', 'preparation_wall_seconds'),
            ('Fresh corpus generation', 'corpus_generation_child_cpu_seconds', 'corpus_generation_wall_seconds'),
            ('Combined-corpus validation', 'corpus_combine_validation_child_cpu_seconds', 'corpus_combine_wall_seconds'),
            ('Combine controller', 'corpus_combine_controller_cpu_seconds', None)):
            rows.append([study['kind'], label, number(costs.get(cpu)), number(costs.get(wall)) if wall else '--'])
    sections.append(table(['Study', 'Component', 'CPU seconds', 'Worker wall seconds'], rows, 'llrr'))
    sections += ['Shared preparation and corpus costs are counted once, not per arm/budget. Fresh-generation CPU and combined-corpus '
                 'revalidation are separate. Historical generation sunk costs are not attributed to this batch. Combine wall includes its controller; '
                 'do not add it again to child wall. Unknown CPU stays unknown; wall time is never substituted. '
                 'Completed-summary costs and all-attempt totals are separate views and must not be added together.',
                 r'\includegraphics[width=\linewidth]{costs.pdf}',
                 r'\section*{Errors and censoring}']
    for study in studies:
        attempts = study.get('attempts') or {}
        sections.append(tex(f"{study['kind']}: summary complete={study['complete']}; ")+tex(', '.join(
            f"{key.replace('_', ' ')}={attempts.get(key, 'not recorded')}" for key in (
                'persisted_attempts', 'incomplete_attempts', 'external_interruptions',
                'overhead_watchdogs', 'audit_watchdogs', 'forced_native_kills')))+'.')
        sections.append(tex('Recorded statuses: '+json.dumps(attempts.get('status_counts', {}), sort_keys=True))+'.')
    sections.append('Ordinary native-budget termination is expected, not an operational error. Failed/missing certificates are not impossibility proofs. '
                    'Interrupted/inflight work remains separately censored; abrupt termination may leave unrecorded CPU. '
                    'The machine-readable ledger retains retries, errors, and cost-field coverage.')
    sections += [r'\section*{Separate positive control}']
    if control:
        rows = [[labels.get(row['arm'], row['arm']), str(row['valid_final']),
                 number(row['native_cpu_seconds']), number(row['native_wall_seconds']),
                 number(row['orientation_violations'])] for row in control['arms']]
        sections.append('This is one known realizable type, excluded from the diverse target corpus. Cold-start results are a pipeline sanity check, '
                        'not a representative solve-rate estimate or part of the diverse-target denominators.')
        sections.append(table(['Arm', 'Geometry valid', 'Native CPU s', 'Native wall s', 'Target errors'], rows, 'lrrrr'))
    else:
        sections.append('The known positive-control canonical type is excluded from the prospective corpus. '
                        'No separate control-result file was supplied to this report; no control success or timing is inferred.')
    sections += [r'\section*{Provenance and reproduction}',
                 'This PDF, README.md, report.json, scaling-report.tex, and the vector/PNG figures form one read-only report snapshot. '
                 'The JSON records full input/output hashes, frozen corpus provenance, raw-attempt diagnostics, and paired effects. '
                 'No searches or geometry audits are run during report generation. Earlier reports remain untouched.']
    for study in studies:
        sections.append(tex(study['kind']+' registration: ')+r'\url{'+study['sources']['registration']['path']+'}'+r'\\'+
                        r'{\footnotesize\texttt{'+study['sources']['registration']['sha256']+'}}')
    if machine:
        sections.append('Machine/environment snapshot: '+r'{\small\url{'+machine['path']+'}}'+'. '
                        'This does not imply exclusive ownership of every machine core.')
    if control:
        sections.append('Positive-control source: '+r'{\small\url{'+control['path']+'}}')
    sections += [r'\end{document}', '']
    source = output/'scaling-report.tex'
    source.write_text('\n\n'.join(sections))
    with tempfile.TemporaryDirectory(prefix='pointsat-scaling-pdf-') as temporary:
        deadline = time.monotonic()+45
        # Longtable records column widths in the first pass; the second pass
        # aligns repeated headers and body cells. Both share one wall cap.
        for _ in range(2):
            result = subprocess.run(['pdflatex', '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error',
                                     '-output-directory', temporary, str(source)], cwd=output,
                                    text=True, capture_output=True, timeout=max(.001, deadline-time.monotonic()))
            if result.returncode:
                raise RuntimeError('PDF compilation failed: '+result.stdout[-5000:]+result.stderr[-1000:])
        shutil.copy2(Path(temporary)/'scaling-report.pdf', output/'scaling-report.pdf')
        # Preserve nonfatal layout diagnostics in machine-readable provenance.
        log = (Path(temporary)/'scaling-report.log').read_text(errors='replace')
    return {'engine': 'pdflatex -no-shell-escape',
            'layout_warnings': [line for line in log.splitlines() if 'Overfull' in line or 'Underfull' in line]}
