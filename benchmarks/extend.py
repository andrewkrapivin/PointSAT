#!/usr/bin/env python3
"""Freeze disjoint prospective targets with an existing experiment's policy."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import shutil
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--parent', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--offset', type=int, default=4)
    p.add_argument('--targets', type=int, default=4)
    args = p.parse_args()
    parent = Path(args.parent).resolve()
    config = json.loads(parent.read_text())
    root = Path(config['root'])
    out = Path(args.output).resolve()
    assert args.offset >= 0 and args.targets > 0
    assert not out.exists(), 'Never overwrite a registration'
    for name, digest in config['frozen_sha256'].items():
        assert sha(parent.parent/'frozen'/name) == digest
    for path, digest in config['binary_sha256'].items():
        assert sha(path) == digest
    cases = []
    for family in ('mixed23', 'holes29', 'gons32', 'caps26'):
        seen, unique = set(), []
        for path in sorted((root/'improvements/benchmarks/overnight/runs').glob(family+'-*/case_result.json')):
            record = json.loads(path.read_text())
            if record.get('sat', {}).get('returncode') != 10:
                continue
            digest = record['orientation_sha256']
            if digest in seen:
                continue
            seen.add(digest)
            case = dict(record['case'])
            case.update(orientation=str((path.parent/'target.or').resolve()), orientation_sha256=digest)
            case['cnf'] = str(root/case['cnf'])
            unique.append(case)
        selected = unique[args.offset:args.offset+args.targets]
        assert len(selected) == args.targets
        cases.extend(selected)
    previous = {c['orientation_sha256'] for c in config['cases']}
    assert not previous.intersection(c['orientation_sha256'] for c in cases)
    jobs = [{'case': c, 'seed': seed, 'arm': arm} for c in cases for seed in config['seeds']
            for arm in ('warm_retry', 'core_feedback')]
    random.Random(20260906).shuffle(jobs)
    config = copy.deepcopy(config)
    config.update(registered_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  cases=cases, jobs=jobs, phase='prospective_extension',
                  parent_registration=str(parent), parent_registration_sha256=sha(parent),
                  selection_offset=args.offset, targets_per_family=args.targets,
                  no_tuning=True, job_shuffle_seed=20260906,
                  sampling=f'Unique SAT targets at zero-based positions {args.offset}..{args.offset+args.targets-1} '
                           'in the same lexicographically ordered reused corpus; disjoint from the pilot. '
                           'Policy, helpers, native binary, seeds and budgets copied unchanged from the pilot.')
    out.mkdir(parents=True)
    shutil.copytree(parent.parent/'frozen', out/'frozen', ignore=shutil.ignore_patterns('__pycache__'))
    for name, digest in config['frozen_sha256'].items():
        assert sha(out/'frozen'/name) == digest
    (out/'registration.json').write_text(json.dumps(config, indent=2)+'\n')
    print(json.dumps({'registration': str(out/'registration.json'),
                      'sha256': sha(out/'registration.json'), 'trials': len(jobs),
                      'case_ids': [c['id'] for c in cases]}))


if __name__ == '__main__':
    main()
