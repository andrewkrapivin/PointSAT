"""Synthetic summary tests; no SAT, Localizer, or geometry audit is run."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from benchmarks.scaling_report import FAMILIES, load_study, main, read_attempts


class ScalingReportTests(unittest.TestCase):
    def fixture(self, root, name, partial=False):
        path = root/name
        path.mkdir()
        names = ['symmetry19'] if name == 'nineteen' else list(FAMILIES[1:])
        arms = ['original', 'improved_fixed', 'improved_feedback'] if name == 'nineteen' else ['original', 'v6_plain', 'v6_line10', 'v6_line10_pair10', 'v6_feedback']
        cases = [dict(id=f'{family}-{i}', family=family, problem=family) for family in names for i in range(2)]
        registration = dict(cases=cases, budgets=[10,30,60], arms=arms)
        (path/'registration.json').write_text(json.dumps(registration))
        families = {}
        for family in names:
            budgets = {}
            for budget in (10,30,60):
                rows = {}
                for arm in arms:
                    completed = 1 if partial else 2
                    rows[arm] = dict(trials=completed, valid_final=int(budget>=30), valid_any_checkpoint=int(budget>=30),
                                     general_position_final=completed, median_forbidden_count_in_GP=5 if budget==10 else 0,
                                     native_cpu_seconds=budget*completed*.9, native_wall_seconds=budget*completed,
                                     worker_observed_cpu_seconds=budget*completed*.9+1,
                                     worker_wall_seconds=budget*completed+2, audit_wall_seconds=3,
                                     watchdog_trials=0, error_trials=0, audit_errors=0)
                budgets[str(budget)] = dict(arms=rows, pairs={'original__'+arms[-1]: dict(pairs=completed,first_only=0,second_only=0,both=int(budget>=30),neither=completed-int(budget>=30))})
            families[family] = dict(budgets=budgets)
        summary = dict(registered_trials=len(cases)*len(arms)*3,
                       completed_trials=len(cases)*len(arms)*3//(2 if partial else 1),
                       complete=not partial, preparation_cpu_seconds=4, preparation_wall_seconds=5)
        if name == 'nineteen':
            summary.update(families['symmetry19'])
        else:
            summary['families'] = families
        (path/'summary.json').write_text(json.dumps(summary))
        return path/'registration.json'

    def test_normalization_keeps_missing_cpu_unknown_and_shared_prep_once(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp),'paper')
            study = load_study(registration,'paper',False)
            self.assertIsNone(study['costs']['audit_cpu_seconds'])
            self.assertEqual(study['costs']['preparation_cpu_seconds'],4)
            self.assertEqual(len(study['families']),4)
            self.assertEqual(study['families'][0]['registered_targets'],2)
            self.assertEqual(study['families'][0]['budgets']['10.0']['arms']['original']['median_forbidden_in_GP'],5)

    def test_partial_requires_draft_and_retains_pending_denominators(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp),'nineteen',partial=True)
            with self.assertRaises(ValueError):
                load_study(registration,'nineteen',False)
            study = load_study(registration,'nineteen',True)
            row = study['families'][0]['budgets']['10.0']['arms']['original']
            self.assertEqual(row['pending_targets'],1)
            self.assertEqual(row['valid_final'],0)

    def test_combined_corpus_costs_and_frozen_provenance_are_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            registration = self.fixture(Path(temp), 'nineteen')
            data = json.loads(registration.read_text())
            data['corpus'] = str(Path(temp)/'missing_original_corpus')
            registration.write_text(json.dumps(data))
            frozen = registration.parent/'frozen'
            frozen.mkdir()
            (frozen/'corpus-manifest.json').write_text(json.dumps(dict(
                generation_child_cpu_seconds=1800, combine_validation_child_cpu_seconds=20,
                combine_controller_cpu_seconds=2, combine_wall_seconds=24,
                strata=dict(fresh=7, historical_initial_sat=13))))
            study = load_study(registration, 'nineteen', False)
            self.assertEqual(study['costs']['corpus_generation_child_cpu_seconds'], 1800)
            self.assertEqual(study['costs']['corpus_combine_validation_child_cpu_seconds'], 20)
            self.assertEqual(study['corpus']['strata']['fresh'], 7)

    def test_attempt_accounting_includes_inflight_identity_and_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp)/'results.sqlite'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE trials(id INTEGER PRIMARY KEY,case_id INTEGER,arm TEXT,budget REAL,complete INTEGER,record TEXT)')
                for identifier in (1,2):
                    db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)',
                               (identifier,identifier,'original',10,0,json.dumps({'status':'RUNNING'})))
                db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)',
                           (3,1,'original',10,1,json.dumps({'status':'ERROR','error':'test','parent_cpu_seconds':2})))
            result = read_attempts(database)
            self.assertEqual(result['persisted_attempts'],3)
            self.assertEqual(result['incomplete_attempts'],2)
            self.assertEqual(result['repeated_case_arm_budget_attempts'],1)
            self.assertEqual(len(result['errors']),1)
            self.assertEqual(result['recorded_worker_cpu_seconds_all_attempts'],2)
            self.assertIsNone(result['recorded_audit_cpu_seconds_all_attempts'])

    def test_report_creates_vector_and_raster_artifacts_without_source_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nineteen = self.fixture(root,'nineteen')
            paper = self.fixture(root,'paper')
            before = {p: p.read_bytes() for p in root.rglob('*.json')}
            output = root/'report'
            args = ['--nineteen-registration',str(nineteen),'--paper-registration',str(paper),'--out',str(output)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args),0)
            self.assertEqual({p.name for p in output.iterdir()},
                             {'README.md','report.json','checkpoints.pdf','checkpoints.png','costs.pdf','costs.png',
                              'scaling-report.tex','scaling-report.pdf'})
            self.assertTrue((output/'checkpoints.pdf').read_bytes().startswith(b'%PDF'))
            self.assertTrue((output/'checkpoints.png').read_bytes().startswith(b'\x89PNG'))
            self.assertTrue((output/'scaling-report.pdf').read_bytes().startswith(b'%PDF'))
            for path, contents in before.items():
                self.assertEqual(path.read_bytes(),contents)
            self.assertIn('No actual first-success time', (output/'README.md').read_text())
            with self.assertRaises(FileExistsError):
                main(args)


if __name__ == '__main__':
    unittest.main()
