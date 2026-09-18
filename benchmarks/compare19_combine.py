#!/usr/bin/env python3
"""Build a separately validated fresh-plus-historical SAT target corpus.

Selection never reads realization outcomes. Historical candidates are exclusively
initial SAT records' original_solution, not feedback targets or partial models.
The known positive-control order type is explicitly excluded from this study.
One child owns one original-CNF solver; an outer watchdog bounds native SAT calls.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import resource
import signal
import sqlite3
import subprocess
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.compare19_inputs import (DEFAULT_CNF, DEFAULT_MAP, SCHEMA, connect,
    digest_file, distance_summary, event, hamming, load_models, meta, stop_child,
    utc, validate_extension, write_manifest)
from benchmarks.compare19_types import canonicalize
from improvements.pipeline.orientation_map import OrientationMap

CONTROL = ROOT/'improvements/success19/witness.or'
TERMINAL = {'COMPLETE', 'TIME_LIMIT', 'INTERRUPTED', 'ERROR', 'DIVERSITY_EXHAUSTED'}


def historical_sources():
    """Frozen source priority; within each file use ascending physical line."""
    overnight = sorted((ROOT/'improvements/pipeline/unattended_20260905/runs').glob(
        'job*-symmetry19-target_margin/raw_results.jsonl'))
    early = [ROOT/'improvements/pipeline'/p/'raw_results.jsonl' for p in (
        'resumed_0532/symmetry19_run', 'resumed_0532/symmetry19_target_run',
        'symmetry19_feedback/run')]
    return overnight + early


def primary_projection(value, variables):
    """Require every mapped variable exactly once, with no conflicting signs."""
    if isinstance(value, str):
        values = []
        for line in value.splitlines():
            tokens = line.split()
            if tokens and tokens[0] == 'v':
                tokens = tokens[1:]
            values.extend(int(token) for token in tokens)
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError('Expected original_solution string or primary literal list')
    assignment = {}
    for literal in values:
        if not isinstance(literal, int) or isinstance(literal, bool):
            raise ValueError('Non-integer model literal')
        if not literal:
            continue
        variable = abs(literal)
        if variable in assignment:
            raise ValueError('Duplicate or conflicting model variable')
        assignment[variable] = literal
    missing = set(variables)-assignment.keys()
    if missing:
        raise ValueError(f'Incomplete original primary assignment: {len(missing)} missing')
    return [assignment[variable] for variable in variables]


def canonical_key(canonical):
    return (canonical['n'], canonical['canonical_signs']) if canonical['supported'] else None


def exclusion(primary, canonical, selected, selected_types, control_key, minimum):
    key = canonical_key(canonical)
    if key is not None and key == control_key:
        return 'KNOWN_POSITIVE_CONTROL', None
    if key is not None and key in selected_types:
        return 'CANONICAL_DUPLICATE', None
    nearest = min((hamming(primary, row['primary_model']) for row in selected), default=None)
    if nearest is not None and nearest < minimum:
        return 'MINIMUM_DISTANCE', nearest
    return None, nearest


def source_info(path):
    settings_path = path.parent/'settings.json'
    settings = json.loads(settings_path.read_text())
    base = Path(settings['base_file'])
    if not base.is_absolute():
        base = ROOT/base
    audit = Path(settings.get('audit_base_file', settings['base_file']))
    if not audit.is_absolute():
        audit = ROOT/audit
    proofs = [Path(p) if Path(p).is_absolute() else ROOT/p
              for p in settings.get('nonrealizability_proof_files', [])]
    return dict(path=str(path.resolve()), sha256=digest_file(path),
                settings=str(settings_path.resolve()), settings_sha256=digest_file(settings_path),
                source_cnf=str(base.resolve()), source_cnf_sha256=digest_file(base),
                declared_audit_cnf=str(audit.resolve()), declared_audit_cnf_sha256=digest_file(audit),
                proof_sources=[dict(path=str(p.resolve()), sha256=digest_file(p)) for p in proofs])


def register(args, output):
    fresh = args.fresh_corpus.resolve()
    source_manifest = json.loads((fresh/'manifest.json').read_text())
    source_db = sqlite3.connect((fresh/'corpus.sqlite').as_uri()+'?mode=ro', uri=True)
    try:
        source_state = json.loads(source_db.execute("SELECT value FROM metadata WHERE key='state'").fetchone()[0])
    finally:
        source_db.close()
    if source_state not in TERMINAL or source_manifest.get('state') != source_state:
        raise ValueError('Fresh corpus must have a finalized manifest and terminal SQLite state')
    n = json.loads(args.orientation_map.read_text())['n']
    adapter = OrientationMap(args.orientation_map, n)
    if args.min_distance > len(adapter.variables):
        raise ValueError('Minimum distance exceeds primary variable count')
    cnf_hash, map_hash = digest_file(args.cnf), digest_file(args.orientation_map)
    original_registration = source_manifest['registration']
    if original_registration['cnf_sha256'] != cnf_hash or original_registration['orientation_map_sha256'] != map_hash:
        raise ValueError('Fresh corpus original CNF or mapping differs from combine inputs')
    fresh_records = list(load_models(fresh))
    if len(fresh_records) != source_manifest['accepted_models']:
        raise ValueError('Fresh manifest count differs from committed rows')
    if len(fresh_records) > args.count:
        raise ValueError('Requested count would discard fresh commits; increase --count')
    control = canonicalize(args.control_orientation.read_text())
    if not control['supported'] or control['n'] != n:
        raise ValueError('Positive-control exclusion requires a supported complete same-n order type')
    sources = [source_info(p) for p in (args.historical_log if args.historical_log is not None else historical_sources())]
    for source in sources:
        if source['declared_audit_cnf_sha256'] != cnf_hash:
            raise ValueError('Historical source declares a different original audit CNF')
    candidates, ignored = [], []
    for row in fresh_records:
        primary = primary_projection(row['primary_model'], adapter.variables)
        if adapter.orientations(primary) != row['orientations']:
            raise ValueError('Fresh orientation expansion differs from the registered map')
        candidates.append(dict(primary_model=primary, origin=dict(
            stratum='fresh', source=str(fresh/'corpus.sqlite'), source_id=row['id'],
            source_primary_sha256=row['primary_sha256'], original_generation=row['generation'])))
    for source in sources:
        with Path(source['path']).open() as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get('type') != 'SAT':
                    # Deliberately do not inspect geometry or feedback records.
                    continue
                origin = dict(stratum='historical_initial_sat', source=source['path'],
                              source_sha256=source['sha256'], line=line_number,
                              source_id=row.get('id'), sat_seed=row.get('scranfilize_seed'),
                              source_cnf=source['source_cnf'], source_cnf_sha256=source['source_cnf_sha256'])
                if row.get('satisfiable') is not True or 'original_solution' not in row:
                    ignored.append(dict(origin=origin, reason='NOT_SAT_OR_NO_ORIGINAL_SOLUTION'))
                    continue
                primary = primary_projection(row['original_solution'], adapter.variables)
                origin['original_solution_sha256'] = hashlib.sha256(row['original_solution'].encode()).hexdigest()
                candidates.append(dict(primary_model=primary, origin=origin))
    registration = dict(schema_version=1, registered_utc=utc(), count=args.count,
        seed=original_registration.get('seed'), min_distance=args.min_distance,
        corpus_wall_cap_seconds=args.seconds, n=n, primary_variables=adapter.variables,
        expanded_constraints=len(adapter.entries), cnf=str(args.cnf.resolve()), cnf_sha256=cnf_hash,
        orientation_map=str(args.orientation_map.resolve()), orientation_map_sha256=map_hash,
        builder_sha256=digest_file(__file__), canonicalizer_sha256=digest_file(ROOT/'benchmarks/compare19_types.py'),
        fresh_corpus=str(fresh), fresh_database_sha256=digest_file(fresh/'corpus.sqlite'),
        fresh_manifest_sha256=digest_file(fresh/'manifest.json'), fresh_state=source_state,
        fresh_committed_models=len(fresh_records), historical_sources=sources,
        original_generator_cpu_seconds=source_manifest.get('generation_child_cpu_seconds'),
        original_generator_wall_seconds=source_manifest.get('generation_wall_seconds'),
        control_orientation=str(args.control_orientation.resolve()),
        control_orientation_sha256=digest_file(args.control_orientation), control_canonicalization=control,
        selection='Retain fresh commits first, then fixed historical source order and ascending line: initial SAT, satisfiable=true, original_solution only. Exclude the known positive-control canonical type, canonical duplicates, and primary Hamming distances below the registered minimum. No realization outcome filtering; no claim of uniform or all-fresh sampling.',
        validation_cnf='Original CNF only. Historical two-proof-cut generation is a separately disclosed reused stratum. No diversity or proof-cut clause enters benchmark flippability, feedback, or acceptance.',
        deadline='One validation child; parent wall watchdog terminates blocked native SAT calls. Committed rows survive interruption.',
        candidates=candidates, preselection_exclusions=ignored)
    output.mkdir(parents=True, exist_ok=False)
    db = connect(output/'corpus.sqlite')
    with db:
        db.executescript(SCHEMA)
        meta(db, 'registration', registration)
        meta(db, 'state', 'REGISTERED')
        event(db, 'REGISTERED', candidates=len(candidates), preselection_exclusions=len(ignored))
    db.close()
    write_manifest(output, dict(registration=registration, state='REGISTERED', accepted_models=0))
    return registration


def worker(output):
    from pysat.formula import CNF
    from pysat.solvers import Cadical195
    db = connect(output/'corpus.sqlite')
    registration = json.loads(db.execute("SELECT value FROM metadata WHERE key='registration'").fetchone()[0])
    if db.execute('SELECT count(*) FROM models').fetchone()[0]:
        raise ValueError('Combine worker refuses to overwrite committed models')
    begin, cpu_begin = time.monotonic(), time.process_time()
    with db:
        meta(db, 'state', 'VALIDATING')
        event(db, 'INITIALIZING')
    try:
        for key in ('cnf', 'orientation_map'):
            if digest_file(registration[key]) != registration[key+'_sha256']:
                raise ValueError(f'Registered input changed: {key}')
        adapter = OrientationMap(registration['orientation_map'], registration['n'])
        formula = CNF(from_file=registration['cnf'])
        selected, selected_types = [], set()
        control_key = canonical_key(registration['control_canonicalization'])
        with Cadical195(bootstrap_with=formula.clauses) as solver:
            with db:
                event(db, 'INITIALIZED', seconds=time.monotonic()-begin,
                      original_variables=formula.nv, original_clauses=len(formula.clauses))
            for index, candidate in enumerate(registration['candidates'], 1):
                primary, origin = candidate['primary_model'], candidate['origin']
                if len(selected) == registration['count']:
                    with db:
                        event(db, 'CANDIDATE_EXCLUDED', index=index, origin=origin, reason='TARGET_COUNT_FILLED')
                    continue
                orientations = adapter.orientations(primary)
                canonical = canonicalize(orientations)
                reason, nearest = exclusion(primary, canonical, selected, selected_types,
                                            control_key, registration['min_distance'])
                if reason:
                    with db:
                        event(db, 'CANDIDATE_EXCLUDED', index=index, origin=origin, reason=reason,
                              nearest_previous_primary_distance=nearest, canonicalization=canonical)
                    if origin['stratum'] == 'fresh' and reason != 'KNOWN_POSITIVE_CONTROL':
                        raise ValueError(f'Fresh committed model violates declared diversity: {reason}')
                    continue
                wall, cpu = time.monotonic(), time.process_time()
                with db:
                    event(db, 'VALIDATION_STARTED', index=index, origin=origin)
                if not solver.solve(assumptions=primary):
                    raise ValueError(f'Candidate {index} recorded SAT but original-CNF extension is UNSAT')
                full = solver.get_model()
                assigned = {abs(lit): lit for lit in full}
                if any(assigned.get(abs(lit)) != lit for lit in primary):
                    raise ValueError('Extension does not preserve primary assumptions')
                validation = validate_extension(formula.clauses, formula.nv, full)
                validation.update(original_cnf_sha256=registration['cnf_sha256'],
                                  solve_and_check_wall_seconds=time.monotonic()-wall,
                                  solve_and_check_cpu_seconds=time.process_time()-cpu,
                                  method='Fresh original-CNF solver, complete primary assumptions, explicit every-clause scan; no generation constraints')
                identifier = len(selected)+1
                primary_bytes = json.dumps(primary, separators=(',', ':')).encode()
                orientation_bytes = orientations.encode()
                generation = dict(origin=origin, selection_index=index,
                                  nearest_previous_primary_distance=nearest,
                                  elapsed_seconds=time.monotonic()-begin)
                with db:
                    db.execute('INSERT INTO models VALUES(?,?,?,?,?,?,?,?)', (
                        identifier, zlib.compress(primary_bytes, 6), zlib.compress(orientation_bytes, 6),
                        hashlib.sha256(primary_bytes).hexdigest(), hashlib.sha256(orientation_bytes).hexdigest(),
                        json.dumps(validation), json.dumps(generation), json.dumps(canonical)))
                    meta(db, 'accepted_models', identifier)
                    event(db, 'MODEL_COMMITTED', id=identifier, generation=generation, validation=validation)
                selected.append(dict(primary_model=primary))
                if canonical['supported']:
                    selected_types.add(canonical_key(canonical))
                print(json.dumps(dict(event='MODEL_COMMITTED', id=identifier, origin=origin,
                                      validation_wall_seconds=validation['solve_and_check_wall_seconds'])), flush=True)
        with db:
            state = 'COMPLETE' if len(selected) == registration['count'] else 'INSUFFICIENT_ELIGIBLE'
            meta(db, 'state', state)
            event(db, 'WORKER_FINISHED', state=state, wall_seconds=time.monotonic()-begin,
                  cpu_seconds=time.process_time()-cpu_begin)
    except BaseException as exc:
        with db:
            meta(db, 'state', 'ERROR')
            event(db, 'ERROR', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--min-distance', type=int, default=8)
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--cnf', type=Path, default=DEFAULT_CNF)
    parser.add_argument('--orientation-map', type=Path, default=DEFAULT_MAP)
    parser.add_argument('--control-orientation', type=Path, default=CONTROL)
    parser.add_argument('--historical-log', type=Path, action='append',
                        help='Explicit fixed-order source override, repeatable; each requires sibling settings.json')
    parser.add_argument('--_worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._worker:
        worker(args.output.resolve())
        return 0
    if args.fresh_corpus is None:
        parser.error('--fresh-corpus is required')
    if args.count < 1 or args.min_distance < 1 or not 0 < args.seconds <= 600 or not math.isfinite(args.seconds):
        parser.error('count/min-distance must be positive and seconds must be finite in (0, 600]')
    begin, cpu_begin = time.monotonic(), time.process_time()
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    output = args.output.resolve()
    registration = register(args, output)
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                '--output', str(output), '--_worker'], start_new_session=True)
    state = None
    def interrupted(*unused):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        process.wait(timeout=max(.001, args.seconds-(time.monotonic()-begin)))
    except subprocess.TimeoutExpired:
        state = 'TIME_LIMIT'
        stop_child(process)
    except KeyboardInterrupt:
        state = 'INTERRUPTED'
        stop_child(process)
    finally:
        signal.signal(signal.SIGTERM, previous)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    rows = list(load_models(output))
    db = connect(output/'corpus.sqlite')
    current = json.loads(db.execute("SELECT value FROM metadata WHERE key='state'").fetchone()[0])
    state = state or (current if process.returncode == 0 else 'ERROR')
    exclusions = registration['preselection_exclusions'] + [json.loads(row[0]) for row in db.execute(
        "SELECT payload FROM events WHERE event='CANDIDATE_EXCLUDED' ORDER BY id")]
    result = dict(registration=registration, state=state, accepted_models=len(rows),
        child_pid=process.pid, child_returncode=process.returncode,
        original_generator_cpu_seconds=registration['original_generator_cpu_seconds'],
        original_generator_wall_seconds=registration['original_generator_wall_seconds'],
        generation_child_cpu_seconds=registration['original_generator_cpu_seconds'],
        generation_wall_seconds=registration['original_generator_wall_seconds'],
        combine_wall_seconds=time.monotonic()-begin,
        combine_validation_child_cpu_seconds=after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime,
        combine_controller_cpu_seconds=time.process_time()-cpu_begin,
        validation_solve_and_check_cpu_seconds=math.fsum(row['validation']['solve_and_check_cpu_seconds'] for row in rows),
        strata=dict(Counter(row['generation']['origin']['stratum'] for row in rows)),
        exclusions=exclusions, exclusion_counts=dict(Counter(row['reason'] for row in exclusions)),
        hamming=distance_summary(rows, OrientationMap(registration['orientation_map'], registration['n'])),
        canonical_supported=sum(row['canonicalization']['supported'] for row in rows),
        canonical_unsupported=sum(not row['canonicalization']['supported'] for row in rows),
        supported_distinct_types=len({canonical_key(row['canonicalization']) for row in rows if row['canonicalization']['supported']}),
        corpus_database=str(output/'corpus.sqlite'),
        models=[{key: row[key] for key in ('id', 'primary_sha256', 'expanded_orientation_sha256',
                                         'validation', 'generation', 'canonicalization')} for row in rows])
    with db:
        meta(db, 'state', state)
        meta(db, 'summary', {k: v for k, v in result.items() if k not in ('models', 'registration')})
        event(db, 'CONTROLLER_FINISHED', state=state, accepted=len(rows))
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.execute('PRAGMA journal_mode=DELETE')
    db.close()
    write_manifest(output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('models', 'registration', 'exclusions')}), flush=True)
    return 0 if state == 'COMPLETE' else 130 if state == 'INTERRUPTED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
