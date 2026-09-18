"""A small, dependency-light CLI around the tested PointSAT pipeline."""
import argparse
import csv
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import shutil
import signal
import sqlite3
import sys
import zipfile
import zlib

from .geometry import describe, pts_text, read_points, real_text
from .store import RunStore
from .workflow import FAMILIES, ROOT, database_path, import_coordinates, optimize_solutions, svg, verify_points


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('must be a finite positive number')
    return number


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def default_output():
    return str(Path('runs')/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))


def find_executable(candidates):
    for name in candidates:
        candidate = ROOT/name
        if candidate.is_file():
            return str(candidate)
        located = shutil.which(name)
        if located:
            return located
    return str(ROOT/candidates[0])


def doctor():
    binaries = {
        'Localizer': find_executable(['localizer/build/localizer']),
        'SAT solver': find_executable(['kissat/build/kissat', 'direct/vendor/kissat/build/kissat', 'kissat']),
        'scranfilize': find_executable(['scranfilize/scranfilize', 'direct/vendor/scranfilize/scranfilize', 'scranfilize']),
        'optimizer': find_executable(['optimizer/compact']),
        'exact verifier': find_executable(['direct/verify_big']),
    }
    okay = True
    for name, path in binaries.items():
        exists = Path(path).is_file()
        print(f"{'OK     ' if exists else 'MISSING'} {name}: {path}")
        okay &= exists
    pysat = importlib.util.find_spec('pysat') is not None
    print(f"{'OK     ' if pysat else 'MISSING'} python-sat in {sys.executable}")
    if not pysat:
        print('Install Python dependencies: python -m pip install -r requirements.txt')
    if not okay:
        print('Build repository native tools: make')
    return 0 if okay and pysat else 1


def run(args):
    if importlib.util.find_spec('pysat') is None:
        raise RuntimeError('python-sat is missing; install requirements.txt in this Python environment (see pointsat doctor)')
    from improvements.pipeline.runner import PipelineDeadline, run_pipeline
    settings = json.loads(Path(args.settings).read_text()) if args.settings else {}
    family = args.problem or settings.get('problem_family')
    if not family:
        family = next((key for key, value in FAMILIES.items() if value[1] == Path(settings.get('base_file', '')).name), None)
    if not settings and not family:
        family = 'mixed23'
    if family in FAMILIES:
        n, cnf, _, _ = FAMILIES[family]
        if args.problem and settings:
            known_base_family = next((key for key, value in FAMILIES.items()
                                      if value[1] == Path(settings.get('base_file', '')).name), None)
            if (settings.get('n', n) != n or settings.get('problem_family', family) != family or
                    known_base_family not in (None, family)):
                raise ValueError('--problem conflicts with the settings CNF/n/family; use that preset without --settings or supply matching settings')
        settings.setdefault('n', n)
        settings.setdefault('base_file', str(ROOT/cnf))
    if 'base_file' not in settings:
        raise ValueError('Choose --problem or supply a settings file with base_file')
    settings.setdefault('problem_family', family)
    settings.setdefault('cadical_loc', find_executable(['kissat/build/kissat', 'direct/vendor/kissat/build/kissat', 'kissat']))
    settings.setdefault('scranfilize_loc', find_executable(['scranfilize/scranfilize', 'direct/vendor/scranfilize/scranfilize', 'scranfilize']))
    settings.setdefault('localizer_loc', str(ROOT/'localizer/build/localizer'))
    defaults = dict(n_solutions=20, workers=2, worker_max_threads=1, solver_timeout=90,
                    solution_generation='scranfilize', sat_extra_args=['--quiet', '--plain'],
                    seed=1, localizer_native_time_limit=True, localizer_extra_args=['-q'],
                    localizer_attempt_levels=1, localizer_attempt_timeouts=[15]*4,
                    localizer_attempt_thresholds=[10000]*3, localizer_attempt_branches=[1]*3,
                    warm_start_retries=True, feedback_rounds=3, feedback_core_choice='hash',
                    feedback_max_relaxed=256, feedback_max_solves=256,
                    localizer_archive_candidates=3, wall_time_limit=600)
    for key, value in defaults.items():
        settings.setdefault(key, value)
    if family in ('mixed23', 'holes29', 'gons32'):
        settings.setdefault('radial_relabel_check', True)
        settings.setdefault('feedback_radial_scaffold', True)
    if family == 'caps26' and '--ordered-x' not in settings['localizer_extra_args']:
        settings['localizer_extra_args'] = settings['localizer_extra_args']+['--ordered-x']
    for option, key in [('workers', 'workers'), ('samples', 'n_solutions'), ('seed', 'seed'),
                        ('seconds', 'wall_time_limit'), ('sat_seconds', 'solver_timeout')]:
        if getattr(args, option) is not None:
            settings[key] = getattr(args, option)
    if args.attempt_seconds:
        settings['localizer_attempt_timeouts'] = [args.attempt_seconds]*max(4, settings['localizer_attempt_levels'])
    if args.feedback:
        settings['feedback_rounds'] = 0 if args.feedback == 'off' else 3
        settings['localizer_attempt_levels'] = 4 if args.feedback == 'off' else 1
        settings['feedback_core_choice'] = 'target_margin' if args.feedback == 'target-margin' else 'hash'
    settings.update(output_folder=str(Path(args.out or default_output()).resolve()),
                    output_storage=args.storage, quiet_progress=args.quiet)
    for key in ('cadical_loc', 'localizer_loc', 'scranfilize_loc'):
        if not Path(settings[key]).is_file() and not shutil.which(settings[key]):
            raise FileNotFoundError(f"{key}: {settings[key]}; run python -m pointsat doctor")
    print(f"Run: {settings['output_folder']}\nSearch: {family or 'custom'}, {settings['n_solutions']} samples, "
          f"{settings['workers']} workers, {settings['wall_time_limit']:g}s budget", flush=True)
    try:
        summary = run_pipeline(settings)
    except PipelineDeadline:
        db = database_path(settings['output_folder'])
        if db.is_file():
            with RunStore(db, readonly=True) as store:
                summary = store.get_meta('summary', {})
        else:
            summary = json.loads((Path(settings['output_folder'])/'summary.json').read_text())
        print('Search budget reached; active workers saved their checkpoints.', flush=True)
    print(f"Finished: {summary.get('sat_models', 0)} SAT models; "
          f"{summary.get('distinct_realized_samples', summary.get('realized', 0))} accepted samples; "
          f"{summary.get('errors', 0)} errors.")
    if args.storage == 'sqlite' and args.optimize_seconds:
        with RunStore(database_path(settings['output_folder'])) as store:
            if store.status()['solutions']:
                print('Automatically compacting saved solutions (separate per-solution budget).', flush=True)
                reports = optimize_solutions(store, args.optimize_seconds, settings['seed'], args.optimize_mode,
                                             strategy=args.optimize_strategy)
                print_optimizations(reports)
    print(f"Inspect: python -m pointsat status {settings['output_folder']}")
    return 1 if summary.get('errors') else 0


