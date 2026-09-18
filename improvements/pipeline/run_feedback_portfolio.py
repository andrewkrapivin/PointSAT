#!/usr/bin/env python3
"""Matched warm-retry versus UNSAT-core feedback pilot, kept separate from timing isolation."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    os.chdir(ROOT)
    directory = ROOT/'improvements/pipeline/feedback_pilot'
    directory.mkdir(exist_ok=True)
    binary = 'improvements/localizer/localizer_v2'
    manifest = {'description': 'Four matched SAT seeds0..3 per problem; two workers; at most4x15s Localizer/model. Warm retries vs core-guided retargeting are search treatments, not isolated speed tests.',
                'native_sha256': hashlib.sha256((ROOT/binary).read_bytes()).hexdigest(), 'runs': []}
    problems = [('mixed23',23,'7gon-6hole-23-compact.cnf'),
                ('gons32',32,'7gon-32.cnf'), ('caps26',26,'7gon-no-5-cap-no-sb-26.cnf')]
    for problem, n, base in problems:
        for treatment in ('warm_retry', 'core_feedback'):
            out = directory/f'{problem}-{treatment}'
            if (out/'raw_results.jsonl').exists():
                raise SystemExit(f'Refusing existing run {out}')
            out.mkdir(exist_ok=True)
            settings = {'base_file': base, 'n': n, 'output_folder': str(out.relative_to(ROOT)),
                        'solution_generation': 'scranfilize', 'n_solutions': 4, 'workers': 2,
                        'worker_max_threads': 1, 'remove_flippable': True,
                        'localizer_attempt_levels': 4 if treatment=='warm_retry' else 1,
                        'localizer_attempt_timeouts': [15,15,15,15],
                        'localizer_attempt_branches': [1,1,1],
                        'localizer_attempt_thresholds': [10000,10000,10000],
                        'scranfilize_loc': 'direct/vendor/scranfilize/scranfilize',
                        'cadical_loc': 'direct/vendor/kissat/build/kissat', 'localizer_loc': binary,
                        'localizer_native_time_limit': True, 'warm_start_retries': True,
                        'feedback_rounds': 3 if treatment=='core_feedback' else 0,
                        'feedback_max_relaxed': 256, 'feedback_max_solves': 256,
                        'feedback_seconds': 10, 'feedback_conflict_budget': 1000,
                        'solver_timeout': 90, 'continue_if_realized': False}
            config = out/'input_settings.json'
            config.write_text(json.dumps(settings, indent=2)+'\n')
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = time.perf_counter()
            with (out/'console.log').open('w') as log:
                process = subprocess.run([sys.executable,'-u','PointSAT.py',str(config)], stdout=log, stderr=subprocess.STDOUT, timeout=600)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            summary = json.loads((out/'summary.json').read_text())
            entry = {'problem': problem, 'n': n, 'treatment': treatment, 'settings': settings,
                     'wall_seconds': time.perf_counter()-start,
                     'cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                     'returncode': process.returncode, 'summary': summary}
            manifest['runs'].append(entry)
            (directory/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
            print(json.dumps(entry), flush=True)


if __name__=='__main__':
    main()
