#!/usr/bin/env python3
"""Synthetic SQLite tests; no native search, SAT solve, or verifier rerun."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zlib

SPEC = importlib.util.spec_from_file_location('scaling_effects', Path(__file__).with_name('scaling_effects.py'))
effects = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(effects)


class EffectsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pointsat-scaling-effects-')
        self.folder = Path(self.temporary.name)
        self.registration = self.folder/'registration.json'
        self.config = {'arms': ['original'], 'budgets': [10, 30, 60],
                       'cases': [{'id': i, 'seed': 40+i, 'family': 'mixed23'} for i in range(4)]}
        self.registration.write_text(json.dumps(self.config))
        self.db = sqlite3.connect(self.folder/'results.sqlite')
        self.db.executescript('CREATE TABLE trials(id INTEGER PRIMARY KEY,case_id,arm,budget,complete,record);'
                             'CREATE TABLE artifacts(trial_id,name,sha256,data);')

    def tearDown(self):
        self.db.close(); self.temporary.cleanup()

    def add(self, case, budget, forbidden, *, gp=True, orientation=8, complete=True,
            seed=None, input_sha='a'*64, target_sha='b'*64, certificate=True, earlier_valid=False, nineteen=False):
        check = {'general_position': gp, 'valid_geometry': gp and forbidden == 0,
                 'orientation_violations': orientation, 'constraint_count': 969 if nineteen else 1771}
        if nineteen:
            check.update(forbidden_hexagons=forbidden, input_signature={'target_sha256': target_sha})
        else:
            check.update(forbidden_polygons=forbidden, source_full_target_sha256=target_sha)
        audits = [dict(check, checkpoint='stage1.real')]
        if earlier_valid:
            audits.insert(0, dict(check, checkpoint='stage0.real', valid_geometry=True, forbidden_polygons=0))
        row = {'case_id': case, 'arm': 'original', 'seed': 40+case if seed is None else seed,
               'primary_valid_geometry': check['valid_geometry'], 'final_checkpoint': 'stage1.real', 'audits': audits}
        row.update({'budget_seconds': budget, 'input_sha256': input_sha} if nineteen else
                   {'budget': budget, 'initial_target_sha256': input_sha, 'family': 'mixed23'})
        cursor = self.db.execute('INSERT INTO trials(case_id,arm,budget,complete,record) VALUES(?,?,?,?,?)',
                                 (case, 'original', budget, complete, json.dumps(row)))
        trial_id = cursor.lastrowid
        if certificate:
            data = json.dumps(check).encode()
            self.db.execute('INSERT INTO artifacts VALUES(?,?,?,?)',
                            (trial_id, 'stage1-audit/certificate.json', effects.sha(data), zlib.compress(data)))
        self.db.commit(); return trial_id

    def comparison(self, key='10.0__30.0'):
        return effects.analyze(self.registration)['families']['mixed23']['arms']['original']['comparisons'][key]

    def test_paired_gains_losses_and_delta_not_difference_of_medians(self):
        for i, (low, high) in enumerate([(4, 0), (0, 2), (1, 9), (0, 0)]):
            self.add(i, 10, low, orientation=10+i)
            self.add(i, 30, high, orientation=3+i)
        result = self.comparison()
        self.assertEqual(result['validity'], {'gains': 1, 'losses': 1, 'both': 1, 'neither': 1})
        self.assertEqual(result['forbidden']['median_delta'], 1)
        self.assertEqual([result['forbidden'][k] for k in ('lower','equal','higher')], [1,1,2])
        self.assertEqual(result['orientation']['median_delta'], -7)
        self.assertEqual(result['completed_pairs'], 4)

    def test_missing_non_gp_certificates_and_final_only(self):
        self.add(0, 10, 2, earlier_valid=True); self.add(0, 30, 4)
        self.add(1, 10, 0, gp=False); self.add(1, 30, 3)
        self.add(2, 10, 3, certificate=False); self.add(2, 30, 2)
        self.add(3, 30, 1)
        result = self.comparison()
        self.assertEqual(result['validity']['neither'], 3)
        self.assertEqual(result['forbidden']['paired_GP'], 1)
        self.assertEqual(result['forbidden']['missing'], 2)
        self.assertEqual(result['forbidden']['median_delta'], 2)
        self.assertEqual(result['missing_lower'], 1)
        self.assertEqual(result['forbidden']['reasons']['lower:not_general_position'], 1)
        self.assertEqual(result['forbidden']['reasons']['lower:missing_or_mismatched_certificate'], 1)

    def test_latest_complete_only_and_interrupted_preserved(self):
        self.add(0, 10, 8); self.add(0, 10, 2)
        self.add(0, 10, 0, complete=False); self.add(0, 30, 1)
        result = effects.analyze(self.registration, include_pairs=True)
        ledger = result['sources'][0]['ledger']
        self.assertEqual(ledger['superseded_completed_attempts'], 1)
        self.assertEqual(ledger['incomplete_attempts'], 1)
        self.assertEqual(self.comparison()['forbidden']['median_delta'], -1)
        self.assertEqual(self.comparison('10.0__60.0')['missing_higher'], 1)

    def test_seed_and_input_mismatch_rejected(self):
        self.add(0, 10, 1); self.add(0, 30, 1, input_sha='c'*64)
        with self.assertRaisesRegex(ValueError, 'Unmatched seed/initial'):
            self.comparison()
        self.db.execute('DELETE FROM trials'); self.db.execute('DELETE FROM artifacts'); self.db.commit()
        self.add(0, 10, 1, seed=999)
        with self.assertRaisesRegex(ValueError, 'Registered seed mismatch'):
            self.comparison()

    def test_hash_corruption_rejected(self):
        self.add(0, 10, 1)
        self.db.execute("UPDATE artifacts SET sha256=?", ('0'*64,)); self.db.commit()
        with self.assertRaisesRegex(ValueError, 'Certificate hash mismatch'):
            self.comparison()

    def test_orientation_target_mismatch_rejected_only_for_secondary(self):
        self.add(0, 10, 3); self.add(0, 30, 2, target_sha='d'*64)
        with self.assertRaisesRegex(ValueError, 'different full targets'):
            self.comparison()
        result = effects.analyze(self.registration, include_orientation=False)
        group = result['families']['mixed23']['arms']['original']['comparisons']['10.0__30.0']
        self.assertEqual(group['forbidden']['median_delta'], -1)

    def test_missing_saved_final_is_failure_without_residual(self):
        trial = self.add(0, 10, 3); self.add(0, 30, 2)
        row = json.loads(self.db.execute('SELECT record FROM trials WHERE id=?', (trial,)).fetchone()[0])
        row['audits'] = []
        self.db.execute('UPDATE trials SET record=? WHERE id=?', (json.dumps(row), trial)); self.db.commit()
        group = self.comparison()
        self.assertEqual(group['validity']['neither'], 1)
        self.assertEqual(group['forbidden']['paired_GP'], 0)
        self.assertEqual(group['forbidden']['reasons']['lower:missing_final_checkpoint'], 1)

    def test_nineteen_schema_and_read_only(self):
        for case in self.config['cases']:
            del case['family']
        self.registration.write_text(json.dumps(self.config))
        self.add(0, 10, 6, nineteen=True); self.add(0, 60, 1, nineteen=True)
        before = (self.folder/'results.sqlite').read_bytes()
        result = effects.analyze(self.registration, include_orientation=False, include_pairs=True)
        group = result['families']['symmetry19']['arms']['original']['comparisons']['10.0__60.0']
        self.assertEqual(group['forbidden']['median_delta'], -5)
        self.assertFalse(group['adjacent']); self.assertNotIn('orientation', group)
        self.assertEqual(before, (self.folder/'results.sqlite').read_bytes())

    def test_no_database_means_pending_not_failures(self):
        self.db.close(); (self.folder/'results.sqlite').unlink()
        result = self.comparison()
        self.assertEqual(result['missing_both'], 4)
        self.assertEqual(result['completed_pairs'], 0)
        self.assertEqual(result['forbidden']['median_delta'], None)


if __name__ == '__main__':
    unittest.main()