def print_optimizations(reports):
    for report in reports:
        after = report.get('after', report['before']) if report.get('accepted') else report['before']
        outcome = f"{after['width']} × {after['height']}; layers {after['hull_layers']}"
        print(f"solution {report['solution_id']}: {outcome}" +
              (f"; {report['error']}" if report.get('error') else ''))


def optimize(args):
    target = args.run or args.out
    if not target:
        raise ValueError('Give an existing run, or --paper/--scan with --out for a new collection')
    db = database_path(target)
    creating = not db.exists()
    legacy = Path(target)/'realizations' if creating and (Path(target)/'realizations').is_dir() else None
    if creating and not (args.paper or args.scan or legacy):
        raise ValueError('Run not found; create it with run or import, or use optimize --paper --out DIR')
    with RunStore(db, create=creating) as store:
        if creating:
            store.set_meta('state', 'collection')
        if args.paper or args.scan or legacy:
            source = ROOT/'direct/seeds/paper23.pts' if args.paper else Path(args.scan) if args.scan else legacy
            rows = import_coordinates(store, source, args.problem, args.max_inputs)
            print(f"Imported {sum(r['status']=='imported' for r in rows)} solutions; "
                  f"{sum(r['status']=='rejected' for r in rows)} rejected inputs.")
        reports = optimize_solutions(store, args.seconds, args.seed, args.mode,
                                     set(args.solution) if args.solution else None, args.strategy)
        print_optimizations(reports)
        if not reports:
            print('No solutions to optimize. Inspect imports with status --json or import a certified collection.')
        return 0 if reports and not any(r.get('error') for r in reports) else 1


