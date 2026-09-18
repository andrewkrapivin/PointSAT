#!/usr/bin/env python3
"""Separate short smoke for both model consumption and actual-geometry idle work."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import signal
import tempfile
import time
import unittest
from matched import ROOT,HERE

class ConsumerTests(unittest.TestCase):
    def test_sigterm_fallback_saves_native_incumbent(self):
        with tempfile.TemporaryDirectory(dir=HERE)as tmp:
            folder=Path(tmp);(folder/'empty').mkdir()
            command=[str(ROOT/'direct/vendor/venv/bin/python'),str(HERE/'consume_lazy19.py'),
                     '--models',str(folder/'empty'),'--output',str(folder/'output'),
                     '--deadline',(datetime.now(timezone.utc)+timedelta(seconds=90)).isoformat(),
                     '--geometry-binary',str(ROOT/'improvements/localizer/geometry19_v2'),
                     '--geometry-seed',str(ROOT/'improvements/localizer/results/resume0526/geometry-free-s1962.pts')]
            process=subprocess.Popen(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            start=time.monotonic()
            while not list((folder/'output').glob('fallback/*/native.stdout')) and time.monotonic()-start<3:time.sleep(.02)
            time.sleep(.2);process.send_signal(signal.SIGTERM)
            stdout,stderr=process.communicate(timeout=5)
            self.assertEqual(process.returncode,0,stdout+stderr)
            checkpoint=json.loads((folder/'output/checkpoint.json').read_text())
            self.assertTrue(checkpoint['stop_requested'])
            records=list((folder/'output').glob('fallback/*/result.json'));self.assertEqual(len(records),1)
            result=json.loads(records[0].read_text())
            self.assertTrue(result['interrupted']);self.assertIn('independent_verification',result)

    def test_cold_warm_model_and_exact_audit(self):
        with tempfile.TemporaryDirectory(dir=HERE)as tmp:
            folder=Path(tmp)
            command=[str(ROOT/'direct/vendor/venv/bin/python'),str(HERE/'consume_lazy19.py'),
                     '--models',str(ROOT/'improvements/lazy19/results/distance19542'),'--output',str(folder/'models'),
                     '--deadline',(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat(),
                     '--geometry-binary',str(ROOT/'improvements/localizer/geometry19_v2'),
                     '--geometry-seed',str(ROOT/'improvements/localizer/results/resume0526/geometry-free-s1962.pts'),
                     '--native-seconds','.2','--max-models','1','--allow-unscreened']
            run=subprocess.run(command,text=True,capture_output=True,timeout=25)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            checkpoint=json.loads((folder/'models/checkpoint.json').read_text())
            self.assertEqual(len(checkpoint['processed_hashes']),1)
            records=list((folder/'models/models').glob('*/result.json'));self.assertEqual(len(records),1)
            result=json.loads(records[0].read_text());self.assertTrue(result['complete'])
            self.assertEqual(len(result['runs']),2)
            self.assertFalse(result['runs'][0]['warm_start']);self.assertTrue(result['runs'][1]['warm_start'])
            self.assertTrue(all('independent_certificate'in r for r in result['runs']))

if __name__=='__main__':unittest.main()
