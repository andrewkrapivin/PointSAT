#!/usr/bin/env python3
"""Serial fixed-work v6/optimization comparison; stdlib only, bounded children."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import random
import resource
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=300000)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if min(args.iterations, args.repeats) < 1:
        raise SystemExit('Positive iteration and repetition limits required')
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    variants = {'v6':ROOT/'build/localizer_v6', 'sampling':ROOT/'build/localizer_sampling',
                'atomic':ROOT/'build/localizer_atomic', 'both':ROOT/'build/localizer_both'}
    families = ['mixed23','holes29','gons32','caps26']
    registration = {'description':'One serial native process at a time; fixed iterations and identical seed/input. Caps26 keeps --ordered-x in every arm. No speed claim unless coordinates and all search counters match.',
                    'arguments':vars(args)|{'output':str(folder)}, 'platform':platform.platform(),
                    'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
                    'native_sha256':{name:digest(path) for name,path in variants.items()},
                    'input_sha256':{family:digest(ROOT/'benchmarks/inputs'/f'{family}.or') for family in families}}
    (folder/'registration.json').write_text(json.dumps(registration,indent=2)+'\n')
    records = []
    rng = random.Random(6062239)
    for family in families:
        for repeat in range(args.repeats):
            order = list(variants)
            rng.shuffle(order)
            paired = {}
            for name in order:
                stem = folder/f'{family}-r{repeat}-{name}'
                output = stem.with_suffix('.real')
                command = [str(variants[name]),str(ROOT/'benchmarks/inputs'/f'{family}.or'),
                           '-I',str(args.iterations),'-i','10','-r','30000','-t','1',
                           '-s',str(args.seed),'-q','-o',str(output)]
                if family == 'caps26':
                    command.append('--ordered-x')
                before = resource.getrusage(resource.RUSAGE_CHILDREN)
                start = time.perf_counter()
                process = subprocess.run(command,text=True,capture_output=True,timeout=60)
                elapsed = time.perf_counter()-start
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                stem.with_suffix('.stdout').write_text(process.stdout)
                stem.with_suffix('.stderr').write_text(process.stderr)
                if process.returncode:
                    raise RuntimeError(f'{family}/{name} failed: {process.stderr}')
                stats = [json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')][-1]
                stats.pop('seconds')
                entry = {'family':family,'repeat':repeat,'variant':name,'command':command,
                         'wall_seconds':elapsed,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                         'coordinates_sha256':digest(output),'search_counters':stats}
                paired[name] = entry
                records.append(entry)
                with (folder/'raw.jsonl').open('a') as stream:
                    stream.write(json.dumps(entry)+'\n')
            for name in variants:
                if (paired[name]['coordinates_sha256'],paired[name]['search_counters']) != (paired['v6']['coordinates_sha256'],paired['v6']['search_counters']):
                    raise RuntimeError(f'Trajectory mismatch for {family}/repeat{repeat}/{name}; no performance claim allowed')
            print(json.dumps({'family':family,'repeat':repeat,'cpu_seconds':{k:round(v['cpu_seconds'],6) for k,v in paired.items()},'all_trajectories_identical':True}),flush=True)
    summary = {'registration':registration,'all_coordinate_and_counter_pairs_identical':True,'families':{}}
    for family in families:
        subset = [entry for entry in records if entry['family']==family]
        medians = {name:statistics.median(entry['cpu_seconds'] for entry in subset if entry['variant']==name) for name in variants}
        summary['families'][family] = {'median_cpu_seconds':medians,
            'cpu_speedup_over_v6':{name:medians['v6']/value for name,value in medians.items()},
            'actual_iterations':subset[0]['search_counters']['iterations'],
            'proposals':subset[0]['search_counters']['proposals'],
            'best_violations':subset[0]['search_counters']['best_violations']}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary['families'],indent=2))


if __name__=='__main__':
    main()
