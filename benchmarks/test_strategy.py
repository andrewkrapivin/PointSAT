#!/usr/bin/env python3
"""Regression checks on the short immutable smoke and SQLite evidence export."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import zlib

HERE=Path(__file__).resolve().parent

class StrategyTests(unittest.TestCase):
    def test_extension_is_disjoint_and_policy_frozen(self):
        pilot_path=HERE/'pilot_20260906/registration.json'
        pilot=json.loads(pilot_path.read_text())
        extension=json.loads((HERE/'extension_20260906/registration.json').read_text())
        self.assertEqual(extension['parent_registration_sha256'],hashlib.sha256(pilot_path.read_bytes()).hexdigest())
        for field in('budget_seconds','native_chunk_seconds','feedback_seconds','native_binary',
                     'binary_sha256','frozen_sha256','seeds','caps_ordered_x','initial_flippability',
                     'feedback_flippability','feedback_policy'):
            self.assertEqual(pilot[field],extension[field],field)
        self.assertEqual(len(extension['jobs']),64)
        self.assertEqual(extension['selection_offset'],4)
        self.assertTrue(extension['no_tuning'])
        self.assertFalse({c['orientation_sha256']for c in pilot['cases']}.intersection(
                         c['orientation_sha256']for c in extension['cases']))
        for cohort in('pilot_20260906','extension_20260906'):
            folder=HERE/cohort;config=json.loads((folder/'registration.json').read_text())
            self.assertEqual(len(config['cases']),16)
            for file,digest in config['frozen_sha256'].items():
                self.assertEqual(hashlib.sha256((folder/'frozen'/file).read_bytes()).hexdigest(),digest)

    def test_pilot_complete_and_matched(self):
        from report import calculate,load
        folder=HERE/'pilot_20260906';config=json.loads((folder/'registration.json').read_text())
        rows=load(folder/'results.sqlite');summary=calculate(rows,config)
        self.assertTrue(summary['complete'])
        self.assertEqual(summary['completed_trials'],64)
        indexed={(r['job']['case']['id'],r['job']['seed'],r['job']['arm']):r for r in rows}
        for (case,seed,arm),a in indexed.items():
            if arm!='warm_retry':continue
            b=indexed[case,seed,'core_feedback']
            self.assertEqual(a['stages'][0]['target_sha256'],b['stages'][0]['target_sha256'])
            self.assertEqual(a['stages'][0]['seed'],b['stages'][0]['seed'])
            self.assertEqual(a['initial_flippable_count'],b['initial_flippable_count'])
        for r in rows:
            self.assertLess(r['wall_seconds'],61.1)
            self.assertFalse(r['externally_interrupted'])
            self.assertTrue(all('geometry'in s for s in r['posthoc']['saved_checkpoints']))

    def test_short_budget_and_exact_audits(self):
        folder=HERE/'smoke_20260906';config=json.loads((folder/'registration.json').read_text())
        with sqlite3.connect(folder/'results.sqlite')as db:
            rows=[json.loads(r[0])for r in db.execute('SELECT result_json FROM trials')]
            self.assertEqual(len(rows),8)
            self.assertEqual({r['job']['case']['problem']for r in rows},{'mixed23','holes29','gons32','caps26'})
            for r in rows:
                self.assertEqual(r['returncode'],0)
                self.assertLess(r['wall_seconds'],config['budget_seconds']+1.1)
                self.assertFalse(r['externally_interrupted'])
                self.assertTrue(r['posthoc']['saved_checkpoints'])
                self.assertTrue(all('geometry'in s for s in r['posthoc']['saved_checkpoints']))
            for name,digest,data in db.execute('SELECT name,sha256,data_zlib FROM artifacts'):
                self.assertEqual(hashlib.sha256(zlib.decompress(data)).hexdigest(),digest)
                self.assertEqual(Path(name).name,name)

    def test_frozen_helpers_and_matched_initial_target(self):
        folder=HERE/'smoke_20260906';config=json.loads((folder/'registration.json').read_text())
        for file,digest in config['frozen_sha256'].items():
            self.assertEqual(hashlib.sha256((folder/'frozen'/file).read_bytes()).hexdigest(),digest)
        with sqlite3.connect(folder/'results.sqlite')as db:
            rows=[json.loads(r[0])for r in db.execute('SELECT result_json FROM trials')]
        indexed={(r['job']['case']['id'],r['job']['arm']):r for r in rows}
        for case in config['cases']:
            a=indexed[case['id'],'warm_retry'];b=indexed[case['id'],'core_feedback']
            self.assertEqual(a['stages'][0]['target_sha256'],b['stages'][0]['target_sha256'])
            self.assertEqual(a['initial_flippable_count'],b['initial_flippable_count'])

    def test_export_round_trip(self):
        with tempfile.TemporaryDirectory(dir=HERE)as tmp:
            destination=Path(tmp)/'export'
            subprocess.run(['python3',str(HERE/'report.py'),'export','--database',str(HERE/'smoke_20260906/results.sqlite'),
                            '--trial','0','--output',str(destination)],check=True,capture_output=True)
            self.assertTrue((destination/'result.json').exists())
            self.assertTrue(list(destination.glob('stage*.real')))

if __name__=='__main__':unittest.main()
