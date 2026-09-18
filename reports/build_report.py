"""Build the human report from checked-in experiment records; never runs searches."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pointsat.geometry import describe, hull, read_points


def tex(value):
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
               '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(mapping.get(c, c) for c in str(value))


def load(path):
    return json.loads((ROOT/path).read_text())


def diagram(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    paths = [
        ('Paper: original', 'direct/seeds/paper23.pts'),
        ('Paper: experimental v2', 'optimizer/results/refinement600s-20260906/paper23-v2/points.pts'),
        ('Independent witness: v2 compaction', 'optimizer/results/refinement600s-20260906/feedback23-sample3-preserve-layers/points.pts'),
        ('A different layer-size class', 'optimizer/results/refinement600s-20260906/control-margin23-sample6-preserve-layers/points.pts'),
        ('Layer-changing compaction', 'optimizer/results/paired120s-20260906/archive23-sample7-new/points.pts'),
        ('New 29-point realization', 'benchmarks/success29/trial19/normalized.pts')]
    colors = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#D55E00', '#56B4E9', '#777777']
    fig, axes = plt.subplots(2, 3, figsize=(11, 7.4), layout='constrained')
    for ax, (title, filename) in zip(axes.flat, paths):
        if not (ROOT/filename).exists():
            ax.axis('off')
            continue
        points = read_points(ROOT/filename)
        info = describe(points)
        remaining, depth = set(range(len(points))), 0
        while remaining:
            outer = hull(points, remaining)
            color = colors[depth % len(colors)]
            if len(outer) >= 3:
                cycle = outer+[outer[0]]
                ax.plot([points[i][0] for i in cycle], [points[i][1] for i in cycle], color=color, lw=.8, alpha=.65)
            ax.scatter([points[i][0] for i in outer], [points[i][1] for i in outer], c=color, s=14, zorder=3)
            remaining.difference_update(outer)
            depth += 1
        ax.set_title(title+'\n'+f"{info['width']} × {info['height']}; layers "+','.join(map(str, info['hull_layers'])), fontsize=9)
        ax.set_aspect('equal', adjustable='box')
        ax.tick_params(labelsize=7)
        ax.spines[['top', 'right']].set_visible(False)
    fig.savefig(output/'configurations.pdf')
    fig.savefig(output/'configurations.png', dpi=150)
    plt.close(fig)
    return paths


def table(headers, rows, alignment=None):
    alignment = alignment or 'l'+'r'*(len(headers)-1)
    return '\\begin{center}\n\\begin{tabular}{'+alignment+'}\n\\toprule\n'+ \
        ' & '.join(headers)+r' \\'+ '\n\\midrule\n'+ \
        '\n'.join(' & '.join(map(str, row))+r' \\' for row in rows)+ \
        '\n\\bottomrule\n\\end{tabular}\n\\end{center}\n'


def create_report(draft=False):
    output = ROOT/'reports/build'
    output.mkdir(parents=True, exist_ok=True)
    source_paths = ['reports/storage-benchmark-20260906-v2.json',
                    'localizer/benchmarks/RESULTS.json', 'optimizer/results/paired120s-20260906/summary.json',
                    'optimizer/results/summary.json', 'reports/build_report.py', 'reports/QA.md', 'Happy_ending.pdf',
                    'improvements/FINAL_RESULTS.md', 'improvements/RESEARCH_TARGETS.md',
                    'improvements/benchmarks/results/kernel_fresh_v1/summary.json']
    storage = load(source_paths[0])
    figures = diagram(output)
    source_paths += [path for _, path in figures if (ROOT/path).exists()]
    legacy, compact = storage['groups']['legacy'], storage['groups']['sqlite']
    sections = []
    sections.append(r"""\section{Scope and principal outcomes}
