#!/usr/bin/env python3
"""Make a separate, explicitly excluded smoke registration from frozen code.

No search is launched and the parent study is never modified. The known
positive control supplies only its SAT assignment, never its coordinates.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', required=True)
    parser.add_argument('--control-registration', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report-output', required=True)
    args = parser.parse_args()
    source = Path(args.registration).resolve()
    control = Path(args.control_registration).resolve()
    out = Path(args.output).resolve()
    report = Path(args.report_output).resolve()
    if out.exists() or report.exists():
        raise ValueError('Smoke and report outputs must be new directories')
    config = json.loads(source.read_text())
    for name, digest in config['frozen_sha256'].items():
        if hashlib.sha256((source.parent/'frozen'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen source drift: '+name)
    fresh = copy.deepcopy(next(c for c in config['cases'] if c['id'] == 'symmetry19-0'))
    positive = copy.deepcopy(fresh)
    old = json.loads(control.read_text())['cases'][0]
    positive.update(id='positive-control19', primary_model=old['primary_model'], seed=old['seed'],
                    canonical_sha256=None, source_case_metadata={'smoke': 'known positive SAT assignment'})
    spec = importlib.util.spec_from_file_location('smoke_orientation_map', source.parent/'frozen/orientation_map.py')
    adapter_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter_module)
    adapter = adapter_module.OrientationMap(config['paths']['mapping'], 19)
    positive['initial_full_sha256'] = hashlib.sha256(adapter.orientations(positive['primary_model']).encode()).hexdigest()
    fresh['id'] = 'fresh-smoke19'
    arms = ['original', 'v4_fixed', 'v4_feedback']
    for case in (positive, fresh):
        case['condition_order'] = arms.copy()
    config.update(cases=[positive, fresh], family_arms={'symmetry19': arms},
                  arms_for_family={'symmetry19': arms}, horizon_seconds=60,
                  milestones=[30, 60], report_output=str(report),
                  selection='SMOKE ONLY, EXCLUDED from main results: known-positive SAT assignment and first fresh target; no coordinate seeds.',
                  budget_scope='SMOKE ONLY: 60 total wall seconds, including preparation, search, feedback and online verification.',
                  smoke_only=True, parent_registration=str(source),
                  parent_registration_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    config['source_registrations'] += [{'path': str(control), 'sha256': hashlib.sha256(control.read_bytes()).hexdigest()}]
    out.mkdir(parents=True)
    shutil.copytree(source.parent/'frozen', out/'frozen')
    config['paths'] = {key: str(out/'frozen'/Path(value).name) for key, value in config['paths'].items()}
    (out/'registration.json').write_text(json.dumps(config, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'registration': str(out/'registration.json'), 'smoke_only': True,
                      'trajectories': 6, 'maximum_primary_wall_seconds_two_workers': 180,
                      'searches_launched': 0}))


if __name__ == '__main__':
    main()
