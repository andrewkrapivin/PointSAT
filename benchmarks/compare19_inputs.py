#!/usr/bin/env python3
"""Freeze diverse SAT targets without inspecting any coordinate realization.

The public CLI owns a bounded subprocess: this PySAT CaDiCaL build does not
implement interrupt(). Only the child owns incremental generation constraints.
Consumers must use the original CNF, never those diversity constraints, for
flippability, feedback, or acceptance checks.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import signal
import sqlite3
import subprocess
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from improvements.pipeline.orientation_map import OrientationMap

DEFAULT_CNF = ROOT/'convex_hexagon_inside_19_3sym.cnf'
DEFAULT_MAP = ROOT/'improvements/symmetry19/variants/mapping.json'
SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE models(id INTEGER PRIMARY KEY,primary_model BLOB NOT NULL,
 orientations BLOB NOT NULL,primary_sha256 TEXT UNIQUE NOT NULL,
 expanded_orientation_sha256 TEXT UNIQUE NOT NULL,validation TEXT NOT NULL,
 generation TEXT NOT NULL,canonicalization TEXT NOT NULL);
CREATE TABLE events(id INTEGER PRIMARY KEY,event TEXT NOT NULL,payload TEXT NOT NULL);
"""


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    return db


def meta(db, key, value):
    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, json.dumps(value)))


def event(db, name, **values):
    db.execute('INSERT INTO events(event,payload) VALUES(?,?)',
               (name, json.dumps(dict(utc=utc(), **values))))


def load_models(path):
    """Read committed corpus rows; directories and corpus.sqlite are accepted.

    Yields id, primary_model (complete signed projection), orientations (full
    expanded Localizer text), both hashes, validation, and generation metadata.
    Reading is safe while the single generator child is still committing rows.
    """
    path = Path(path)
    if path.is_dir():
        path /= 'corpus.sqlite'
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        for row in db.execute('SELECT * FROM models ORDER BY id'):
            result = dict(row)
            result['primary_model'] = json.loads(zlib.decompress(result['primary_model']))
            result['orientations'] = zlib.decompress(result['orientations']).decode()
            for key in ('validation', 'generation', 'canonicalization'):
                result[key] = json.loads(result[key])
            yield result
    finally:
        db.close()


def expanded_signs(primary, adapter):
    truth = {abs(lit): lit > 0 for lit in primary}
    return bytes(truth[abs(literal)] == (literal > 0) for _, literal, _ in adapter.entries)


def hamming(a, b):
    if len(a) != len(b):
        raise ValueError('Hamming inputs differ in length')
    return sum(x != y for x, y in zip(a, b))


def distance_summary(models, adapter):
    primary = [bytes(lit > 0 for lit in row['primary_model']) for row in models]
    expanded = [expanded_signs(row['primary_model'], adapter) for row in models]
    result = {}
    for name, vectors in (('primary', primary), ('expanded', expanded)):
        values = [hamming(vectors[i], vectors[j]) for i in range(len(vectors)) for j in range(i)]
        result[name] = dict(pairs=len(values), minimum=min(values) if values else None,
                            maximum=max(values) if values else None,
                            mean=math.fsum(values)/len(values) if values else None,
                            histogram=dict(sorted(Counter(values).items())))
    return result


def distance_clauses(primary, minimum, top_id):
    """Fresh auxiliaries only; disagreement literal is the negated old value."""
    from pysat.card import CardEnc, EncType
    if not 1 <= minimum <= len(primary):
        raise ValueError('minimum distance must be in1..primary count')
    encoded = CardEnc.atleast(lits=[-lit for lit in primary], bound=minimum,
                             top_id=max(top_id, max(map(abs, primary))), encoding=EncType.seqcounter)
    return encoded.clauses, max(top_id, encoded.nv)