This report covers the direct-geometric work and PointSAT/Localizer improvements
of 5 September, followed by the usability, coordinate-optimization and matched
experiments of 6 September 2026. The supplied \texttt{Happy\_ending.pdf} is
\emph{Toward Satisfiability Modulo Realizability}. Its Figure~1 and Section~5.2
specify a $672\times566$ integer witness with no empty convex hexagon and no
convex heptagon. A $64\times78$ result mentioned from another conversation was
not available as a fixture; it was a target, not a claimed reproduced result.

The implementation now provides a compact command-line workflow, a self-contained
optimized Localizer source tree, automated multi-solution compaction, explicit
hull-layer preservation modes, and independently checked outputs. The paper
example reached $101\times78$ with frozen experimental v2 in 600 seconds,
without target-grid options. No claim of global coordinate optimality is made.
The user's final priority was generality across inputs rather than tuning to that
example; subsequent tests use independently discovered types and all four families.

Earlier SAT-guided work solved the supplied 19-point problem with exact Euclidean
threefold symmetry and produced at least 15 distinct 23-point order types. The
new matched experiments also found exactly verified 29-point realizations.
These are verified constructions, not claims of literature-wide novelty or new
bounds for every family.

\section{A usable, compact workflow}
\begin{verbatim}
make
python -m pointsat doctor
python -m pointsat run --problem mixed23 --samples 20 \
  --workers 2 --seconds 600 --out runs/demo
python -m pointsat status runs/demo
python -m pointsat optimize runs/demo --seconds 60 --mode layers
python -m pointsat solutions runs/demo --csv
python -m pointsat export runs/demo --mode layers --out exports/demo --svg
\end{verbatim}
The CLI accepts the four paper presets and advanced legacy settings. It detects
existing external SAT tools and uses \texttt{localizer/build/localizer} by default.
Search and automatic per-solution optimization budgets are separate and explicit.
The old \texttt{PointSAT.py SETTINGS.json} command remains compatible; the modern
\texttt{run --settings} command selects compact output instead.
The presets are \texttt{mixed23} (no 6-hole or convex 7-gon),
\texttt{holes29} (no 6-hole), \texttt{gons32} (no convex 7-gon), and
\texttt{caps26} (no convex 7-gon or 5-cap in the actual x direction).

\subsection{Storage and recovery}
One SQLite database stores compressed JSON events, exact coordinate arrays,
configuration/provenance metadata, and content-addressed original artifacts.
Only the coordinator writes. Temporary WAL files permit inspection while running.
Completed jobs reclaim native input/output files after the last queued or active
reference disappears. A normally completed run leaves one database, not one
directory of files per attempt. Explicit export can produce points, SVG diagrams,
events, and one ZIP of original artifacts with an event/path index.

An event, its artifacts and its accepted solution commit atomically. Interrupted
transactions retain their bounded temporary workspace; \texttt{recover RUN}
independently checks saved coordinates and deduplicates repeated recovery.
Exceptional output is not deleted merely because a database write was interrupted.
Existing research directories are never silently removed or repacked. Recovery
does not pretend to resume the identical stochastic search state.
""")
    sections.append(table(['Storage replay', 'Legacy', 'SQLite'], [
        ['Final files', f"{legacy['files']:,.0f}", f"{compact['files']:,.0f}"],
        ['Logical MiB', f"{legacy['logical_bytes']/2**20:.2f}", f"{compact['logical_bytes']/2**20:.2f}"],
        ['Allocated MiB', f"{legacy['allocated_bytes']/2**20:.2f}", f"{compact['allocated_bytes']/2**20:.2f}"],
        ['Peak scratch files', f"{legacy['peak_temporary_files']:,.0f}", f"{compact['peak_temporary_files']:,.0f}"],
        ['Median wall seconds', f"{legacy['wall_seconds']:.3f}", f"{compact['wall_seconds']:.3f}"],
        ['Median CPU seconds', f"{legacy['cpu_seconds']:.3f}", f"{compact['cpu_seconds']:.3f}"]]))
    sections.append('This deterministic replay used 200 representative SAT records and 400 native-attempt records, three repetitions and alternating storage order. Semantic payloads matched after ordering by job ID. It performs no SAT or native search: its timings isolate storage/coordinator overhead, not end-to-end solution speed. Allocated disk usage decreased by '+f"{100*(1-compact['allocated_bytes']/legacy['allocated_bytes']):.1f}"+r'\%. The first draft hash check compared different event orders and failed; the corrected replay compares the same semantic records by ID. Raw draft and corrected results are retained.'+'\n')
    sections.append(r"""\section{Automatic integer-coordinate optimization}
