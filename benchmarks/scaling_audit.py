#!/usr/bin/env python3
"""Read-only integrity audit for compare19 / compare_families registrations.

No benchmark, geometry predicate, native executable, or SAT solver is imported
or run. SQLite is opened mode=ro and query_only, with one consistent snapshot.
Stored zlib artifacts are streamed and checked against their recorded SHA256.
This checks evidence consistency, not geometric truth or realizability.

Exit 0 means no integrity fault (a study may still be explicitly PENDING).
Exit 1 means an integrity fault. Output must be a NEW file and is never replaced.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fcntl
import hashlib
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import sqlite3
import time
import zlib


CHUNK = 64 * 1024


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(CHUNK), b''):
            digest.update(part)
    return digest.hexdigest()


def bytes_sha(data):
    return hashlib.sha256(data).hexdigest()


def colex_triples(n):
    return {a+(b-1)*(b-2)//2+(c-1)*(c-2)*(c-3)//6: (a, b, c)
            for a, b, c in itertools.combinations(range(1, n+1), 3)}


def orientation_bytes(model, n, mapping=None):
    """Independent serialization of the two registered orientation interfaces."""
    truth = {}
    for literal in model:
        if type(literal) is not int or not literal or abs(literal) in truth:
            raise ValueError('Primary model contains zero, noninteger, or duplicate variables')
        truth[abs(literal)] = literal > 0
    if mapping is not None:
        if mapping['n'] != n:
            raise ValueError('Mapping n mismatch')
        expected = set(itertools.combinations(range(1, n+1), 3))
        seen, variables, rows = set(), set(), []
        for entry in mapping['entries']:
            triple, literal = tuple(entry['triple']), entry['literal']
            if triple not in expected or triple in seen or type(literal) is not int or not literal:
                raise ValueError('Malformed signed mapping')
            seen.add(triple)
            variables.add(abs(literal))
            if abs(literal) in truth:
                positive = truth[abs(literal)] == (literal > 0)
                rows.append(f"{'A' if positive else 'B'}_{triple}\n")
        if seen != expected or not set(truth) <= variables:
            raise ValueError('Incomplete mapping or nonprimary model variable')
    else:
        triples = colex_triples(n)
        if not set(truth) <= set(triples):
            raise ValueError('Nonprimary orientation variable')
        rows = [f"{'A' if literal > 0 else 'B'}_{triples[abs(literal)]}\n" for literal in model]
    return ''.join(rows).encode()


def streamed_artifact(db, rowid, maximum):
    """Hash a bounded decompressed artifact without allocating it all at once."""
    digest, total = hashlib.sha256(), 0
    decoder = zlib.decompressobj()
    with db.blobopen('artifacts', 'data', rowid, readonly=True) as blob:
        for compressed in iter(lambda: blob.read(CHUNK), b''):
            pending = compressed
            while pending:
                part = decoder.decompress(pending, CHUNK)
                pending = decoder.unconsumed_tail
                total += len(part)
                if total > maximum:
                    raise ValueError('Artifact exceeds the configured expanded-byte bound')
                digest.update(part)
                if decoder.unused_data:
                    raise ValueError('Trailing data after the zlib stream')
        part = decoder.flush()
        total += len(part)
        if total > maximum:
            raise ValueError('Artifact exceeds the configured expanded-byte bound')
        digest.update(part)
    if not decoder.eof:
        raise ValueError('Truncated zlib artifact')
    return digest.hexdigest(), total


def controller_active(directory):
    lock = directory/'run.lock'
    if not lock.exists():
        return False
    with lock.open('r') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


class IntegrityAudit:
    def __init__(self, maximum_artifact_bytes=256*1024*1024, seconds=600):
        self.maximum_artifact_bytes = maximum_artifact_bytes
        self.deadline = time.monotonic()+seconds
        self.faults, self.pending, self.diagnostics = [], [], []
        self.hashes = {}

    def check_time(self):
        if time.monotonic() > self.deadline:
            raise TimeoutError('Integrity-audit time bound reached; audit is incomplete')

    def fault(self, message, **details):
        self.faults.append(dict(message=message, **details))

    def check(self, passed, message, **details):
        if not passed:
            self.fault(message, **details)

    def file_hash(self, path, expected=None, role=None):
        self.check_time()
        path = Path(path).resolve()
        try:
            stat = path.stat()
            key = (str(path), stat.st_size, stat.st_mtime_ns)
            if key not in self.hashes:
                self.hashes[key] = sha_file(path)
            actual = self.hashes[key]
            if expected is not None:
                self.check(actual == expected, 'Source/frozen SHA256 mismatch', path=str(path), role=role)
            return actual
        except OSError as error:
            self.fault('Missing or unreadable registered file', path=str(path), role=role, error=str(error))
            return None

    def run(self, registration):
        begin = time.monotonic()
        registration = Path(registration).resolve()
        directory = registration.parent
        config = json.loads(registration.read_text())
        family_study = bool(config.get('cases') and 'family' in config['cases'][0])
        self.kind = 'paper_families' if family_study else 'symmetry19'
        self.config, self.cases, self.mapping = config, {}, None
        expected = set()
        for case in config['cases']:
            self.check(case['id'] not in self.cases, 'Duplicate registered case ID', case_id=case['id'])
            self.cases[case['id']] = case
            jobs = case['condition_order' if family_study else 'experiments']
            actual = [(job['arm'], job['budget']) for job in jobs]
            desired = {(arm, budget) for arm in config['arms'] for budget in config['budgets']}
            self.check(len(actual) == len(set(actual)) and set(actual) == desired,
                       'Registered case conditions are not the complete arm/budget product', case_id=case['id'])
            for arm, budget in actual:
                self.check(isinstance(budget, (int, float)) and math.isfinite(budget) and budget > 0,
                           'Invalid registered native budget', case_id=case['id'])
                expected.add((case['id'], arm, budget))
        for name, digest in config['frozen_sha256'].items():
            if Path(name).name != name:
                self.fault('Unsafe frozen dependency name', name=name)
                continue
            self.file_hash(directory/'frozen'/name, digest, 'frozen')
        if family_study:
            for case in self.cases.values():
                self.file_hash(case['cnf'], case['cnf_sha256'], 'original_CNF')
                self.file_hash(case['orientation'], case['orientation_sha256'], 'original_orientation')
        else:
            self.file_hash(config['cnf'], config['cnf_sha256'], 'original_CNF')
            self.mapping = json.loads(Path(config['paths']['mapping']).read_text())
        # Executed paths must themselves be covered by the registered frozen set.
        frozen_paths = {str((directory/'frozen'/name).resolve()) for name in config['frozen_sha256']}
        for role, path in config['paths'].items():
            self.check(str(Path(path).resolve()) in frozen_paths,
                       'Runtime path not covered by frozen manifest', role=role, path=path)
        active = controller_active(directory)
        database = directory/'results.sqlite'
        result = {'registration': str(registration), 'registration_sha256': sha_file(registration),
                  'kind': self.kind, 'controller_active_at_start': active,
                  'registered_conditions': len(expected), 'hash_checked_files': len(self.hashes),
                  'geometric_predicates_rerun': False, 'SAT_calls': 0}
        if not database.exists():
            self.pending.append({'message': 'Results database not created yet'})
            return self.finish(result, begin)
        db = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            integrity = [row[0] for row in db.execute('PRAGMA quick_check')]
            self.check(integrity == ['ok'], 'SQLite structural quick_check failed', details=integrity)
            preparation = {row['case_id']: json.loads(row['record']) for row in db.execute('SELECT * FROM preparation')}
            self.initial, self.full = {}, {}
            for identifier, case in self.cases.items():
                n = case['n'] if family_study else 19
                full = orientation_bytes(case['primary_model'], n, self.mapping)
                required_variables = ({abs(entry['literal']) for entry in self.mapping['entries']}
                                      if self.mapping is not None else set(colex_triples(n)))
                self.check({abs(literal) for literal in case['primary_model']} == required_variables,
                           'Registered full target has an incomplete primary projection', case_id=identifier)
                self.full[identifier] = bytes_sha(full)
                if not family_study and case.get('expanded_orientation_sha256'):
                    self.check(self.full[identifier] == case['expanded_orientation_sha256'],
                               'Registered expanded orientation differs from its primary model', case_id=identifier)
                if identifier in preparation:
                    partial = preparation[identifier]['partial_model']
                    full_literals = set(case['primary_model'])
                    self.check(set(partial) <= full_literals, 'Prepared target changes rather than omits initial literals', case_id=identifier)
                    if 'flippables' in preparation[identifier]:
                        omitted = {abs(literal) for literal in full_literals-set(partial)}
                        self.check(omitted == set(preparation[identifier]['flippables']),
                                   'Prepared omission set differs from recorded flippable variables', case_id=identifier)
                    self.initial[identifier] = bytes_sha(orientation_bytes(partial, n, self.mapping))
            for identifier in preparation:
                self.check(identifier in self.cases, 'Preparation for unregistered case', case_id=identifier)
            rows = list(db.execute('SELECT id,case_id,arm,budget,complete,record FROM trials ORDER BY id'))
            records = {}
            complete_keys, input_by_case = defaultdict(list), defaultdict(set)
            diagnostics = Counter()
            for row in rows:
                self.check_time()
                key = (row['case_id'], row['arm'], row['budget'])
                self.check(key in expected, 'Unregistered trial condition', trial_id=row['id'], condition=key)
                self.check(row['complete'] in (0, 1), 'Invalid complete flag', trial_id=row['id'])
                record = json.loads(row['record'])
                records[row['id']] = (row, record)
                if row['complete']:
                    complete_keys[key].append(row['id'])
                    self.check_record(row, record, input_by_case, diagnostics)
                else:
                    diagnostics['incomplete_attempts'] += 1
                    if record.get('status') == 'RUNNING':
                        diagnostics['inflight_or_abandoned_attempts'] += 1
                        work = record.get('workspace', record.get('work_directory'))
                        if work and not Path(work).is_dir():
                            self.diagnostics.append({'message': 'Incomplete attempt workspace unavailable', 'trial_id': row['id'], 'path': work})
            for key, identifiers in complete_keys.items():
                self.check(len(identifiers) == 1, 'Duplicate completed condition', condition=key, trial_ids=identifiers)
            for identifier, values in input_by_case.items():
                self.check(len(values) == 1, 'Unmatched common initial targets across arms/budgets', case_id=identifier)
            artifacts = defaultdict(dict)
            compressed_total = expanded_total = artifact_count = 0
            for artifact in db.execute('SELECT rowid,trial_id,name,sha256,length(data) AS size FROM artifacts ORDER BY rowid'):
                self.check_time()
                artifact_count += 1
                compressed_total += artifact['size']
                identifier, name = artifact['trial_id'], artifact['name']
                self.check(identifier in records, 'Orphan artifact', trial_id=identifier, artifact=name)
                path = PurePosixPath(name)
                self.check(not path.is_absolute() and '..' not in path.parts and str(path) == name,
                           'Unsafe artifact path', trial_id=identifier, artifact=name)
                try:
                    digest, expanded = streamed_artifact(db, artifact['rowid'], self.maximum_artifact_bytes)
                    expanded_total += expanded
                    self.check(digest == artifact['sha256'], 'Compressed artifact SHA256 mismatch', trial_id=identifier, artifact=name)
                    artifacts[identifier][name] = digest
                except (ValueError, zlib.error, sqlite3.Error) as error:
                    self.fault('Unreadable or invalid compressed artifact', trial_id=identifier, artifact=name, error=str(error))
            for identifier, (row, record) in records.items():
                if row['complete']:
                    self.check_artifacts(row, record, artifacts[identifier])
            for event in db.execute("SELECT record FROM events WHERE event='START'"):
                event = json.loads(event[0])
                affinity = event.get('affinity', [])
                self.check(event.get('workers') in (1, 2) and 0 < len(affinity) <= 2 and len(set(affinity)) == len(affinity),
                           'Recorded controller exceeds two CPU slots or has invalid affinity', event=event)
            missing = sorted(expected-set(complete_keys))
            if missing:
                self.pending.append({'message': 'Registered conditions remain unfinished', 'count': len(missing), 'first_conditions': missing[:100]})
            unresolved_attempts = sum(not row['complete'] and
                                      (row['case_id'], row['arm'], row['budget']) not in complete_keys
                                      for row in rows)
            if unresolved_attempts:
                self.pending.append({'message': 'Incomplete/abandoned attempts without a completed replacement', 'count': unresolved_attempts})
            diagnostics['superseded_incomplete_attempts'] = diagnostics['incomplete_attempts']-unresolved_attempts
            result.update(attempted_trials=len(rows), completed_rows=sum(row['complete'] for row in rows),
                          completed_conditions=len(complete_keys), pending_conditions=len(missing),
                          artifacts_checked=artifact_count, compressed_artifact_bytes=compressed_total,
                          expanded_artifact_bytes=expanded_total, diagnostics_counts=dict(diagnostics))
            result['summary'] = self.check_summary(db, directory, expected, complete_keys, active)
            db.rollback()
        finally:
            db.close()
        return self.finish(result, begin)

    def check_record(self, row, record, inputs, diagnostics):
        identifier = row['id']
        case = self.cases.get(row['case_id'])
        if case is None:
            return
        for key in ('case_id', 'arm'):
            self.check(record.get(key) == row[key], 'Trial JSON/SQL condition mismatch', trial_id=identifier, field=key)
        budget_field = 'budget' if self.kind == 'paper_families' else 'budget_seconds'
        self.check(record.get(budget_field) == row['budget'], 'Trial JSON/SQL budget mismatch', trial_id=identifier)
        self.check(record.get('seed') == case['seed'], 'Trial seed differs from registration', trial_id=identifier)
        if self.kind == 'paper_families':
            self.check(record.get('family') == case['family'], 'Wrong registered family', trial_id=identifier)
        field = 'initial_target_sha256' if self.kind == 'paper_families' else 'input_sha256'
        inputs[row['case_id']].add(record.get(field))
        self.check(row['case_id'] in self.initial and record.get(field) == self.initial.get(row['case_id']),
                   'Common initial target differs from preparation', trial_id=identifier)
        feedback = 'feedback' in row['arm']
        intended = 'stage1.real' if feedback else 'stage0.real'
        recorded_final = record.get('final_checkpoint')
        self.check(recorded_final in (None, intended), 'Wrong planned final checkpoint', trial_id=identifier)
        checks = record.get('audits', [])
        names = [item['checkpoint'] for item in checks if item.get('checkpoint') is not None]
        self.check(len(names) == len(set(names)), 'Duplicate checkpoint audit', trial_id=identifier)
        final = next((item for item in checks if item.get('checkpoint') == intended), {})
        primary = bool(final.get('valid_geometry')) if recorded_final == intended else False
        any_saved = any(bool(item.get('valid_geometry')) for item in checks if item.get('checkpoint') is not None)
        self.check(record.get('primary_valid_geometry') is primary, 'Final-checkpoint primary result inconsistent', trial_id=identifier)
        self.check(record.get('any_saved_valid_geometry') is any_saved, 'Any-checkpoint secondary result inconsistent', trial_id=identifier)
        self.check(not record.get('externally_interrupted'), 'Interrupted attempt incorrectly marked complete', trial_id=identifier)
        total_budget = 0
        for index, stage in enumerate(record.get('stages', [])):
            expected_seed = case['seed']+(index if self.kind == 'symmetry19' and feedback else 0)
            self.check(stage.get('seed') == expected_seed, 'Native stage seed differs from protocol', trial_id=identifier, stage=index)
            expected_budget = row['budget']/(2 if feedback else 1)
            self.check(stage.get('native_budget_seconds') == expected_budget, 'Native stage allowance differs from protocol', trial_id=identifier, stage=index)
            total_budget += stage.get('native_budget_seconds', 0)
            self.check(stage.get('file') == f'stage{index}.real', 'Native checkpoint ordering mismatch', trial_id=identifier, stage=index)
            command = stage.get('command', [])
            try:
                self.check(command[command.index('-t')+1] == '1', 'Native invocation is not single-threaded', trial_id=identifier)
                self.check(int(command[command.index('-s')+1]) == expected_seed, 'Command seed differs from recorded seed', trial_id=identifier)
                executable = self.config['paths']['original' if row['arm'] == 'original' else 'improved']
                self.check(command[0] == executable, 'Wrong frozen native executable', trial_id=identifier)
            except (ValueError, IndexError):
                self.fault('Incomplete native command metadata', trial_id=identifier, stage=index)
            diagnostics['forced_native_kills'] += bool(stage.get('forced_kill'))
            diagnostics['missing_native_outputs'] += not stage.get('output_saved', False)
        self.check(total_budget <= row['budget']+1e-9, 'Native stage allowances exceed the registered total', trial_id=identifier)
        diagnostics['error_trials'] += record.get('status') in ('ERROR', 'NO_CHECKPOINT', 'MISSING_OUTPUT')
        diagnostics['worker_watchdogs'] += bool(record.get('overhead_watchdog'))
        diagnostics['audit_watchdogs'] += bool(record.get('audit_watchdog'))
        diagnostics['audit_errors'] += sum('audit_error' in item for item in checks)

    def check_artifacts(self, row, record, artifacts):
        identifier, case_id = row['id'], row['case_id']
        self.check(artifacts.get('initial.or') == self.initial.get(case_id), 'Stored initial target missing or mismatched', trial_id=identifier)
        self.check(artifacts.get('full.or') == self.full.get(case_id), 'Stored full target missing or mismatched', trial_id=identifier)
        for stage in record.get('stages', []):
            self.check(bool(stage.get('output_saved')) == (stage.get('file') in artifacts),
                       'Native saved-output flag disagrees with artifacts', trial_id=identifier, checkpoint=stage.get('file'))
        for item in record.get('audits', []):
            checkpoint = item.get('checkpoint')
            if item.get('valid_geometry'):
                self.check(checkpoint in artifacts, 'Accepted checkpoint artifact is missing', trial_id=identifier, checkpoint=checkpoint)
            signature = item.get('input_signature', {})
            real_hash = signature.get('real_sha256', item.get('real_sha256'))
            target_hash = signature.get('target_sha256', item.get('source_full_target_sha256'))
            if real_hash:
                self.check(real_hash == artifacts.get(checkpoint), 'Audited coordinates differ from stored checkpoint', trial_id=identifier, checkpoint=checkpoint)
            if target_hash:
                self.check(target_hash == artifacts.get('full.or'), 'Audited target differs from stored full target', trial_id=identifier)

    def check_summary(self, db, directory, expected, complete_keys, active):
        path = directory/'summary.json'
        if not path.exists():
            self.pending.append({'message': 'Summary has not been written'})
            return {'status': 'PENDING_MISSING'}
        summary = json.loads(path.read_text())
        mismatches = []

        def equal(actual, expected_value, location):
            if actual != expected_value:
                mismatches.append({'location': location,
                                   'reported': sorted(actual) if isinstance(actual, set) else actual,
                                   'independent': sorted(expected_value) if isinstance(expected_value, set) else expected_value})

        total_rows = db.execute('SELECT COUNT(*) FROM trials').fetchone()[0]
        incomplete = db.execute('SELECT COUNT(*) FROM trials WHERE complete=0').fetchone()[0]
        equal(summary.get('registered_trials'), len(expected), 'registered_trials')
        equal(summary.get('completed_trials'), len(complete_keys), 'completed_trials')
        equal(summary.get('complete'), len(complete_keys) == len(expected), 'complete')
        for field, value in (('attempted_trials', total_rows), ('incomplete_attempts', incomplete)):
            if field in summary:
                equal(summary[field], value, field)
        family_expr = "json_extract(record,'$.family')" if self.kind == 'paper_families' else "'symmetry19'"
        groups = {(row['family'], row['arm'], row['budget']): row for row in db.execute(f"""
            SELECT {family_expr} AS family,arm,budget,COUNT(*) AS trials,
                   SUM(COALESCE(json_extract(record,'$.primary_valid_geometry'),0)) AS valid_final,
                   SUM(COALESCE(json_extract(record,'$.any_saved_valid_geometry'),0)) AS valid_any_checkpoint,
                   SUM(COALESCE(json_extract(record,'$.overhead_watchdog'),0)) AS watchdog_trials,
                   SUM(COALESCE(json_extract(record,'$.audit_watchdog'),0)) AS audit_watchdog_trials
            FROM trials WHERE complete=1 GROUP BY family,arm,budget""")}
        families = sorted({case.get('family', 'symmetry19') for case in self.cases.values()})
        if self.kind == 'paper_families':
            equal(set(summary.get('families', {})), set(families), 'family_groups')
            protocol_pairs = [('original', 'v6_plain'), ('v6_plain', 'v6_line10'),
                              ('v6_plain', 'v6_line10_pair10'), ('v6_plain', 'v6_feedback')]
        else:
            protocol_pairs = [('original', 'improved_fixed'), ('original', 'improved_feedback'),
                              ('improved_fixed', 'improved_feedback')]
        expected_pairs = {first+'__'+second for first, second in protocol_pairs
                          if first in self.config['arms'] and second in self.config['arms']}
        pair_names = []
        for family in families:
            for budget in self.config['budgets']:
                try:
                    budgets = summary['families'][family]['budgets'] if self.kind == 'paper_families' else summary['budgets']
                    keys = [key for key in budgets if float(key) == budget]
                    if len(keys) != 1:
                        raise ValueError('Missing or duplicate budget summary')
                    group = budgets[keys[0]]
                    equal(set(group['arms']), set(self.config['arms']), f'{family}/{budget}/arm_groups')
                    equal(set(group['pairs']), expected_pairs, f'{family}/{budget}/pair_groups')
                    for arm in self.config['arms']:
                        reported = group['arms'][arm]
                        independent = groups.get((family, arm, budget), {})
                        for field in ('trials', 'valid_final', 'valid_any_checkpoint', 'watchdog_trials', 'audit_watchdog_trials'):
                            equal(reported.get(field), independent[field] if independent else 0,
                                  f'{family}/{budget}/{arm}/{field}')
                    for pair, reported in group['pairs'].items():
                        first, second = pair.split('__')
                        pair_names.append(pair)
                        family_filter = "AND json_extract(a.record,'$.family')=?" if self.kind == 'paper_families' else ''
                        values = [first, second, budget]+([family] if family_filter else [])
                        joined = db.execute(f"""SELECT
                            json_extract(a.record,'$.primary_valid_geometry') AS x,
                            json_extract(b.record,'$.primary_valid_geometry') AS y
                            FROM trials a JOIN trials b ON a.case_id=b.case_id AND a.budget=b.budget
                            WHERE a.complete=1 AND b.complete=1 AND a.arm=? AND b.arm=? AND a.budget=? {family_filter}""", values)
                        counts = dict(pairs=0, first_only=0, second_only=0, both=0, neither=0)
                        for pair_row in joined:
                            x, y = pair_row
                            counts['pairs'] += 1
                            counts['both' if x and y else 'first_only' if x else 'second_only' if y else 'neither'] += 1
                        equal(reported, counts, f'{family}/{budget}/{pair}')
                except (KeyError, ValueError, TypeError) as error:
                    mismatches.append({'location': f'{family}/{budget}', 'error': str(error)})
        if mismatches:
            if active:
                self.pending.append({'message': 'Summary differs from the live SQLite snapshot; recheck after controller stops',
                                     'mismatches': mismatches})
                status = 'PENDING_LIVE_SNAPSHOT'
            else:
                self.fault('Published summary differs from independent SQL aggregates', mismatches=mismatches)
                status = 'MISMATCH'
        else:
            status = 'MATCHED'
        return {'status': status, 'sha256': sha_file(path), 'SQL_groups': len(groups),
                'paired_comparisons_checked': len(pair_names), 'mismatch_count': len(mismatches)}

    def finish(self, result, begin):
        result.update(status='FAILED' if self.faults else 'PENDING' if self.pending else 'PASSED',
                      integrity_ok=not self.faults, faults=self.faults, pending=self.pending,
                      diagnostics=self.diagnostics, wall_seconds=time.monotonic()-begin)
        return result


def audit_registration(registration, *, maximum_artifact_bytes=256*1024*1024, seconds=600):
    auditor = IntegrityAudit(maximum_artifact_bytes, seconds)
    try:
        return auditor.run(registration)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, TimeoutError) as error:
        # A bounded or malformed-input audit must not silently claim integrity.
        auditor.fault('Integrity audit could not finish', error=f'{type(error).__name__}: {error}')
        return auditor.finish({'registration': str(Path(registration).resolve()), 'geometric_predicates_rerun': False, 'SAT_calls': 0}, time.monotonic())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True, help='NEW JSON output path; never overwritten')
    parser.add_argument('--seconds', type=float, default=600, help='Per-study integrity-audit wall bound')
    parser.add_argument('--max-artifact-mib', type=int, default=256)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; specify a NEW path')
    if not math.isfinite(args.seconds) or args.seconds <= 0 or args.max_artifact_mib < 1:
        parser.error('Positive finite time and artifact limits required')
    studies = [audit_registration(path, maximum_artifact_bytes=args.max_artifact_mib*1024*1024,
                                 seconds=args.seconds) for path in args.registration]
    result = {'integrity_ok': all(study['integrity_ok'] for study in studies),
              'status': 'FAILED' if any(not s['integrity_ok'] for s in studies)
              else 'PENDING' if any(s['status'] == 'PENDING' for s in studies) else 'PASSED',
              'auditor_sha256': sha_file(__file__), 'studies': studies}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output),
                      'studies': len(studies), 'integrity_ok': result['integrity_ok']}))
    return 0 if result['integrity_ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
