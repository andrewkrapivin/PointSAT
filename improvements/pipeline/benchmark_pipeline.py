#!/usr/bin/env python3
"""Isolate Python orchestration/helpers using the SAME immutable native binary."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    os.chdir(ROOT)
    directory = ROOT / 'improvements/pipeline/paired_pipeline'
    directory.mkdir(exist_ok=True)
    common = {'base_file': '7gon-6hole-23-compact.cnf', 'n': 23,
              'solution_generation': 'scranfilize', 'n_solutions': 8, 'workers': 2,
              'worker_max_threads': 1, 'remove_flippable': True,
              'localizer_attempt_levels': 1, 'localizer_attempt_timeouts': [15],
              'scranfilize_loc': 'direct/vendor/scranfilize/scranfilize',
              'cadical_loc': 'direct/vendor/kissat/build/kissat',
              'localizer_loc': 'improvements/pipeline/localizer_baseline_safe.sh',
              'solver_timeout': 90, 'continue_if_realized': False}
    manifest = {'description': 'Eight matched SAT seeds0..7;2workers;15s per realization; identical upstream native binary with explicit empty -f/-c.',
                'native_sha256': hashlib.sha256((ROOT/'improvements/localizer/localizer_baseline').read_bytes()).hexdigest(),
                'runs': []}
    for label, script in [('before', 'improvements/benchmarks/baseline_snapshot/PointSAT.py'), ('after', 'PointSAT.py')]:
        out = directory / label
        out.mkdir(exist_ok=True)
        if (out/'raw_results.jsonl').exists():
            raise SystemExit('Refusing existing benchmark output')
        settings = dict(common, output_folder=str(out.relative_to(ROOT)))
        config = directory / f'{label}.json'
        config.write_text(json.dumps(settings, indent=2)+'\n')
        command = [sys.executable, '-u', script, str(config)]
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        begin = time.perf_counter()
        timed_out = False
        with (out/'console.log').open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                process.wait(timeout=360)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        raw = out/'raw_results.jsonl'
        records = [json.loads(line) for line in raw.read_text().splitlines()] if raw.exists() else []
        entry = {'label': label, 'command': command, 'wall_seconds': time.perf_counter()-begin,
                 'cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                 'returncode': process.returncode, 'timed_out': timed_out, 'settings': settings,
                 'records': len(records), 'realized': sum(r.get('realized', False) for r in records),
                 'sat_models': sum(r.get('satisfiable', False) for r in records if r['type']=='SAT'),
                 'raw_results': str(raw.relative_to(ROOT))}
        manifest['runs'].append(entry)
        (directory/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        print(json.dumps(entry), flush=True)


if __name__ == '__main__':
    main()