The tool discovers valid realizations in a collection or in a legacy run's
\texttt{realizations/} directory. New successful searches automatically feed
their saved solutions to the optimizer; no manually paired orientation file is
needed. Input decimals are interpreted exactly and positive axis scaling clears
denominators. Bounded rounding is used only if all triple signs are preserved;
coordinate-dependent cap validity is separately rechecked.

The standard native C++ portfolio combines exact feasible-line moves, valid
order-type boundary crossings, affine/projective proposals with integer rounding
and exact repair. Experimental v2 adds minimum-triangle-area centering and
triangular-hull barycentric normalization. The latter is a general preconditioner,
not a hard-coded transformation of the paper coordinates.
Floating point proposes moves only; bounded signed-128-bit predicates guard
acceptance. Optional actual-geometry repair and target-grid proposals are not
enabled by default. The best valid incumbent is saved atomically, at most once
per second and on termination, rather than dumping every improvement.

\begin{description}
\item[layers (CLI default)] Preserve the sequence of hull-layer sizes; labeled
orientation signs and membership of individual layers may change.
\item[order-type] Preserve every labeled orientation sign.
\item[free] Permit any configuration satisfying the same geometric family.
\end{description}
Preservation refers to the original imported solution, not an earlier free
optimization that may have changed its layers. Listing and export accept a
matching preservation filter; without one, they select the smallest saved box
overall and report its actual layer sizes.
The objective is bounding-box area, with side-length tie-breaking in the native
engine. Width and height are coordinate spans: a $w\times h$ box has
$(w+1)(h+1)$ integer grid sites. Every accepted optimized result has a separate
exact geometric audit, before/after grid dimensions and layers, orientation
changes, seed, budget, and binary hash. A smaller result need not satisfy the
source CNF's label-symmetry-breaking clauses after its order type changes.

\subsection{Matched-input exploratory comparison}
Six inputs were run for 120 native wall seconds each, one seed, at most three
single-core jobs concurrently. The old compactor preserves the complete order
type; the initial new optimizer v1 used its more permissive default. Therefore
this measures the benefit of a broader compaction strategy, not a pure speed
ablation under identical preservation constraints. All twelve outputs passed
independent exact validation.
""")
    paired = load('optimizer/results/paired120s-20260906/summary.json')
    rows = []
    for case in paired['manifest']['cases']:
        source_paths.extend(f'optimizer/results/paired120s-20260906/{case}-{label}/points.pts' for label in ('old', 'new'))
        old_info = describe(read_points(ROOT/f'optimizer/results/paired120s-20260906/{case}-old/points.pts'))
        new_info = describe(read_points(ROOT/f'optimizer/results/paired120s-20260906/{case}-new/points.pts'))
        rows.append([tex(case.replace('23-', '-')), f"{old_info['width']:,}"+r'$\times$'+f"{old_info['height']:,}",
                     f"{new_info['width']:,}"+r'$\times$'+f"{new_info['height']:,}"])
    sections.append(table(['Input', 'Old box', 'New v1 box'], rows))
    sections.append(r"""Area improved on all six exploratory examples. Five independently discovered
inputs represent two original layer-size classes, not five independent layer
classes. One free compaction changed layers from $(3,4,4,6,5,1)$ to
$(3,3,4,6,4,3)$; that result must not be presented as layer-preserving.
Frozen v2 additionally produced a $101\times121$ example from an independently
discovered input while retaining its layers. Other inputs remain substantially
larger under the same budget, so performance is not uniform.

