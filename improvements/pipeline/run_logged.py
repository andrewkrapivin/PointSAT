#!/usr/bin/env python3
"""Run one bounded pipeline experiment, retaining wall/CPU logs in its output."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('settings')
parser.add_argument('--out', required=True)
parser.add_argument('--wall-seconds', type=float, default=1200)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
os.chdir(root)
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
if (out/'raw_results.jsonl').exists() or (out/'resource.json').exists():
    raise SystemExit('Refusing to overwrite an existing experiment')
command = [sys.executable,'-u','PointSAT.py',args.settings,'--out',str(out)]
before = resource.getrusage(resource.RUSAGE_CHILDREN)
start = time.perf_counter()
timed_out = False
with (out/'console.log').open('w') as log:
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        process.wait(timeout=args.wall_seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        timed_out = True
        os.kill(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.kill(process.pid, signal.SIGTERM)
            process.wait(timeout=20)
after = resource.getrusage(resource.RUSAGE_CHILDREN)
record = {'command':command,'wall_seconds':time.perf_counter()-start,
          'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
          'max_rss_kib':after.ru_maxrss,'returncode':process.returncode,'timed_out':timed_out}
(out/'resource.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
