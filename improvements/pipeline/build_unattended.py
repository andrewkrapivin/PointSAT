#!/usr/bin/env python3
"""Freeze a reproducible two-slot portfolio for the root deadline supervisor."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
CNFS = {'mixed23':('7gon-6hole-23-compact.cnf',23),
        'holes29':('6hole-29-compact.cnf',29),
        'gons32':('7gon-32.cnf',32),
        'caps26':('7gon-no-5-cap-no-sb-26.cnf',26),
        'symmetry19':('improvements/pipeline/verified19/with_two_verified_cuts.cnf',19)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='improvements/pipeline/unattended_20260905')
    parser.add_argument('--jobs',type=int,default=120)
    args = parser.parse_args()
    directory = ROOT/args.output
    directory.mkdir(parents=True,exist_ok=True)
    manifest_file = directory/'jobs.json'
    if manifest_file.exists():
        raise SystemExit('Refusing to overwrite a frozen job manifest')
    frozen = directory/'frozen'
    snapshot = {}
    for name in ('PointSAT.py','flippable2.py','sat_orient_conversion.py',
                 'improvements/pipeline/runner.py','improvements/pipeline/orientation_map.py',
                 'improvements/pipeline/verified_cuts.py','improvements/benchmarks/verify_bfp.py'):
        target = frozen/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
        snapshot[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    for name in ('improvements/__init__.py','improvements/pipeline/__init__.py','improvements/benchmarks/__init__.py'):
        target = frozen/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'improvements/pipeline/frozen_package_init.py',target)
        snapshot[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    cycle = ['mixed23','symmetry19','gons32','mixed23','holes29','caps26']
    jobs, families_seen = [], {}
    for index in range(args.jobs):
        family = cycle[index%len(cycle)]
        count = families_seen.get(family,0)
        families_seen[family] = count+1
        base,n = CNFS[family]
        strategy = 'hash' if family=='mixed23' and count%3==2 else 'target_margin'
        label = f'job{index:03d}-{family}-{strategy}'
        out = directory/'runs'/label
        settings = {'base_file':base,'n':n,'problem_family':family,
                    'workers':1,'worker_max_threads':1,'remove_flippable':True,
                    'solution_generation':'scranfilize','n_solutions':6,
                    'sat_seed_start':10000+100*index,'seed':700001+31*index,
                    'scranfilize_loc':'direct/vendor/scranfilize/scranfilize',
                    'cadical_loc':'direct/vendor/kissat/build/kissat',
                    'sat_extra_args':['--quiet','--plain'],'solver_timeout':90,
                    'localizer_loc':'improvements/localizer/localizer_v4',
                    'localizer_extra_args':['--line-every','10','--min-radius','0.000001','-q'],
                    'localizer_native_time_limit':True,'localizer_archive_candidates':10,
                    'localizer_attempt_levels':1,'localizer_attempt_timeouts':[15],
                    'warm_start_retries':True,'feedback_rounds':3,
                    'feedback_max_relaxed':256,'feedback_max_solves':256,
                    'feedback_seconds':10,'feedback_conflict_budget':1000,
                    'feedback_core_choice':strategy,'flippability_model_cache_size':128,
                    'radial_relabel_check':family in ('mixed23','holes29','gons32'),
                    'feedback_radial_scaffold':family in ('mixed23','holes29','gons32')}
        if family=='holes29':
            settings.update(n_solutions=4,solver_timeout=180)
            settings['sat_extra_args'] = [['--quiet','--sat'],['--quiet'],['--quiet','--plain']][count%3]
        if family=='caps26':
            settings['localizer_loc'] = 'improvements/localizer/localizer_v6'
            settings['localizer_extra_args'].append('--ordered-x')
        if family=='symmetry19':
            settings.update(solution_generation='scranfilize',n_solutions=4,
                            orientation_map_file='improvements/symmetry19/variants/mapping.json',
                            audit_base_file='convex_hexagon_inside_19_3sym.cnf',
                            nonrealizability_proof_files=['improvements/realizability/results/supplied19-rational.json',
                                                        'improvements/realizability/results/relaxed002.json'],
                            feedback_rounds=3,feedback_max_relaxed=128,feedback_max_solves=128,
                            feedback_conflict_budget=2000,localizer_attempt_timeouts=[30])
            settings['sat_extra_args'] = [['--quiet','--plain'],['--quiet','--sat']][count%2]
            settings['localizer_extra_args'] += ['-c','improvements/symmetry19/decoded/center19-adjacent.cycles',
                                                  '-f','improvements/symmetry19/decoded/center19-adjacent.fixed']
        config = directory/'configs'/f'{label}.json'
        config.parent.mkdir(exist_ok=True)
        config.write_text(json.dumps(settings,indent=2)+'\n')
        jobs.append({'label':label,'command':[sys.executable,str(frozen/'PointSAT.py'),str(config),'--out',str(out)],
                     'max_seconds':900 if family=='holes29' else 600,'workers':1,'output':str(out),
                     'audit_command':[sys.executable,str(ROOT/'improvements/pipeline/audit_run.py'),
                                      '--input',str(out),'--output',str(out/'audit'),'--family',family]})
    manifest_file.write_text(json.dumps(jobs,indent=2)+'\n')
    metadata = {'description':'Oversubscribed deterministic queue; supervisor deadline stops unused jobs. At mosttwo queue workers, one CPUworker/native thread perjob.',
                'deadline_utc':'2026-09-05T14:00:00+00:00','jobs':len(jobs),'family_counts':families_seen,
                'pipeline_snapshot_sha256':snapshot,
                'cnf_sha256':{family:hashlib.sha256((ROOT/base).read_bytes()).hexdigest()for family,(base,n)in CNFS.items()},
                'native_sha256':{version:hashlib.sha256((ROOT/f'improvements/localizer/localizer_{version}').read_bytes()).hexdigest()for version in ('v4','v6')}}
    (directory/'freeze.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(manifest_file)


if __name__=='__main__':
    main()