\begin{figure}[htbp]\centering
\includegraphics[width=\textwidth]{configurations.pdf}
\caption{Exact configurations from different sources. Colors show successive
convex-hull layers. Panels use independent coordinate scales; box sizes and layer
sequences are shown explicitly. Seeded compaction is not fresh discovery.}
\end{figure}

\subsection{Frozen generalization and same-mode ablation}
Two additional 23-point order types, two newly found 29-point realizations and
known 26/32-point controls were reserved for frozen-v2 tests. The optimizer was
not tuned after observing them. Separate comparisons use old versus v2, and
frozen v1 versus v2 with identical layer-preservation settings, seeds and budgets.
The optimizer README and JSON manifests retain all outcomes, including ties and
regressions. The following comparison uses 30 seconds per input and seed 1,
with layer-size preservation enabled in both arms.
""")
    optimizer = load('optimizer/results/summary.json')
    ablation = optimizer['phases']['same_mode_ablation']
    grouped = {}
    for row in ablation['rows']:
        grouped.setdefault(row['case'], []).append(row)
    rows = []
    for case, entries in grouped.items():
        labels = {entry['label']: entry for entry in entries}
        boxes = [f"{labels[label]['width']:,}"+r'$\times$'+f"{labels[label]['height']:,}"
                 for label in ablation['comparison']]
        rows.append([tex(case)]+boxes)
    sections.append(table(['Input', 'Standard v1', 'Experimental v2'], rows))
    total_runs = sum(phase['runs'] for phase in optimizer['phases'].values())
    total_valid = sum(phase['valid_runs'] for phase in optimizer['phases'].values())
    total_cpu = sum(phase['cpu_seconds'] for phase in optimizer['phases'].values())
    sections.append(r"""V2 improved area on one of these six inputs and regressed on five. Consequently
v1 is the standard CLI default; v2 is explicitly experimental. The better paper
result is not sufficient evidence for promoting v2. This cohort was used to
select the default, so it is selection evidence, not an untouched estimate of
the selected policy's future performance. Old-versus-v2 cross-family compaction
improved all six boxes, but those comparisons used different preservation
constraints and do not isolate implementation speed.
"""+f'Across all four compaction phases, {total_valid}/{total_runs} saved outputs passed independent exact validation, using {total_cpu:,.1f} CPU seconds.\n')
    sections.append(r"""\section{PointSAT and Localizer changes}
PointSAT now retains parsed CNFs and incremental SAT checkers per worker,
caches exact flippability results, avoids repeated clause shuffling during
realization, schedules bounded work, and records stage timings. Optional
feedback releases actual orientation assumptions selected from UNSAT cores,
solves for a nearby abstract target, and warm-starts the native search.
Numerical realization failure alone never produces a permanent SAT exclusion.
Exact product-inequality nonrealizability certificates may supply sound cuts
only after an independent checker verifies every premise and cancellation.

The self-contained \texttt{localizer/} source tree includes the established
cached incident-constraint evaluator, early rejection, correct coupled symmetry
proposals, archive fixes, warm starts, native budgets, and checked signal saves.
Untouched upstream and optimized-v6 baselines, build targets, tests, provenance
and upstream attribution are retained. No nested Git repository or modification
of a separately cloned upstream checkout is needed. The pinned upstream snapshot
contains no explicit license grant; the package documents that fact rather than
inventing an upstream license.

\subsection{Established speed evidence}
Five paired 100,000-iteration tests per family compared cached and reference
evaluation within the same revised search, with byte-identical coordinates.
Median CPU ratios were 1.879 (23), 2.119 (29), 2.078 (32), and 2.116 (26).
These are fixed-work native speedups, not end-to-end solve-rate multipliers.
A separate matched eight-input orchestration test used the same unchanged
upstream Localizer: wall time fell from 91.945 to 79.791 seconds (13.2\%);
both versions solved 0/8. Loaded-machine measurements are not bare-metal rates.