def status(args):
    legacy = Path(args.run)/'summary.json'
    if not database_path(args.run).exists() and legacy.is_file():
        summary = json.loads(legacy.read_text())
        if args.json:
            print(json.dumps({'storage': 'legacy', 'summary': summary}, indent=2))
        else:
            print(f"Legacy run: {summary.get('jobs', 0)} jobs, {summary.get('realized', 0)} accepted results")
            print('Use optimize RUN to automatically import and compact its realizations, or import RUN --out NEWDIR.')
        return 0
    with RunStore(database_path(args.run), readonly=True) as store:
        report = store.status()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['state']}: {report['events']} events, {report['solutions']} saved solutions, "
              f"{report['optimizations']} optimization attempts")
        print('  '.join(f'{key}: {count}' for key, count in sorted(report['statuses'].items())))
        if report['summary']:
            print(f"Search wall time: {report['summary']['wall_seconds']:.2f}s")
        if report['recovery_workspace']:
            print(f"Recovery files retained: {report['recovery_workspace']}; use pointsat recover {args.run}")
        print(report['database'])
    return 0


def solutions(args):
    with RunStore(database_path(args.run), readonly=True) as store:
        rows = []
        for solution in store.solutions():
            _, info = store.best_points(solution, args.mode)
            rows.append(dict(id=solution['id'], family=solution['family'], width=info['width'],
                             height=info['height'], area=info['area'], hull_layers=info['hull_layers'],
                             source=solution['source']))
    if args.json:
        print(json.dumps(rows, indent=2))
    elif args.csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=['id', 'family', 'width', 'height', 'area', 'hull_layers', 'source'])
        writer.writeheader()
        writer.writerows(rows)
    else:
        for row in rows:
            print(f"{row['id']:4} {row['family'] or 'custom':8} {row['width']} × {row['height']} "
                  f"area={row['area']} layers={','.join(map(str, row['hull_layers']))}")
        if not rows:
            print('No accepted solutions in this run.')
    return 0


def import_run(args):
    db = database_path(args.out)
    creating = not db.exists()
    with RunStore(db, create=creating) as store:
        if creating:
            store.set_meta('state', 'collection')
        rows = import_coordinates(store, args.source, args.problem, args.max_inputs)
        print(json.dumps(rows, indent=2) if args.json else
              f"Imported {sum(r['status']=='imported' for r in rows)}; "
              f"duplicates {sum(r['status']=='duplicate_labeled_order_type' for r in rows)}; "
              f"rejected {sum(r['status']=='rejected' for r in rows)}. Database: {db}")
    return 0 if any(r['status'] != 'rejected' for r in rows) else 1


def recover(args):
    """Recover geometry, not resume a stochastic experiment with invented state."""
    db = database_path(args.run)
    with RunStore(db) as store:
        family = args.problem or store.get_meta('settings', {}).get('problem_family')
        if family not in FAMILIES:
            raise ValueError('Recovery needs a supported --problem for independent exact checking')
        workspaces = sorted(db.parent.glob('.work-*'))
        results = []
        for workspace in workspaces:
            for path in sorted(workspace.glob('*.real')):
                results.extend(import_coordinates(store, path, family, 1))
        store.set_meta('last_recovery', results)
        print(f"Recovered {sum(r['status']=='imported' for r in results)} solutions; "
              f"{sum(r['status']=='rejected' for r in results)} candidates failed exact validation. "
              'Original recovery files were retained.')
    return 0


