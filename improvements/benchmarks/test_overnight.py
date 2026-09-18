#!/usr/bin/env python3
"""Bounded end-to-end smoke; separate seed and tiny budgets, never heldout data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from matched import ROOT,HERE

class OvernightTests(unittest.TestCase):
    def test_sat_and_five_paired_treatments(self):
        with tempfile.TemporaryDirectory(dir=HERE)as temporary:
            folder=Path(temporary)
            registration=json.loads((HERE/'overnight/registration.json').read_text())
            case=dict(next(c for c in registration['cases']if c['problem']=='caps26'))
            case.update(id='smoke-caps26-s99991',sat_seed=99991,sat_seconds=30,output=str(folder/'output'))
            registration.update(cases=[case],native_seeds=[1],native_seconds=.2)
            path=folder/'registration.json';path.write_text(json.dumps(registration))
            run=subprocess.run([str(ROOT/'direct/vendor/venv/bin/python'),str(HERE/'overnight_case.py'),
                                '--registration',str(path),'--index','0'],text=True,capture_output=True,timeout=45)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            got=json.loads((folder/'output/case_result.json').read_text())
            self.assertEqual(got['sat']['returncode'],10)
            self.assertTrue(got['independent_original_cnf']['satisfiable'])
            self.assertEqual(len(got['native_runs']),5)
            self.assertTrue(got['completed_all_native_runs'])
            self.assertTrue(all('orientation_violations'in r for r in got['native_runs']))
            self.assertEqual(len({r['orientation_sha256']for r in got['native_runs']}),1)
            ordered=next(r for r in got['native_runs']if r['label']=='v6_ordered_x')
            self.assertTrue(ordered['label_order_affine_feasible'])

if __name__=='__main__':unittest.main()