\subsection{Additional micro-optimizations tested, not promoted}
Two new candidates removed a redundant sampling-weight pass and replaced a
stop-flag mutex read with an atomic read. Eighty serial runs across all four
families compared baseline, either change, and both changes, using five repeats
and 300,000 iterations. Every coordinate byte and search counter matched.
Neither change consistently reduced CPU time across families; both remain
disabled by default. Additional equivalence tests and sanitizers passed.
The earlier 831-run prospective cold-search experiment likewise did not support
enabling optional line/paired moves universally. A failed optimization experiment
is retained as a negative result, not silently presented as an improvement.
""")
    micro = load('localizer/benchmarks/RESULTS.json')
    sections.append(table(['Family', 'v6', 'Sampling', 'Atomic', 'Both'], [
        [tex(family)]+[f"{group['median_cpu_seconds'][variant]:.3f}" for variant in ('v6', 'sampling', 'atomic', 'both')]
        for family, group in micro['families'].items()]))
    sections.append(r'Entries are median CPU seconds for identical fixed work; smaller is better.'+'\n')
    sections.append(r"""\section{Matched feedback-on/off experiments}
This addresses the previously missing causal comparison. Each arm starts from
the same frozen SAT target and native seed. The control uses ordinary warm
retries; the treatment uses target-margin core feedback. Both share a 15-second
native-stage cap and a 60-second total operational budget including loading,
flippability, native search, feedback and acceptance work. All four paper families
are represented. Post-hoc independent geometric checks are outside the search
budget, identical for both arms, and never feed the search.

The first cohort uses four distinct targets per family and two native seeds:
64 arm trials. A separately registered prospective extension uses the next four
targets per family, unchanged code and policy, for another 64. Targets, not
repeated seeds, are the independent clusters. SAT generation is excluded because
the question is search strategy on matched existing targets. This cannot be
interpreted as a complete end-to-end discovery-time benchmark.
""")
    combined = ROOT/'benchmarks/combined_20260906.json'
    benchmark = json.loads(combined.read_text()) if combined.exists() else load('benchmarks/pilot_20260906/summary.json')
    if not draft and not benchmark.get('complete'):
        raise RuntimeError('Combined benchmark not complete; use --draft while jobs run')
    source_paths.append(str(combined.relative_to(ROOT)) if combined.exists() else 'benchmarks/pilot_20260906/summary.json')
    if 'families' in benchmark:
        rows = []
        for family, group in benchmark['families'].items():
            arms = group['arms']
            control, feedback = arms.get('warm_retry', {}), arms.get('core_feedback', {})
            rows.append([tex(family), f"{control.get('valid_geometry_trials',0)}/{control.get('trials',0)}",
                         f"{feedback.get('valid_geometry_trials',0)}/{feedback.get('trials',0)}",
                         group.get('retry_only_successes', 0), group.get('feedback_only_successes', 0)])
        sections.append(table(['Family', 'Retry valid', 'Feedback valid', 'Retry only', 'Feedback only'], rows))
        sections.append('A pair is one target and native seed. Counting a target as solved if either seed succeeds gives the following cluster-level comparison; only fully evaluated targets are included.\n')
        sections.append(table(['Family', 'Targets', 'Retry only', 'Feedback only', 'Both', 'Neither'], [
            [tex(family)]+[group.get('target_cluster_outcomes', {}).get(key, 0)
                          for key in ('complete_models', 'retry_only', 'feedback_only', 'both', 'neither')]
            for family, group in benchmark['families'].items()]))
        arms = [arm for group in benchmark['families'].values() for arm in group['arms'].values()]
        cpu = sum(arm['trials']*arm['mean_cpu_seconds'] for arm in arms)
        audits = sum(arm.get('posthoc_audit_wall_seconds', 0) for arm in arms)
        sections.append(f"The recorded {benchmark.get('completed_trials', 64)} arm trials accumulated {cpu:,.1f} parent-observed operational CPU seconds. Post-hoc audits consumed {audits:,.1f} summed wall seconds, separately accounted for.\n")
        totals = benchmark.get('totals', {})
        if totals:
            sections.append(f"Exit audit: {totals.get('unexpected_nonzero_exit_trials', 0)} unexpected worker exits, "
                            f"{totals.get('operational_inspection_errors', 0)} operational inspection errors. "
                            f"{totals.get('cpu_accounting_flagged_trials', 0)} trials carry conservative CPU-accounting flags for signal shutdown; "
                            'budget-triggered signal exits with saved checkpoints are classified as censored searches, not algorithmic failures.\n')
    if draft:
        sections.append(r'\textbf{DRAFT: benchmark tables may be incomplete. Finalize only after both registered cohorts finish.}'+'\n')
    sections.append(r"""The two first independently certified 29-point outputs illustrate why attribution
