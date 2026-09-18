"""Presentation-only PDF helper, usable beside a frozen anytime_report.py."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def tex(value):
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
                    '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
                    '→': r'$\to$', '—': '---', '–': '--'}
    return ''.join(replacements.get(character, character) for character in str(value))


def number(value):
    return '--' if value is None else str(value) if isinstance(value, int) else f'{value:.2f}'


def table(headers, rows, alignment):
    return (r'\begin{center}\small\begin{longtable}{'+alignment+'}\n'+r'\toprule'+'\n'+
        ' & '.join(tex(c) for c in headers)+r' \\'+'\n'+r'\midrule\endhead'+'\n'+
        '\n'.join(' & '.join(tex(c) for c in row)+r' \\' for row in rows)+'\n'+
        r'\bottomrule\end{longtable}\end{center}'+'\n')


def build_pdf(report, output, labels):
    if shutil.which('pdflatex') is None:
        raise RuntimeError('PDF reporting requires the existing pdflatex installation')
    families = list(report['families'].values())
    milestones = sorted({float(t) for family in families for t in family['milestones']})
    sections = [r'\documentclass[10pt,a4paper]{article}', r'\usepackage[margin=18mm]{geometry}',
        r'\usepackage[T1]{fontenc}', r'\usepackage{lmodern,booktabs,longtable,graphicx,pdflscape,hyperref}',
        r'\hypersetup{colorlinks=true,urlcolor=blue}', r'\setlength{\parindent}{0pt}',
        r'\setlength{\parskip}{5pt}', r'\setlength{\emergencystretch}{2em}', r'\begin{document}',
        r'\begin{center}{\Large\bfseries Equal-total-time PointSAT study'+(' --- DRAFT' if report['draft'] else '')+r'}\end{center}',
        r'\section*{Method and endpoint}',
        'Each registered SAT target and native seed is compared under a single total-wall-time allowance. '
        'Runtime preparation and imports, flippability, native search, SAT feedback, and online verification all share the same clock. '
        'Initial SAT target sampling is outside this clock and reported separately as corpus construction. '
        'No state is shared between treatment arms or targets.',
        'This is a cold realization-workflow comparison, not the literal untouched PointSAT driver or steady-state batch throughput. '
        'The original arm uses the frozen original flippability implementation and untouched native solver. Updated arms use the revised checker, '
        'persistent only within one trajectory. Conversion, the required compressed-variable adapter, storage and geometric acceptance are common. '
        'Original-to-updated continuous changes both preparation and the native package; updated plain/line/pair comparisons isolate native flags. '
        'Cold preparation may dominate short allowances, especially for 19 points.',
        'The primary event is the first accepted solution returned by completed online verification before the deadline. '
        'We use logged verification-completion timestamps tied to immutable checked certificates, not estimated native discovery times. '
        'A posthoc-valid coordinate file cannot create or backdate an online success. '
        'For 19 points, numeric geometric validity is distinct from exact threefold-symmetry reconstruction; '
        'the latter is a secondary posthoc claim. Actual x-direction caps are checked for the cap family.',
        'Continuous arms and segmented arms have intentionally different candidate-return opportunities. Retry-only controls '
        'use the segmented schedule without SAT feedback. Their comparison measures the additional feedback workflow under '
        'the same total allowance, not a fixed-work native-kernel speedup.',
        'All registered targets remain in empirical verified-return denominators. Failures have no success event and retain '
        'censor times. This is a small, deliberately diverse, non-IID corpus with one native seed per target; no universal '
        'success rate or speed multiplier is established. The curves are actual step functions, not interpolated time-to-discovery estimates.',
        r'\textbf{Protocol correction.} Earlier native-only-budget runs remain separate partial diagnostics. '
        'Their outcomes, costs, or native seconds are not converted into equal-total-time observations. '
        'The same fixed targets are reused after those diagnostics; this is not an unseen holdout evaluation.']
    if report['draft']:
        sections.append(r'\textbf{Incomplete snapshot.} Pending, early-censored and inflight trajectories are explicitly retained. '
                        'Unobserved exposure is not manufactured into a completed failure. Current success counts are lower bounds; '
                        'matched comparisons with incomplete exposure remain provisional.')
    sections += [r'\section*{Verified returns by total wall time}',
        'Cells show verified returns / all registered targets. The parenthetical U count identifies '
        'targets neither observed through that milestone nor already solved; those targets are not removed from the denominator.']
    rows = []
    for family in families:
        for arm, data in family['arms'].items():
            cells = []
            for seconds in milestones:
                record = data['milestones'].get(str(float(seconds)))
                cells.append('--' if record is None else f"{record['solved']}/{record['registered_targets']} (U{record['unobserved_targets']})")
            rows.append([family['family'], labels.get(arm, arm)]+cells)
    sections.append(table(['Problem', 'Arm']+[f'{seconds:g} s' for seconds in milestones], rows, 'll'+'r'*len(milestones)))
    sections += [r'\clearpage\begin{landscape}', r'\section*{Actual first-verified-return curves}',
        r'\begin{center}\includegraphics[width=\linewidth,height=100mm,keepaspectratio]{verified-returns.pdf}\end{center}',
        'Every event occurs at its recorded verification-completed elapsed time. Hollow milestone markers indicate incomplete exposure. '
        'Failures remain censored rather than being assigned invented success times. Coincident arm values can overlap. '
        'This is the empirical fraction of all registered targets, not a Kaplan--Meier extrapolation.',
        r'\end{landscape}\clearpage', r'\section*{Matched retry-only versus SAT-feedback outcomes}',
        'All target identities are paired. A first-only result favors retry-only; a second-only result favors feedback. '
        'Both and neither are retained; provisional pairs have incomplete exposure. All other arm pairs, including upstream comparisons, are in README.md/report.json.']
    rows = []
    for family in families:
        for pair, changes in family['pairs'].items():
            a, b = pair.split('__')
            if not a.endswith('_retry') or not b.endswith('_feedback'):
                continue
            for seconds, values in changes.items():
                rows.append([family['family'], f'{float(seconds):g}']+
                    [str(values[key]) for key in ('first_only', 'second_only', 'both', 'neither', 'provisional_pairs')])
    sections.append(table(['Problem', 'Wall s', 'Retry only', 'Feedback only', 'Both', 'Neither', 'Provisional'], rows, 'lrrrrrr'))
    sections += [r'\section*{Compute accounting}',
        'All recorded attempts contribute, including failed and interrupted work. CPU seconds measure processor consumption; '
        'wall is never substituted for missing CPU. Parent totals overlap component costs and must not be added to them. '
        'Summed worker wall is not elapsed calendar duration. Posthoc audit costs are outside the primary clock. '
        'No cost average is conditioned only on successful trials.']
    rows = []
    for family in families:
        for arm, data in family['arms'].items():
            costs = data['all_attempt_costs']
            rows.append([family['family'], labels.get(arm, arm)]+[
                number(costs['components'][kind]['cpu_seconds']) for kind in ('preparation', 'native', 'feedback', 'online_audit')])
    sections.append(table(['Problem', 'Arm', 'Prep CPU s', 'Native CPU s', 'Feedback CPU s', 'Online check CPU s'], rows, 'llrrrr'))
    rows = []
    for index, study in enumerate(report['studies'], 1):
        costs = study['ledger']['all_attempt_costs']
        rows.append([index, costs['attempts'], number(costs['parent_cpu_seconds']), number(costs['parent_wall_seconds']),
                     number(costs['posthoc_cpu_seconds']), number(costs['posthoc_wall_seconds'])])
    sections.append(table(['Study', 'Attempts', 'Parent CPU s', 'Parent wall s', 'Posthoc CPU s', 'Posthoc wall s'], rows, 'rrrrrr'))
    sections += [r'\section*{Censoring, errors and provenance}']
    for study in report['studies']:
        ledger = study['ledger']
        sections.append(tex(f"Registered trajectories: {ledger['registered_trajectories']}; completed: {ledger['completed_selected_trajectories']}; "
            f"persisted attempts: {ledger['persisted_attempts']}; incomplete: {ledger['incomplete_attempts']}; repeat attempts: {ledger['repeated_attempts']}; "
            f"late verification events excluded: {ledger['late_verified_events']}.")+' '+tex('Statuses: '+json.dumps(ledger['status_counts'], sort_keys=True))+'.')
        costs = ledger['all_attempt_costs']
        sections.append(tex(f"Online deadline-exceeded checks: {ledger['online_deadline_exceeded_checks']}; online checker errors: {ledger['online_check_errors']}; "
            f"search CPU lower-bound attempts: {costs['cpu_lower_bound_attempts']}; posthoc CPU lower-bound attempts: {costs['posthoc_cpu_lower_bound_attempts']}.")+
            ' Abruptly killed descendants may leave unrecorded CPU, so affected totals are lower bounds rather than complete exact measurements.')
        for corpus in study['corpus']:
            sections.append(tex('Corpus strata: '+json.dumps(corpus['data'].get('strata', {}), sort_keys=True))+'. '
                'Fresh SAT generation and reused historical/proof-filtered targets are distinct strata. Historical selection '
                'used initial SAT assignments in fixed source order, not coordinate or feedback outcomes. The known positive-control '
                'canonical type is excluded. Generation-only cuts do not enter the benchmark original CNF.')
            data = corpus['data']
            sections.append('Outside-clock corpus construction: '+tex(number(data.get('generation_child_cpu_seconds')))+
                ' fresh-generation CPU seconds; '+tex(number(data.get('combine_validation_child_cpu_seconds')))+
                ' combined-corpus revalidation CPU seconds. These are separate timers; historical generation sunk costs are not attributed to this batch.')
        registration = study['sources']['registration']
        sections.append(r'{\small Registration: \url{'+registration['path']+'}}'+r'\\'+
                        r'{\footnotesize\texttt{'+registration['sha256']+'}}')
    sections.append('An operational error or a deadline without a returned solution is not an impossibility proof. '
                    'The JSON retains each censor timestamp, certificate hash, all arm pairs, component timing coverage, and every recorded error. '
                    'A duplicate completed case/arm is an integrity failure rather than an opportunity to pick the better run.')
    if report.get('positive_control'):
        sections += [r'\section*{Separate earlier positive control}',
            'The supplied control file belongs to a known realizable target excluded from the main diverse corpus. '
            'It is an earlier pipeline sanity check, not an additional equal-total-time trial. Its native timings '
            'are not first-verified-return times and are not pooled into these curves.',
            r'{\small\url{'+report['positive_control']['path']+'}}']
    if report.get('machine'):
        sections += ['Machine/environment snapshot: '+r'{\small\url{'+report['machine']['path']+'}}'+'. '
            'The recorded environment is virtualized; its reported CPU model and visible logical topology do not establish dedicated physical cores. '
            'The study has a two-worker budget; measured CPU and wall costs are retained separately.']
    sections += ['This report was generated read-only from the new equal-total-time registration and committed SQLite records. '
                'No native search or geometry audit runs during reporting. README.md and report.json accompany this PDF, '
                'together with its LaTeX source and vector/PNG figure. All earlier reports are preserved.', r'\end{document}', '']
    source = output/'anytime-report.tex'
    source.write_text('\n\n'.join(sections))
    deadline = time.monotonic()+45
    with tempfile.TemporaryDirectory(prefix='pointsat-anytime-pdf-') as directory:
        for _ in range(2):
            completed = subprocess.run(['pdflatex', '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error',
                '-output-directory', directory, str(source)], cwd=output, text=True, capture_output=True,
                timeout=max(.001, deadline-time.monotonic()))
            if completed.returncode:
                raise RuntimeError('PDF compilation failed: '+completed.stdout[-5000:])
        shutil.copy2(Path(directory)/'anytime-report.pdf', output/'anytime-report.pdf')
        log = (Path(directory)/'anytime-report.log').read_text(errors='replace')
    return dict(engine='pdflatex -no-shell-escape, two passes within one45-second wall cap',
                layout_warnings=[line for line in log.splitlines() if 'Overfull' in line or 'Underfull' in line])
