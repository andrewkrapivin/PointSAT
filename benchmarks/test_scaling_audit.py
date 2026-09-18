"""Tiny self-contained integrity fixtures; no geometry/native/SAT execution."""
import hashlib
import fcntl
import io
import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import zlib

from benchmarks.scaling_audit import audit_registration, main, streamed_artifact


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ScalingIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-scaling-audit-test-')
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, paper=False, finished=True):
        folder = self.directory
        frozen = folder/'frozen'
        frozen.mkdir()
        n = 4 if paper else 19
        triples = [(a, b, c) for c in range(3, n+1) for b in range(2, c) for a in range(1, b)]
        primary = list(range(1, len(triples)+1))
        mapping = {'n': n, 'primary_variables': len(primary),
                   'entries': [{'triple': list(triple), 'literal': i+1} for i, triple in enumerate(triples)]}
        files = {'original': b'untouched native fixture', 'improved': b'improved native fixture',
                 'verifier': b'verifier fixture never executed', 'mapping': json.dumps(mapping).encode()}
        for name, content in files.items():
            (frozen/name).write_bytes(content)
        full = ''.join(f'A_{triple}\n' for triple in triples).encode()
        initial = ''.join(f'A_{triple}\n' for triple in triples[:-1]).encode()
        source = folder/'source.or'
        source.write_bytes(full)
        cnf = folder/'source.cnf'
        cnf.write_text(f'p cnf {len(primary)} 1\n1 0\n')
        arms = ['original', 'v6_plain', 'v6_feedback'] if paper else ['original', 'improved_fixed', 'improved_feedback']
        budget = 10
        case = {'id': 0, 'seed': 17, 'primary_model': primary}
        if paper:
            case.update(family='mixed23', n=n, cnf=str(cnf), cnf_sha256=digest(cnf.read_bytes()),
                        orientation=str(source), orientation_sha256=digest(full),
                        condition_order=[{'arm': arm, 'budget': budget} for arm in arms])
        else:
            case.update(experiments=[{'arm': arm, 'budget': budget} for arm in arms],
                        expanded_orientation_sha256=digest(full))
        config = {'cases': [case], 'arms': arms, 'budgets': [budget],
                  'paths': {name: str(frozen/name) for name in files},
                  'frozen_sha256': {name: digest(content) for name, content in files.items()},
                  'cnf': str(cnf), 'cnf_sha256': digest(cnf.read_bytes())}
        registration = folder/'registration.json'
        registration.write_text(json.dumps(config))
        db = sqlite3.connect(folder/'results.sqlite')
        db.executescript('''
            CREATE TABLE preparation(case_id INTEGER PRIMARY KEY,record TEXT);
            CREATE TABLE trials(id INTEGER PRIMARY KEY,case_id INTEGER,arm TEXT,budget REAL,complete INTEGER,record TEXT);
            CREATE TABLE artifacts(trial_id INTEGER,name TEXT,sha256 TEXT,data BLOB,PRIMARY KEY(trial_id,name));
            CREATE TABLE events(id INTEGER PRIMARY KEY,event TEXT,record TEXT);
        ''')
        db.execute('INSERT INTO preparation VALUES(?,?)', (0, json.dumps({'partial_model': primary[:-1]})))
        db.execute('INSERT INTO events VALUES(?,?,?)', (1, 'START', json.dumps({'workers': 2, 'affinity': [0, 1]})))
        records = []
        if finished:
            for identifier, arm in enumerate(arms, 1):
                feedback = 'feedback' in arm
                stages, audits = [], []
                artifacts = {'initial.or': initial, 'full.or': full, 'nested/late-audit.json': b'{"checked":true}'}
                for index in range(2 if feedback else 1):
                    name = f'stage{index}.real'
                    artifacts[name] = f'opaque printed-coordinate fixture {identifier} {index}'.encode()
                    seed = case['seed']+(index if feedback and not paper else 0)
                    stages.append({'file': name, 'seed': seed, 'native_budget_seconds': budget/(2 if feedback else 1),
                                   'command': [config['paths']['original' if arm == 'original' else 'improved'],
                                               'target.or', '-t', '1', '-s', str(seed)],
                                   'output_saved': True, 'forced_kill': False})
                    audits.append({'checkpoint': name, 'valid_geometry': arm == 'original' or (feedback and index == 0),
                                   'input_signature': {'real_sha256': digest(artifacts[name]), 'target_sha256': digest(full)}})
                record = {'case_id': 0, 'arm': arm, 'seed': case['seed'], 'status': 'FINISHED',
                          'stages': stages, 'audits': audits,
                          'final_checkpoint': 'stage1.real' if feedback else 'stage0.real',
                          'primary_valid_geometry': arm == 'original',
                          'any_saved_valid_geometry': arm == 'original' or feedback,
                          'externally_interrupted': False, 'overhead_watchdog': False, 'audit_watchdog': False}
                if paper:
                    record.update(family='mixed23', budget=budget, initial_target_sha256=digest(initial))
                else:
                    record.update(budget_seconds=budget, input_sha256=digest(initial))
                records.append(record)
                db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)', (identifier, 0, arm, budget, 1, json.dumps(record)))
                for name, content in artifacts.items():
                    db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (identifier, name, digest(content), zlib.compress(content)))
        else:
            workspace = folder/'abandoned-attempt'
            workspace.mkdir()
            db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)', (1, 0, arms[0], budget, 0,
                       json.dumps({'status': 'RUNNING', 'workspace': str(workspace)})))
        db.commit()
        db.close()
        grouped = {}
        for arm in arms:
            selected = [record for record in records if record['arm'] == arm]
            grouped[arm] = {'trials': len(selected), 'valid_final': sum(r['primary_valid_geometry'] for r in selected),
                            'valid_any_checkpoint': sum(r['any_saved_valid_geometry'] for r in selected),
                            'watchdog_trials': 0, 'audit_watchdog_trials': 0}
        pairs = {}
        pairs_to_check = [(arms[0], arms[1]), (arms[1], arms[2])] if paper else itertools.combinations(arms, 2)
        for first, second in pairs_to_check:
            pairs[first+'__'+second] = {'pairs': int(finished), 'first_only': int(finished and first == 'original'),
                                      'second_only': 0, 'both': 0, 'neither': int(finished and first != 'original')}
        group = {'arms': grouped, 'pairs': pairs}
        summary = {'registered_trials': 3, 'completed_trials': len(records), 'complete': finished}
        if paper:
            summary.update(families={'mixed23': {'budgets': {str(budget): group}}},
                           attempted_trials=3 if finished else 1, incomplete_attempts=0 if finished else 1)
        else:
            summary['budgets'] = {str(budget): group}
        (folder/'summary.json').write_text(json.dumps(summary))
        return registration

    def mutate_record(self, identifier, function):
        with sqlite3.connect(self.directory/'results.sqlite') as db:
            record = json.loads(db.execute('SELECT record FROM trials WHERE id=?', (identifier,)).fetchone()[0])
            function(record)
            db.execute('UPDATE trials SET record=? WHERE id=?', (json.dumps(record), identifier))

    def test_clean_19_fixture_and_no_database_changes(self):
        registration = self.fixture()
        before = digest((self.directory/'results.sqlite').read_bytes())
        report = audit_registration(registration)
        self.assertTrue(report['integrity_ok'], report['faults'])
        self.assertEqual(report['status'], 'PASSED')
        self.assertEqual(report['summary']['status'], 'MATCHED')
        self.assertEqual(report['completed_conditions'], 3)
        self.assertEqual(report['artifacts_checked'], 13)
        self.assertEqual(before, digest((self.directory/'results.sqlite').read_bytes()))

    def test_clean_paper_fixture(self):
        report = audit_registration(self.fixture(paper=True))
        self.assertTrue(report['integrity_ok'], report['faults'])
        self.assertEqual(report['kind'], 'paper_families')
        self.assertEqual(report['summary']['paired_comparisons_checked'], 2)

    def test_inflight_is_pending_not_corruption(self):
        report = audit_registration(self.fixture(finished=False))
        self.assertTrue(report['integrity_ok'], report['faults'])
        self.assertEqual(report['status'], 'PENDING')
        self.assertEqual(report['pending_conditions'], 3)
        self.assertEqual(report['diagnostics_counts']['inflight_or_abandoned_attempts'], 1)

    def test_superseded_incomplete_attempt_does_not_make_finished_study_pending(self):
        registration = self.fixture()
        with sqlite3.connect(self.directory/'results.sqlite') as db:
            db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)', (4, 0, 'original', 10, 0,
                       json.dumps({'status': 'RUNNING'})))
        report = audit_registration(registration)
        self.assertTrue(report['integrity_ok'], report['faults'])
        self.assertEqual(report['status'], 'PASSED')
        self.assertEqual(report['diagnostics_counts']['superseded_incomplete_attempts'], 1)

    def test_wrong_frozen_hash(self):
        registration = self.fixture()
        (self.directory/'frozen/original').write_text('modified')
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        self.assertTrue(any('SHA256 mismatch' in fault['message'] for fault in report['faults']))

    def test_compressed_artifact_corruption(self):
        registration = self.fixture()
        with sqlite3.connect(self.directory/'results.sqlite') as db:
            db.execute("UPDATE artifacts SET data=? WHERE trial_id=1 AND name='stage0.real'", (b'not zlib',))
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        self.assertTrue(any('compressed artifact' in fault['message'] for fault in report['faults']))

    def test_wrong_seed_and_false_first_checkpoint_promotion(self):
        registration = self.fixture()
        self.mutate_record(1, lambda record: record.update(seed=999))
        self.mutate_record(3, lambda record: record.update(final_checkpoint='stage0.real', primary_valid_geometry=True))
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        messages = [fault['message'] for fault in report['faults']]
        self.assertIn('Trial seed differs from registration', messages)
        self.assertIn('Wrong planned final checkpoint', messages)
        self.assertIn('Final-checkpoint primary result inconsistent', messages)

    def test_duplicate_completed_condition(self):
        registration = self.fixture()
        with sqlite3.connect(self.directory/'results.sqlite') as db:
            db.execute('INSERT INTO trials SELECT 4,case_id,arm,budget,complete,record FROM trials WHERE id=1')
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        self.assertTrue(any(fault['message'] == 'Duplicate completed condition' for fault in report['faults']))

    def test_wrong_summary_count_is_detected_independently(self):
        registration = self.fixture()
        path = self.directory/'summary.json'
        summary = json.loads(path.read_text())
        summary['budgets']['10']['arms']['original']['valid_final'] = 0
        path.write_text(json.dumps(summary))
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        self.assertEqual(report['summary']['status'], 'MISMATCH')

    def test_stale_live_summary_is_pending_and_cli_never_overwrites(self):
        registration = self.fixture()
        path = self.directory/'summary.json'
        summary = json.loads(path.read_text())
        summary['completed_trials'] = 0
        path.write_text(json.dumps(summary))
        with (self.directory/'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            report = audit_registration(registration)
            self.assertTrue(report['integrity_ok'], report['faults'])
            self.assertEqual(report['status'], 'PENDING')
            self.assertEqual(report['summary']['status'], 'PENDING_LIVE_SNAPSHOT')
            fcntl.flock(lock, fcntl.LOCK_UN)
        output = self.directory/'new-audit.json'
        argv = ['scaling_audit.py', '--registration', str(registration), '--output', str(output)]
        with mock.patch('sys.argv', argv), mock.patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(), 1)  # Same stale summary is now a quiescent integrity mismatch.
        old_bytes = output.read_bytes()
        with mock.patch('sys.argv', argv), mock.patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(output.read_bytes(), old_bytes)

    def test_missing_pair_summary_is_a_serializable_fault(self):
        registration = self.fixture()
        path = self.directory/'summary.json'
        summary = json.loads(path.read_text())
        summary['budgets']['10']['pairs'] = {}
        path.write_text(json.dumps(summary))
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        json.dumps(report, allow_nan=False)

    def test_mutating_artifact_and_its_hash_still_breaks_target_pairing(self):
        registration = self.fixture()
        replacement = b'different initial target\n'
        with sqlite3.connect(self.directory/'results.sqlite') as db:
            db.execute("UPDATE artifacts SET data=?,sha256=? WHERE trial_id=2 AND name='initial.or'",
                       (zlib.compress(replacement), digest(replacement)))
        report = audit_registration(registration)
        self.assertFalse(report['integrity_ok'])
        self.assertTrue(any(fault['message'] == 'Stored initial target missing or mismatched' for fault in report['faults']))

    def test_streaming_enforces_size_bound_and_rejects_trailing_data(self):
        self.fixture()
        with sqlite3.connect(self.directory/'results.sqlite') as db:
            rowid = db.execute('SELECT rowid FROM artifacts LIMIT 1').fetchone()[0]
            db.execute('UPDATE artifacts SET data=? WHERE rowid=?', (zlib.compress(b'x'*10000), rowid))
            with self.assertRaisesRegex(ValueError, 'bound'):
                streamed_artifact(db, rowid, 100)
            db.execute('UPDATE artifacts SET data=? WHERE rowid=?', (zlib.compress(b'abc')+b'junk', rowid))
            with self.assertRaisesRegex(ValueError, 'Trailing'):
                streamed_artifact(db, rowid, 100)


if __name__ == '__main__':
    unittest.main()