def validate_extension(clauses, nvars, model):
    """Check every original clause against an explicit complete assignment.

    Unmentioned variables are set false; this completion must still pass every
    clause. The digest is of nvars bytes, each0/1, in ascending variable order.
    Generation-only auxiliary variables are excluded from this certificate.
    """
    started = time.monotonic()
    truth = bytearray(nvars+1)
    for lit in model:
        if abs(lit) <= nvars:
            truth[abs(lit)] = lit > 0
    for index, clause in enumerate(clauses, 1):
        if not any(truth[abs(lit)] == (lit > 0) for lit in clause):
            raise ValueError(f'Solver extension violates original CNF clause{index}')
    return dict(valid=True, clauses_checked=len(clauses), violated_clauses=0, variables=nvars,
                full_extension_sha256=hashlib.sha256(truth[1:]).hexdigest(),
                digest_format='one byte0/1 for each original variable1..nvars; omitted variables=false',
                seconds=time.monotonic()-started)


def worker(output):
    from pysat.formula import CNF
    from pysat.solvers import Cadical195
    from benchmarks.compare19_types import canonicalize
    db = connect(output/'corpus.sqlite')
    registration = json.loads(db.execute("SELECT value FROM metadata WHERE key='registration'").fetchone()[0])
    if db.execute('SELECT count(*) FROM models').fetchone()[0]:
        raise ValueError('Worker refuses to resume or overwrite an existing corpus')
    begin, cpu_begin = time.monotonic(), time.process_time()
    with db:
        meta(db, 'state', 'GENERATING')
        event(db, 'INITIALIZING')
    for key in ('cnf', 'orientation_map'):
        if digest_file(registration[key]) != registration[key+'_sha256']:
            raise ValueError(f'Registered input changed before generation: {key}')
    adapter = OrientationMap(registration['orientation_map'], registration['n'])
    formula = CNF(from_file=registration['cnf'])
    if max(adapter.variables) > formula.nv:
        raise ValueError('Map references variables absent from original CNF')
    solver = Cadical195(bootstrap_with=formula.clauses)
    solver.configure({'seed': registration['seed'] & 0x7fffffff})
    rng = random.Random(registration['seed'])
    accepted, aux_top, total_calls = [], formula.nv, 0
    primary_variables, canonical_types = set(adapter.variables), set()
    isomorphic_rejections = 0
    try:
        with db:
            event(db, 'INITIALIZED', seconds=time.monotonic()-begin, original_variables=formula.nv,
                  original_clauses=len(formula.clauses), primary_variables=len(adapter.variables))
        status = 'COMPLETE'
        while len(accepted) < registration['count']:
            phases = [v if rng.getrandbits(1) else -v for v in adapter.variables]
            solver.set_phases(phases)
            solve_start, solve_cpu = time.monotonic(), time.process_time()
            calls = 0
            while True:
                # Conflict limits allow progress events. The parent wall
                # watchdog also bounds preprocessing and any unusually long call.
                solver.conf_budget(10000)
                solved = solver.solve_limited(expect_interrupt=False)
                total_calls += 1
                calls += 1
                if solved is not None:
                    break
                with db:
                    event(db, 'SOLVE_SLICE', next_model=len(accepted)+1, calls=calls,
                          elapsed_seconds=time.monotonic()-begin)
            solve_wall_seconds = time.monotonic()-solve_start
            solve_cpu_seconds = time.process_time()-solve_cpu
            if solved is False:
                status = 'DIVERSITY_EXHAUSTED'
                with db:
                    event(db, status, accepted=len(accepted),
                          note='UNSAT only under generation diversity constraints; not a geometric impossibility claim')
                break
            full = solver.get_model()
            assignment = {abs(lit): lit for lit in full if abs(lit) in primary_variables}
            primary = [assignment[v] for v in adapter.variables]
            nearest = min((hamming(primary, old) for old in accepted), default=None)
            if nearest is not None and nearest < registration['min_distance']:
                raise ValueError('Generation violated its declared pairwise primary distance')
            primary_bytes = json.dumps(primary, separators=(',', ':')).encode()
            orientation_bytes = adapter.orientations(primary).encode()
            canonical = canonicalize(orientation_bytes.decode())
            canonical_key = (canonical['n'], canonical.get('canonical_signs'))
            if canonical['supported'] and canonical_key in canonical_types:
                # This exclusion affects generation only; do not add a
                # geometric impossibility clause to the original formula.
                solver.add_clause([-lit for lit in primary])
                isomorphic_rejections += 1
                with db:
                    event(db, 'CANONICAL_DUPLICATE', primary_sha256=hashlib.sha256(primary_bytes).hexdigest(),
                          canonical_sha256=canonical['canonical_sha256'], rejected=isomorphic_rejections)
                continue
            validation = validate_extension(formula.clauses, formula.nv, full)
            identifier = len(accepted)+1
            generation = dict(solve_calls=calls, solve_wall_seconds=solve_wall_seconds,
                              solve_cpu_seconds=solve_cpu_seconds,
                              elapsed_seconds=time.monotonic()-begin, nearest_previous_primary_distance=nearest,
                              phase_sha256=hashlib.sha256(json.dumps(phases).encode()).hexdigest(),
                              generation_aux_top=aux_top)
            with db:
                db.execute('INSERT INTO models VALUES(?,?,?,?,?,?,?,?)',
                           (identifier, zlib.compress(primary_bytes, 6), zlib.compress(orientation_bytes, 6),
                            hashlib.sha256(primary_bytes).hexdigest(), hashlib.sha256(orientation_bytes).hexdigest(),
                            json.dumps(validation), json.dumps(generation), json.dumps(canonical)))
                meta(db, 'accepted_models', identifier)
                event(db, 'MODEL_COMMITTED', id=identifier, **generation)
            accepted.append(primary)
            if canonical['supported']:
                canonical_types.add(canonical_key)
            print(json.dumps(dict(event='MODEL_COMMITTED', id=identifier, **generation)), flush=True)
            if identifier < registration['count']:
                clauses, aux_top = distance_clauses(primary, registration['min_distance'], max(aux_top, solver.nof_vars()))
                solver.append_formula(clauses)
                with db:
                    event(db, 'DIVERSITY_CONSTRAINT_ADDED', model=identifier, clauses=len(clauses), aux_top=aux_top)
        with db:
            meta(db, 'state', status)
            event(db, 'WORKER_FINISHED', state=status, accepted=len(accepted), solve_calls=total_calls,
                  rejected_isomorphic=isomorphic_rejections,
                  wall_seconds=time.monotonic()-begin, cpu_seconds=time.process_time()-cpu_begin)
    except BaseException as exc:
        with db:
            meta(db, 'state', 'ERROR')
            event(db, 'ERROR', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        solver.delete()
        db.close()


def register(args, output):
    import pysat
    n = json.loads(args.orientation_map.read_text())['n']
    adapter = OrientationMap(args.orientation_map, n)
    if args.min_distance > len(adapter.variables):
        raise ValueError('Minimum distance exceeds primary variable count')
    registration = dict(schema_version=1, registered_utc=utc(), count=args.count, seed=args.seed,
                        min_distance=args.min_distance, corpus_wall_cap_seconds=args.seconds,
                        cnf=str(args.cnf.resolve()), cnf_sha256=digest_file(args.cnf),
                        orientation_map=str(args.orientation_map.resolve()),
                        orientation_map_sha256=digest_file(args.orientation_map), n=n,
                        primary_variables=adapter.variables, expanded_constraints=len(adapter.entries),
                        generator_sha256=digest_file(__file__),
                        canonicalizer_sha256=digest_file(ROOT/'benchmarks/compare19_types.py'),
                        python_version=sys.version, python_sat_version=pysat.__version__, solver='Cadical195',
                        selection='All-fresh incremental SAT; fresh random primary phases; no coordinates, realization results, or known witness are consulted. Not uniform sampling; not an isomorphism classification.',
                        diversity='At least min_distance primary disagreements from every earlier accepted model; generation-only sequential-counter constraints.',
                        canonical_dedup='Reject supported exact canonical-type duplicates under arbitrary relabeling/reflection. Unsupported cases remain tagged and are not claimed nonisomorphic.',
                        validation_cnf='Original input CNF only; generation constraints must NOT enter flippability, feedback, or audits.',
                        deadline='Parent subprocess watchdog; installed Cadical195 interrupt is unsupported. Completed SQLite transactions survive worker termination.')
    output.mkdir(parents=True, exist_ok=False)
    with connect(output/'corpus.sqlite') as db:
        db.executescript(SCHEMA)
        meta(db, 'registration', registration)
        meta(db, 'state', 'REGISTERED')
        event(db, 'REGISTERED')
    # Close explicitly: Connection context managers only commit, not close.
    db.close()
    write_manifest(output, dict(registration=registration, state='REGISTERED', accepted_models=0))
    return registration


def write_manifest(output, value):
    pending = output/'manifest.tmp'
    pending.write_text(json.dumps(value, indent=2)+'\n')
    pending.replace(output/'manifest.json')


def stop_child(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20260907)
    parser.add_argument('--min-distance', type=int, default=8)
    parser.add_argument('--seconds', type=float, default=1800)
    parser.add_argument('--cnf', type=Path, default=DEFAULT_CNF)
    parser.add_argument('--orientation-map', type=Path, default=DEFAULT_MAP)
    parser.add_argument('--_worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._worker:
        # No Python signal handler in the child: even a blocked native call
        # must terminate promptly on the parent's SIGTERM.
        worker(args.output.resolve())
        return 0
    if args.count < 1 or args.min_distance < 1 or args.seconds <= 0 or not math.isfinite(args.seconds):
        parser.error('count/min-distance/seconds must be finite positive values')
    begin, usage = time.monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
    output = args.output.resolve()
    registration = register(args, output)
    command = [sys.executable, str(Path(__file__).resolve()), '--output', str(output), '--_worker']
    process = subprocess.Popen(command, start_new_session=True)
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
    records = list(load_models(output))
    adapter = OrientationMap(registration['orientation_map'], registration['n'])
    db = connect(output/'corpus.sqlite')
    current = json.loads(db.execute("SELECT value FROM metadata WHERE key='state'").fetchone()[0])
    state = state or (current if process.returncode == 0 else 'ERROR')
    result = dict(registration=registration, state=state, accepted_models=len(records),
                  child_pid=process.pid, child_returncode=process.returncode, generation_wall_seconds=time.monotonic()-begin,
                  generation_child_cpu_seconds=after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime,
                  hamming=distance_summary(records, adapter),
                  canonical_supported=sum(row['canonicalization']['supported'] for row in records),
                  canonical_unsupported=sum(not row['canonicalization']['supported'] for row in records),
                  supported_distinct_types=len({(row['canonicalization']['n'], row['canonicalization']['canonical_signs']) for row in records if row['canonicalization']['supported']}),
                  canonical_rejections=db.execute("SELECT count(*) FROM events WHERE event='CANONICAL_DUPLICATE'").fetchone()[0],
                  corpus_database=str(output/'corpus.sqlite'),
                  models=[{key: row[key] for key in ('id', 'primary_sha256', 'expanded_orientation_sha256', 'validation', 'generation', 'canonicalization')} for row in records])
    with db:
        meta(db, 'state', state)
        meta(db, 'summary', {key: value for key, value in result.items() if key not in ('models', 'registration')})
        event(db, 'CONTROLLER_FINISHED', state=state, accepted=len(records))
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.execute('PRAGMA journal_mode=DELETE')
    db.close()
    write_manifest(output, result)
    print(json.dumps({key: value for key, value in result.items() if key not in ('models', 'registration')}), flush=True)
    return 0 if state == 'COMPLETE' else 130 if state == 'INTERRUPTED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