def export(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with RunStore(database_path(args.run), readonly=True) as store:
        for solution in store.solutions():
            if args.solution and solution['id'] not in args.solution:
                continue
            points, info = store.best_points(solution, args.mode)
            prefix = out/f"solution-{solution['id']:04}"
            contents = {prefix.with_suffix('.pts'): pts_text(points)}
            if args.svg:
                contents[prefix.with_suffix('.svg')] = svg(points, info, f"Solution {solution['id']}")
            for path in contents:
                if path.exists():
                    raise FileExistsError(f'Refusing to overwrite {path}; use a fresh export directory')
            for path, content in contents.items():
                with path.open('x') as file:
                    file.write(content)
                print(path)
        if args.events:
            path = out/'events.jsonl'
            with path.open('x') as file:
                for event in store.events():
                    file.write(json.dumps(event)+'\n')
        if args.artifacts:
            index = []
            with zipfile.ZipFile(out/'artifacts.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for row in store.db.execute('SELECT a.event_id,a.role,a.name,a.digest,b.data FROM artifacts a JOIN blobs b USING(digest) ORDER BY a.event_id,a.role,a.name'):
                    name = f"event-{row['event_id']}/{row['role']}/{row['name']}"
                    content = zlib.decompress(row['data'])
                    archive.writestr(name, content)
                    index.append(dict(event_id=row['event_id'], role=row['role'], original_name=row['name'],
                                      sha256=row['digest'], archive_path=name))
                archive.writestr('index.json', json.dumps(index, indent=2)+'\n')
            print(out/'artifacts.zip')
    return 0


def verify(args):
    points = read_points(args.input)
    result = dict(geometry=describe(points), verification=verify_points(points, args.problem))
    print(json.dumps(result, indent=2))
    return 0 if result['verification']['valid'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='pointsat', description='SAT-guided geometry, compact run storage, and automatic integer-grid optimization.')
    parser.add_argument('--version', action='version', version='PointSAT 0.2.0')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='check tools and Python dependencies').set_defaults(func=lambda args: doctor())
    p = commands.add_parser('run', help='search; store one database; automatically optimize successes')
    p.add_argument('--problem', '--family', choices=FAMILIES)
    p.add_argument('--settings', help='optional legacy JSON settings; explicit CLI options override it')
    p.add_argument('--out', help='fresh run directory (default runs/UTC-timestamp)')
    p.add_argument('--samples', type=positive_int)
    p.add_argument('--workers', type=positive_int)
    p.add_argument('--seconds', type=positive, help='search wall budget; checkpoint shutdown has a bounded grace')
    p.add_argument('--attempt-seconds', type=positive)
    p.add_argument('--sat-seconds', type=positive)
    p.add_argument('--seed', type=int)
    p.add_argument('--feedback', choices=['off', 'hash', 'target-margin'])
    p.add_argument('--storage', choices=['sqlite', 'legacy'], default='sqlite', help='legacy retains all research files')
    p.add_argument('--optimize-seconds', type=positive, default=10, help='extra native budget per solution (default 10)')
    p.add_argument('--no-optimize', action='store_const', const=0, dest='optimize_seconds')
    p.add_argument('--optimize-mode', choices=['layers', 'order-type', 'free'], default='layers')
    p.add_argument('--optimize-strategy', choices=['standard', 'experimental'], default='standard')
    p.add_argument('--quiet', action='store_true')
    p.set_defaults(func=run)
    p = commands.add_parser('status', help='inspect an active or finished database')
    p.add_argument('run'); p.add_argument('--json', action='store_true'); p.set_defaults(func=status)
    p = commands.add_parser('solutions', help='list grid sizes and convex-hull layers')
    p.add_argument('run'); p.add_argument('--json', action='store_true'); p.add_argument('--csv', action='store_true'); p.set_defaults(func=solutions)
    p.add_argument('--mode', choices=['best', 'layers', 'order-type'], default='best', help='select smallest overall, or smallest preserving the original layers/order type')
    p = commands.add_parser('import', help='discover and independently validate existing coordinates')
    p.add_argument('source'); p.add_argument('--out', required=True)
    p.add_argument('--problem', '--family', choices=FAMILIES, default='mixed23')
    p.add_argument('--max-inputs', type=positive_int, default=100); p.add_argument('--json', action='store_true'); p.set_defaults(func=import_run)
    p = commands.add_parser('optimize', help='automatically optimize all saved solutions, or the paper example')
    p.add_argument('run', nargs='?'); p.add_argument('--out')
    source = p.add_mutually_exclusive_group(); source.add_argument('--paper', action='store_true'); source.add_argument('--scan')
    p.add_argument('--problem', '--family', choices=FAMILIES, default='mixed23')
    p.add_argument('--seconds', type=positive, default=30, help='native budget per solution')
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--mode', choices=['layers', 'order-type', 'free'], default='layers')
    p.add_argument('--strategy', choices=['standard', 'experimental'], default='standard', help='standard uses v1; experimental uses the mixed-result v2 extensions')
    p.add_argument('--solution', type=positive_int, action='append'); p.add_argument('--max-inputs', type=positive_int, default=100)
    p.set_defaults(func=optimize)
    p = commands.add_parser('recover', help='exact-check saved native files after interruption; never deletes them')
    p.add_argument('run'); p.add_argument('--problem', '--family', choices=FAMILIES); p.set_defaults(func=recover)
    p = commands.add_parser('export', help='explicitly export best coordinates and optional diagrams/log')
    p.add_argument('run'); p.add_argument('--out', required=True)
    p.add_argument('--mode', choices=['best', 'layers', 'order-type'], default='best', help='select smallest overall, or smallest preserving the original layers/order type')
    p.add_argument('--solution', type=positive_int, action='append'); p.add_argument('--svg', action='store_true')
    p.add_argument('--events', action='store_true'); p.set_defaults(func=export)
    p.add_argument('--artifacts', action='store_true', help='one ZIP with original artifacts and an event/path index')
    p = commands.add_parser('verify', help='independently check a coordinate file using exact arithmetic')
    p.add_argument('input'); p.add_argument('--problem', '--family', choices=FAMILIES, default='mixed23'); p.set_defaults(func=verify)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print('Stopped; recorded results are retained. Use status to inspect them.', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f'pointsat: {exc}', file=sys.stderr)
        return 2