matters. One was found in the shared initial 15-second stage and is not evidence
for either retry policy. Another appeared after three feedback repairs while
its matched warm-retry control failed within budget, a paired benefit. Both passed
all 475,020 six-subset checks and a fresh extension plus explicit scan of the
original 825,978-clause CNF. Their convex-six counts, 4,628 and 4,513, prove the
two types differ. Remaining-error counts are search proxies, not certificates.

No general percentage improvement should be inferred from a handful of
discordant pairs. The final benchmark reports distinguish shared-initial-stage
successes, treatment-only successes, target clustering, CPU use, watchdog
censoring, and any errors. A run stopped at its budget is not an UNSAT result.

\section{Earlier geometry and the exact 19-point result}
The initial direct search implemented Overmars-style insertion, motion and
backtracking, fixed-size annealing, conflict-guided repair and exact arrangement
relocation. It grew valid 22-point sets from scratch and reached 23 points with
one remaining empty hexagon, but did not independently discover a valid 23-point
set in that hour. Direct seeded compaction and SAT-seeded repair were useful.
The exact relocation scan ruled out all single-point repairs of one particular
saved trap, not all 23-point configurations.

The supplied 19-point CNF uses 327 compressed signed C3 orientation orbits,
not the ordinary first 969 triple variables. The explicit adapter was independently
checked. An initial abstract assignment and one relaxed target were proved
nonrealizable by exact product-inequality certificates; those statements did
not rule out the geometric problem. Another SAT-guided target was realized.

An exact solution is the origin together with the 120-degree and 240-degree
rotations of these six integer representatives:
\[
(-667,-1605),\ (3333,1586),\ (-2656,1313),\qquad
\]
\[
(-948,1232),\ (2362,1537),\ (33666,3722).
\]
For $(a,b)$ the rotations are
$((-a-b\sqrt3)/2,(a\sqrt3-b)/2)$ and
$((-a+b\sqrt3)/2,(-a\sqrt3-b)/2)$.
Every one of 969 determinants is nonzero. Exhaustive exact checks of 27,132
six-subsets find 28 convex hexagons: 15 with one interior point, 12 with two,
and one with four, never zero or three. Independent Python and C++ quadratic-field
checks agree, and all 2,311,196 original CNF clauses pass. The final warm realization
took 11 seconds; its multi-sample job took 552.032 seconds. These are not the
same timing quantity.

The separate symmetry-free arm generated 639 new independently verified
impossibility proofs and two unresolved abstract candidates. Direct 19-point
searches evaluated billions of proposals but retained forbidden hexagons. Those
negative arms do not detract from the separately certified positive solution,
and they do not establish a universal ordering of SAT and geometric methods.

