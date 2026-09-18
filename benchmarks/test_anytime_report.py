"""Synthetic total-clock reporting fixtures; no SAT, native, or audit runs."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib

from benchmarks.anytime_report import analyze, main


class AnytimeReportTests(unittest.TestCase):
    def portfolio_fixture(self, root):
        template = self.fixture(root/'template')
        original = json.loads(template.read_text())
        with sqlite3.connect(template.parent/'results.sqlite') as db:
            source_rows = {(row['arm'], row['case_id']): row for stored, in db.execute('SELECT record FROM trials')
                           for row in [json.loads(stored)]}
        root.mkdir(parents=True, exist_ok=True)
        families = ('symmetry19', 'mixed23', 'holes29', 'gons32', 'caps26')
        arms = {f: ['original', 'v4_fixed', 'v4_retry', 'v4_feedback'] if f == 'symmetry19' else
                ['original', 'v6_plain', 'v6_line', 'v6_pair', 'v6_retry', 'v6_feedback'] for f in families}
        cases = [dict(id=f'{family}-{i}', family=family, n=19 if family == 'symmetry19' else 23,
                      seed=40+i, initial_full_sha256=f'{i:064x}') for family in families for i in range(20)]
        config = dict(original, cases=cases, arms_for_family=arms)
        registration = root/'registration.json'
        registration.write_text(json.dumps(config))
        with sqlite3.connect(root/'results.sqlite') as db:
            db.executescript('CREATE TABLE trials(id INTEGER PRIMARY KEY,case_id TEXT,arm TEXT,complete INTEGER,record TEXT);'
                'CREATE TABLE artifacts(trial_id INTEGER,name TEXT,sha256 TEXT,data BLOB);')
            identifier = 0
            for case in cases:
                i = int(case['id'].split('-')[-1])
                for arm in arms[case['family']]:
                    identifier += 1
                    source_arm = 'v6_feedback' if arm.endswith('_feedback') else 'v6_retry' if arm.endswith('_retry') else 'v6_plain'
                    row = json.loads(json.dumps(source_rows[(source_arm, f'mixed23-{i%4}')]))
                    row.update(case_id=case['id'], family=case['family'], arm=arm, seed=case['seed'], initial_full_sha256=case['initial_full_sha256'])
                    if row['certificates']:
                        certificate = dict(valid_geometry=True, general_position=True, family=case['family'],
                            certificate_validated_monotonic=1000+row['first_verified_seconds']-.001)
                        data = json.dumps(certificate).encode()
                        digest = hashlib.sha256(data).hexdigest()
                        row['certificates'][0]['certificate_sha256'] = digest
                        db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (identifier, 'check0000/certificate.json', digest, zlib.compress(data)))
                    db.execute('INSERT INTO trials VALUES(?,?,?,?,?)', (identifier, case['id'], arm, 1, json.dumps(row)))
        return registration

    def fixture(self, root):
        root.mkdir(parents=True, exist_ok=True)
        cases = [dict(id=f'mixed23-{i}', family='mixed23', n=23, seed=40+i,
                      primary_model=[1, -2], cnf='not_read.cnf', initial_full_sha256=str(i)*64) for i in range(4)]
        config = dict(cases=cases, arms_for_family=dict(mixed23=['v6_plain', 'v6_retry', 'v6_feedback']),
                      horizon_seconds=120, milestones=[30, 60, 120])
        registration = root/'registration.json'
        registration.write_text(json.dumps(config))
        db = sqlite3.connect(root/'results.sqlite')
        db.executescript('CREATE TABLE trials(id INTEGER PRIMARY KEY,case_id TEXT,arm TEXT,complete INTEGER,record TEXT);'
            'CREATE TABLE artifacts(trial_id INTEGER,name TEXT,sha256 TEXT,data BLOB);'
            'CREATE TABLE events(id INTEGER PRIMARY KEY,record TEXT);')
        times = {'v6_plain': [80, None, None, 50], 'v6_retry': [40, None, 35, None],
                 'v6_feedback': [20, 110, None, None]}
        identifier = 0
        for arm, outcomes in times.items():
            for i, first in enumerate(outcomes):
                identifier += 1
                status = 'SOLVED' if first is not None else 'TIME_LIMIT'
                observed = first if first is not None else 120
                if (arm, i) in (('v6_retry', 3), ('v6_feedback', 2)):
                    status, observed = 'ERROR', 10
                row = dict(case_id=cases[i]['id'], family='mixed23', arm=arm, seed=40+i,
                    initial_full_sha256=str(i)*64, initial_target_sha256='a'*64,
                    started_monotonic=1000, status=status, first_verified_seconds=first,
                    observed_seconds=observed, censor_seconds=min(120, observed),
                    parent_cpu_seconds=10.5, parent_wall_seconds=observed+.2,
                    posthoc_cpu_seconds=2, posthoc_wall_seconds=2.1,
                    certificates=[], components=[dict(kind=kind, cpu_seconds=cpu, wall_seconds=cpu+.1,
                                                      start_elapsed_seconds=0) for kind, cpu in
                        (('preparation', 3), ('native', 5), ('feedback', .4), ('online_audit', 1))],
                    posthoc=[dict(valid_geometry=True, accepted_elapsed_seconds=1)])
                if first is not None:
                    certificate = dict(valid_geometry=True, general_position=True, family='mixed23',
                        certificate_validated_monotonic=1000+first-.001)
                    data = json.dumps(certificate).encode()
                    digest = hashlib.sha256(data).hexdigest()
                    name = 'check0000/certificate.json'
                    row['certificates'] = [dict(accepted=True, accepted_elapsed_seconds=first,
                        accepted_timestamp_monotonic=1000+first, certificate_artifact=name, certificate_sha256=digest)]
                    db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (identifier, name, digest, zlib.compress(data)))
                db.execute('INSERT INTO trials VALUES(?,?,?,?,?)', (identifier, cases[i]['id'], arm, 1, json.dumps(row)))
        db.commit(); db.close()
        return registration

    def change(self, registration, identifier, update):
        with sqlite3.connect(registration.parent/'results.sqlite') as db:
            row = json.loads(db.execute('SELECT record FROM trials WHERE id=?', (identifier,)).fetchone()[0])
            update(row)
            db.execute('UPDATE trials SET record=? WHERE id=?', (json.dumps(row), identifier))

    def test_actual_events_all_target_denominators_and_posthoc_not_credited(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            report = analyze([registration])
            family = report['families']['mixed23']
            self.assertEqual(family['arms']['v6_feedback']['milestones']['30.0']['solved'], 1)
            self.assertEqual(family['arms']['v6_feedback']['milestones']['120.0']['solved'], 2)
            self.assertEqual(family['arms']['v6_feedback']['milestones']['120.0']['registered_targets'], 4)
            self.assertEqual([point['seconds'] for point in family['arms']['v6_feedback']['curve']], [0, 20, 110, 120])
            self.assertEqual(family['arms']['v6_feedback']['milestones']['120.0']['unobserved_targets'], 1)
            self.assertEqual(family['arms']['v6_feedback']['censoring'][0]['status'], 'ERROR')

    def test_all_attempt_costs_not_success_conditioned_and_posthoc_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            report = analyze([registration])
            cost = report['families']['mixed23']['arms']['v6_feedback']['all_attempt_costs']
            self.assertEqual(cost['attempts'], 4)
            self.assertEqual(cost['parent_cpu_seconds'], 42)
            self.assertEqual(cost['posthoc_cpu_seconds'], 8)
            self.assertEqual(cost['components']['native']['cpu_seconds'], 20)

    def test_matched_feedback_gains_and_losses_include_all_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            report = analyze([self.fixture(Path(temp))])
            pairs = report['families']['mixed23']['pairs']['v6_retry__v6_feedback']['120.0']
            self.assertEqual([pairs[key] for key in ('first_only', 'second_only', 'both', 'neither')], [1, 1, 1, 1])
            self.assertEqual(pairs['registered_pairs'], 4)
            self.assertEqual(pairs['provisional_pairs'], 2)

    def test_corrupt_or_false_certificate_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            with sqlite3.connect(registration.parent/'results.sqlite') as db:
                db.execute('UPDATE artifacts SET data=? WHERE trial_id=1', (zlib.compress(b'{}'),))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                analyze([registration])

    def test_partial_temporary_certificate_is_not_an_online_certificate(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            partial = b'{"incomplete":'
            with sqlite3.connect(registration.parent/'results.sqlite') as db:
                db.execute('INSERT INTO artifacts VALUES(?,?,?,?)',
                    (1, 'check0001/certificate.json.tmp', hashlib.sha256(partial).hexdigest(), zlib.compress(partial)))
            analyze([registration])

    def test_backdated_time_and_wrong_seed_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            self.change(registration, 1, lambda row: row['certificates'][0].update(accepted_elapsed_seconds=79))
            with self.assertRaisesRegex(ValueError, 'trial clock'):
                analyze([registration])
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            self.change(registration, 1, lambda row: row.update(seed=99))
            with self.assertRaisesRegex(ValueError, 'seed mismatch'):
                analyze([registration])

    def test_nonfinite_absolute_clock_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            self.change(registration, 1, lambda row: row['certificates'][0].update(accepted_timestamp_monotonic=float('nan')))
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                analyze([registration])

    def test_mismatched_partial_targets_rejected_but_missing_preptimeout_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            self.change(registration, 2, lambda row: row.update(initial_target_sha256='b'*64))
            with self.assertRaisesRegex(ValueError, 'different initial target'):
                analyze([registration])
            self.change(registration, 2, lambda row: row.update(initial_target_sha256=None))
            analyze([registration])

    def test_duplicate_complete_rejected_incomplete_cpu_kept(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            with sqlite3.connect(registration.parent/'results.sqlite') as db:
                row = dict(status='INTERRUPTED', observed_seconds=5, censor_seconds=5, parent_cpu_seconds=4)
                db.execute('INSERT INTO trials VALUES(?,?,?,?,?)', (20, 'mixed23-0', 'v6_plain', 0, json.dumps(row)))
            report = analyze([registration])
            self.assertEqual(report['studies'][0]['ledger']['incomplete_attempts'], 1)
            self.assertEqual(report['studies'][0]['ledger']['all_attempt_costs']['parent_cpu_seconds'], 130)
            with sqlite3.connect(registration.parent/'results.sqlite') as db:
                db.execute('UPDATE trials SET complete=1 WHERE id=20')
            with self.assertRaisesRegex(ValueError, 'Duplicate COMPLETE'):
                analyze([registration])

    def test_draft_does_not_fabricate_pending_exposure(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp))
            with sqlite3.connect(registration.parent/'results.sqlite') as db:
                db.execute('DELETE FROM trials WHERE id>8')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                analyze([registration])
            report = analyze([registration], draft=True)
            row = report['families']['mixed23']['arms']['v6_feedback']['milestones']['120.0']
            self.assertEqual(row['solved'], 0)
            self.assertEqual(row['unobserved_targets'], 4)
            self.assertEqual(row['statuses'], {'not_started': 4})

    def test_full_report_pdf_and_frozen_sibling_import_without_source_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registration = self.portfolio_fixture(root/'study')
            before = {p: p.read_bytes() for p in (registration, registration.parent/'results.sqlite')}
            output = root/'report'
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--registration', str(registration), '--out', str(output)]), 0)
            self.assertTrue((output/'anytime-report.pdf').read_bytes().startswith(b'%PDF'))
            self.assertEqual(json.loads((output/'report.json').read_text())['pdf']['layout_warnings'], [])
            for path, data in before.items():
                self.assertEqual(path.read_bytes(), data)
            with self.assertRaises(FileExistsError):
                main(['--registration', str(registration), '--out', str(output)])
            frozen = root/'frozen'; frozen.mkdir()
            source = Path(__file__).resolve().parent
            for name in ('anytime_report.py', 'anytime_pdf.py'):
                shutil.copy2(source/name, frozen/name)
            copied = subprocess.run([sys.executable, str(frozen/'anytime_report.py'), '--registration', str(registration),
                '--out', str(root/'frozen-report')], cwd=frozen, text=True, capture_output=True, timeout=20)
            self.assertEqual(copied.returncode, 0, copied.stdout+copied.stderr)


if __name__ == '__main__':
    unittest.main()
