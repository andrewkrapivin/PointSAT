"""Deterministic I/O replay: isolate file layout, not solver/search speed."""
import argparse
from contextlib import redirect_stdout
import concurrent.futures
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import tempfile
import time
from unittest.mock import patch

from .geometry import read_points, real_text
from .store import RunStore
from .workflow import ROOT


class InlineExecutor:
    def __init__(self, **kwargs):
        self._processes = {}
    def submit(self, function, job):
        result = concurrent.futures.Future()
        result.set_result(function(job))
        return result
    def shutdown(self, **kwargs):
        pass


def benchmark(samples=500, repeats=3):
    from improvements.pipeline import runner
    points = read_points(ROOT/'direct/seeds/paper23.pts')
    realization = real_text(points)
    literals = [i if i % 3 else -i for i in range(1, math.comb(23, 3)+1)]
    solution = 'v '+' '.join(map(str, literals))+' 0'
    rows = []
    with tempfile.TemporaryDirectory(prefix='pointsat-storage-bench-') as temporary:
        directory = Path(temporary)
        base = directory/'fixture.cnf'
        base.write_text('p cnf 1771 0\n')
        for repeat in range(repeats):
            for mode in (('legacy', 'sqlite') if repeat % 2 == 0 else ('sqlite', 'legacy')):
                out = directory/f'{repeat}-{mode}'
                peak = 0
                def fake(job):
                    nonlocal peak
                    if job['type'] == 'SAT':
                        return dict(job, satisfiable=True, solution=solution, original_solution=solution,
                                    status='SATISFIABLE', stage_seconds={})
                    if job.get('warm_start_file') and not Path(job['warm_start_file']).is_file():
                        raise AssertionError('Lost warm-start file')
                    file = Path(job['realization_file'])
                    file.write_text(realization)
                    archives = []
                    for i in range(3):
                        path = Path(str(file)+f'.archive-{i:02}.real')
                        path.write_text(realization)
                        archives.append({'file': str(path), 'violations': 5})
                    peak = max(peak, len(list(file.parent.iterdir())))
                    return dict(job, realized=False, status='PARTIAL', violations=5,
                                general_position=True, actual_model=literals, archive_audits=archives, stage_seconds={})
                settings = dict(base_file=str(base), output_folder=str(out), n=23, workers=1,
                                n_solutions=samples, localizer_attempt_levels=2,
                                localizer_attempt_timeouts=[1, 1], localizer_attempt_thresholds=[10],
                                localizer_attempt_branches=[1], warm_start_retries=True,
                                output_storage=mode, quiet_progress=True)
                begin, cpu = time.perf_counter(), time.process_time()
                with patch.object(runner, 'ProcessPoolExecutor', InlineExecutor), patch.object(runner, '_process_job', side_effect=fake), redirect_stdout(io.StringIO()):
                    summary = runner.run_pipeline(settings)
                wall, cpu = time.perf_counter()-begin, time.process_time()-cpu
                files = [p for p in out.rglob('*') if p.is_file()]
                if mode == 'sqlite':
                    with RunStore(out/'run.sqlite', readonly=True) as store:
                        events = list(store.events())
                else:
                    events = [json.loads(line) for line in (out/'raw_results.jsonl').read_text().splitlines()]
                core = [{key: row.get(key) for key in ('id', 'original_id', 'type', 'status', 'solution',
                                                       'actual_model', 'violations', 'seed', 'attempt')}
                        for row in sorted(events, key=lambda event: event['id'])]
                digest = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
                rows.append(dict(repeat=repeat, storage=mode, wall_seconds=wall, cpu_seconds=cpu,
                                 files=len(files), logical_bytes=sum(p.stat().st_size for p in files),
                                 allocated_bytes=sum(p.stat().st_blocks*512 for p in files),
                                 peak_temporary_files=peak, events=len(events), payload_hash=digest))
    groups = {}
    for mode in ('legacy', 'sqlite'):
        selected = [row for row in rows if row['storage'] == mode]
        groups[mode] = {key: statistics.median(row[key] for row in selected)
                        for key in ('wall_seconds', 'cpu_seconds', 'files', 'logical_bytes', 'allocated_bytes', 'peak_temporary_files')}
    return dict(protocol='Deterministic replay of representative 23-point SAT/native records. No SAT or Localizer calls; timings measure storage/coordinator only.',
                samples=samples, native_records_per_sample=2, repeats=repeats,
                identical_semantic_payloads=len({row['payload_hash'] for row in rows}) == 1,
                groups=groups, runs=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=500)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.samples < 1 or args.repeats < 1:
        parser.error('samples and repeats must be positive')
    output = Path(args.out)
    if output.exists():
        parser.error('output exists; choose a fresh result file')
    result = benchmark(args.samples, args.repeats)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as file:
        json.dump(result, file, indent=2)
        file.write('\n')
    print(json.dumps({key: result[key] for key in ('identical_semantic_payloads', 'groups')}, indent=2))
    return 0 if result['identical_semantic_payloads'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