\section{Validation, limitations, and next work}
The workflow/persistence suite includes transactional interruption and SQLite
failure injection, exact recovery/deduplication, two-worker delayed archive
writes and shared warm references, original-artifact ZIP recovery, settings
conflict rejection and retained-result reporting. The concurrency regression
passed 30 repeated executions. All 22 workflow tests and 25 legacy pipeline
tests passed at the recorded QA snapshot. Native Localizer unit/CLI/equivalence
tests and sanitizers passed; standard v1 passed 133 tests and experimental v2
passed 138 tests, including
120 independent full-count comparisons across the four families.
Five benchmark tests also passed. The final evidence audit checked all 128
registered trials, 64 target/seed pairs and 2,539 compressed artifact hashes.

The new defaults do not promise a particular grid size or universal solution
rate. Compaction benefits depend strongly on the orientation type, preservation
mode, coordinate conditioning and budget. Best-so-far outputs are not proven
minimum grids. To study layer classes, keep mode and budgets fixed and report
all inputs, not only the most compact example. Future work should add more
independent targets and predeclared solver-budget allocations, not retune on a
single successful configuration.

Potential separate research targets from the earlier investigation include
garment-number configurations and balanced colored empty-triangle constructions;
their definitions and primary references are recorded in
\texttt{improvements/RESEARCH\_TARGETS.md}. They are proposals, not claimed solved
problems in this report.

\section{Source and artifact inventory}
The repository retains code, immutable benchmark configurations, inputs and
binary hashes, exact witnesses, and negative/censored results. Primary entry
points and evidence are:
\begin{itemize}
\item \texttt{docs/USAGE.md}: installation, defaults, recovery and export.
\item \texttt{pointsat/}: CLI, SQLite storage, exact coordinate utilities and automated optimization.
\item \texttt{localizer/}: source, baselines, build and micro-optimization ablations.
\item \texttt{optimizer/README.md}: algorithm, preservation modes, exploratory and held-out results.
\item \texttt{benchmarks/README.md}: matched strategy protocol and final cohort reports.
\item \texttt{benchmarks/success29/}: exact 29-point outputs and original-CNF certificates.
\item \texttt{improvements/success19/}: exact C3 coordinates, diagram and independent certificates.
\item \texttt{improvements/FINAL\_RESULTS.md} and \texttt{direct/RESULTS23.md}: earlier experiments.
\end{itemize}
This PDF is generated by \texttt{reports/build\_report.py}. Its build manifest
records the source inputs and hashes. No search is launched by the report builder.
""")
    preamble = r"""\documentclass[10pt,letterpaper]{article}
\usepackage[margin=0.8in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{booktabs,graphicx,hyperref,amsmath}
\hypersetup{colorlinks=true,urlcolor=blue,linkcolor=blue,pdftitle={PointSAT engineering and experiments}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.5em}
\emergencystretch=2em
\title{PointSAT: usable workflows, automatic compaction,\\and measured solver improvements}
\author{Technical experiment report}
\date{6 September 2026}
\begin{document}
\maketitle
\begin{abstract}
A compact engineering and experimental record of the PointSAT work. It separates
software improvements, exact constructions, fixed-work speed, coordinate-size
reductions and matched search outcomes. The emphasis is reproducibility and
generality across point sets rather than fitting one published grid.
\end{abstract}
\tableofcontents
\newpage
"""
    report = preamble+'\n'.join(sections)+'\n\\end{document}\n'
    (output/'report.tex').write_text(report)
    for _ in range(2):
        completed = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', 'report.tex'], cwd=output, capture_output=True, text=True)
        if completed.returncode:
            raise RuntimeError(completed.stdout[-5000:])
    destination = ROOT/'reports/PointSAT-improvements.pdf'
    destination.write_bytes((output/'report.pdf').read_bytes())
    manifest = {'built_utc': datetime.now(timezone.utc).isoformat(), 'draft': draft,
                'report_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                'sources': {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in source_paths}}
    (ROOT/'reports/report-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft', action='store_true')
    create_report(parser.parse_args().draft)
