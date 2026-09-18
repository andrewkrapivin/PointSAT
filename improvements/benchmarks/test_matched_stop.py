#!/usr/bin/env python3
"""A supervisor SIGTERM must checkpoint the native child and skip queued runs."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from matched import ROOT,HERE

class StopTests(unittest.TestCase):
    def test_stop_checkpoints_and_skips_pending(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            folder=Path(temporary)
            cases=json.loads((HERE/'round2_initial6_manifest.json').read_text())['cases'][:1]
            manifest=folder/'manifest.json';manifest.write_text(json.dumps({'cases':cases}))
            command=[sys.executable,str(HERE/'matched.py'),'run','--manifest',str(manifest),
                     '--binary',str(ROOT/'improvements/localizer/localizer_v5'),'--label','stop_test',
                     '--output',str(folder/'result'),'--seconds','30','--seeds','991','992','993','--jobs','1']
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            started=time.monotonic()
            while not list((folder/'result').glob('*/stdout.log')) and time.monotonic()-started<3:
                time.sleep(.02)
            time.sleep(.25)
            process.send_signal(signal.SIGTERM)
            stdout,stderr=process.communicate(timeout=6)
            self.assertEqual(process.returncode,0,(stdout,stderr))
            records=[json.loads(p.read_text()) for p in (folder/'result').glob('*/result.json')]
            self.assertEqual(len(records),1,records)
            self.assertTrue(records[0]['interrupted'])
            self.assertFalse(records[0]['eligible_for_matched_comparison'])
            self.assertIn('orientation_violations',records[0])
            self.assertLess(time.monotonic()-started,6)

if __name__=='__main__':unittest.main()
