"""Automatic discovery, independent verification, and bounded optimization."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from .geometry import bounded_points, describe, pts_text, read_points, real_text, signs
from .store import RunStore

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    'mixed23': (23, '7gon-6hole-23-compact.cnf', 7, 6),
    'holes29': (29, '6hole-29-compact.cnf', 0, 6),
    'gons32': (32, '7gon-32.cnf', 7, 0),
    'caps26': (26, '7gon-no-5-cap-no-sb-26.cnf', 7, 0),
}


def database_path(path):
    path = Path(path)
    return path if path.suffix in ('.sqlite', '.db') else path/'run.sqlite'


def native(command, timeout, input_text=None):
    begin = time.monotonic()
    process = subprocess.Popen([str(x) for x in command], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=(os.name == 'posix'))
    def stop(sig):
        try:
            if os.name == 'posix':
                os.killpg(process.pid, sig)
            else:
                process.send_signal(sig)
        except ProcessLookupError:
            pass
    try:
        stdout, stderr = process.communicate(input_text, timeout=timeout)
        return dict(returncode=process.returncode, stdout=stdout, stderr=stderr,
                    wall_seconds=time.monotonic()-begin, timed_out=False)
    except subprocess.TimeoutExpired:
        stop(signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            stop(signal.SIGKILL)
            stdout, stderr = process.communicate()
        return dict(returncode=process.returncode, stdout=stdout, stderr=stderr,
                    wall_seconds=time.monotonic()-begin, timed_out=True)
    except BaseException:
        stop(signal.SIGTERM)
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            stop(signal.SIGKILL)
            process.communicate()
        raise


def verify_points(points, family):
    if family not in FAMILIES:
        raise ValueError(f"Automatic geometric certification supports {', '.join(FAMILIES)}; got {family!r}")
    n, _, gon, hole = FAMILIES[family]
    if len(points) != n:
        raise ValueError(f"{family} requires {n} points, got {len(points)}")
    describe(points)  # exact general-position check independent of native code
    checker = ROOT/'direct/verify_big'
    if not checker.is_file():
        raise FileNotFoundError('Build exact verifier first: make -C direct verify_big')
    stage = native([checker, '--input', '-', '--gon', gon, '--hole', hole], 60, pts_text(points))
    if stage['timed_out'] or stage['returncode'] not in (0, 1):
        raise RuntimeError('Exact verifier failed: '+stage['stderr'][-1000:])
    result = json.loads(stage['stdout'])
    if family == 'caps26':
        # The cap definition depends on actual x order, not solely on the CNF.
        ordered = sorted(points)
        count = [[int(i < j and ordered[i][0] < ordered[j][0]) for j in range(n)] for i in range(n)]
        from .geometry import cross
        for _ in range(3, 6):
            previous, count = count, [[0]*n for _ in range(n)]
            for i in range(1, n):
                for j in range(i+1, n):
                    if ordered[i][0] < ordered[j][0]:
                        count[i][j] = sum(previous[h][i] for h in range(i)
                                          if cross(ordered[h], ordered[i], ordered[j]) < 0)
        result['convex_5_caps'] = sum(map(sum, count))
        result['valid'] = result['valid'] and not result['convex_5_caps']
    result['checker_sha256'] = hashlib.sha256(checker.read_bytes()).hexdigest()
    result['independent_geometric_audit'] = True
    return result


def discover(source, limit=100):
    """One preferred coordinate file per result folder, not every scratch copy."""
    source = Path(source)
    if source.is_file():
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(source)
    preferred = ('normalized.pts', 'compact.pts', 'points.pts', 'points.real')
    folders = {p.parent for p in source.rglob('*.pts')}
    folders.update(p.parent for p in source.rglob('*.real') if 'scratch' not in p.parts)
    result = []
    for folder in sorted(folders):
        if 'scratch' in folder.parts or any(part.startswith('.work-') for part in folder.parts):
            continue
        candidate = next((folder/name for name in preferred if (folder/name).is_file()), None)
        if candidate:
            result.append(candidate)
        else:
            result.extend(sorted(folder.glob('*.pts')) or sorted(folder.glob('*.real')))
    return result[:limit]


def import_coordinates(store, source, family, limit=100):
    results = []
    known_types = {s['info']['orientation_sha256'] for s in store.solutions()}
    for path in discover(source, limit):
        row = {'source': str(path.resolve())}
        try:
            points = read_points(path)
            info = describe(points)
            if info['orientation_sha256'] in known_types:
                row.update(status='duplicate_labeled_order_type')
            else:
                certificate = verify_points(points, family)
                if certificate['valid']:
                    identifier = store.add_solution(points, family, str(path.resolve()), certificate)
                    known_types.add(info['orientation_sha256'])
                    row.update(status='imported', solution_id=identifier, info=info)
                else:
                    row.update(status='rejected', verification=certificate)
        except (ValueError, OSError, RuntimeError) as exc:
            row.update(status='rejected', error=str(exc))
        results.append(row)
    store.set_meta('last_import', results)
    return results


def optimize_solutions(store, seconds=30, seed=1, mode='layers', only=None, strategy='standard'):
    if strategy not in ('standard', 'experimental'):
        raise ValueError('Unknown optimization strategy')
    engine = ROOT/('optimizer/compact_v2' if strategy == 'experimental' else 'optimizer/compact')
    if not engine.is_file():
        raise FileNotFoundError('Build the optimizer first: make -C optimizer')
    results = []
    solutions = list(store.solutions())
    for solution in solutions:
        if only is not None and solution['id'] not in only:
            continue
        points, before = store.best_points(solution, mode)
        report = dict(solution_id=solution['id'], before=before, seconds_budget=seconds,
                      seed=seed+solution['id']-1, mode=mode, strategy=strategy, accepted=False,
                      engine_sha256=hashlib.sha256(engine.read_bytes()).hexdigest())
        try:
            certified_input = verify_points(points, solution['family'])
            if not certified_input['valid']:
                raise ValueError('Stored source fails independent geometry check')
            rounded = bounded_points(points)
            # Sign-preserving rounding can change x ties: recheck cap semantics.
            if solution['family'] == 'caps26' and not verify_points(rounded, solution['family'])['valid']:
                raise ValueError('Rounding would change cap validity; source retained')
            with tempfile.TemporaryDirectory(prefix='pointsat-opt-') as work:
                source, output = Path(work)/'input.pts', Path(work)/'output.pts'
                source.write_text(pts_text(rounded))
                command = [engine, '--input', source, '--output', output, '--seconds', seconds,
                           '--seed', report['seed'], '--family', solution['family']]
                if mode == 'order-type':
                    command += ['--preserve-order-type']
                elif mode == 'layers':
                    command += ['--preserve-layers']
                stage = native(command, seconds+5)
                report.update(stage=stage)
                if not output.is_file() or stage['returncode'] not in (0, 130, -signal.SIGTERM):
                    raise RuntimeError('Optimizer failed: '+stage['stderr'][-1000:])
                candidate = read_points(output)
            after = describe(candidate)
            certificate = verify_points(candidate, solution['family'])
            report.update(after=after, verification=certificate,
                          orientations_changed=sum(a != b for a, b in zip(signs(points), signs(candidate))))
            if not certificate['valid']:
                raise ValueError('Optimizer candidate failed independent exact validation')
            if mode == 'order-type' and signs(points) != signs(candidate):
                raise ValueError('Optimizer changed the requested order type')
            if mode == 'layers' and before['hull_layers'] != after['hull_layers']:
                raise ValueError('Optimizer changed the requested hull-layer sizes')
            if after['area'] <= before['area']:
                report['accepted'] = True
                store.add_optimization(solution['id'], candidate, report)
            else:
                report['reason'] = 'No area improvement; original retained'
                store.add_optimization(solution['id'], None, report)
        except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            report['error'] = str(exc)
            store.add_optimization(solution['id'], None, report)
        results.append(report)
    return results


def svg(points, info, title='PointSAT solution'):
    import html
    width, height = info['width'], info['height']
    scale = min(620/max(1, width), 440/max(1, height))
    min_x, min_y = min(p[0] for p in points), min(p[1] for p in points)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 550">',
           '<rect width="700" height="550" fill="white"/>',
           f'<text x="35" y="30" font-family="sans-serif" font-size="18">{html.escape(title)}</text>']
    for i, (x, y) in enumerate(points, 1):
        px, py = 40+(x-min_x)*scale, 490-(y-min_y)*scale
        out.append(f'<circle cx="{px:.3f}" cy="{py:.3f}" r="3" fill="#185c91"/>')
        out.append(f'<text x="{px+5:.3f}" y="{py-5:.3f}" font-family="sans-serif" font-size="10">{i}</text>')
    caption = f'{width} × {height}; hull layers '+','.join(map(str, info['hull_layers']))
    out.append(f'<text x="35" y="530" font-family="sans-serif" font-size="14">{html.escape(caption)}</text></svg>')
    return '\n'.join(out)+'\n'
