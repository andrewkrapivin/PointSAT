#!/usr/bin/env python3
"""Prepare a one-worker warm-start/core-feedback experiment on the user's C3 CNF."""
import json
from pathlib import Path

directory = Path('improvements/pipeline/symmetry19_feedback')
directory.mkdir(exist_ok=True)
model = json.loads(Path('improvements/symmetry19/variants/model002.json').read_text())['primary_model']
cube = directory/'initial.cubes'
cube.write_text('a '+' '.join(map(str, model))+' 0\n')
settings = {
    'base_file': 'convex_hexagon_inside_19_3sym.cnf', 'n': 19,
    'orientation_map_file': 'improvements/symmetry19/variants/mapping.json',
    'solution_generation': 'subcases', 'cubes_file': str(cube),
    'cadical_loc': 'direct/vendor/kissat/build/kissat',
    'localizer_loc': 'improvements/localizer/localizer_v4',
    'localizer_extra_args': ['-c','improvements/symmetry19/decoded/center19-adjacent.cycles',
                             '-f','improvements/symmetry19/decoded/center19-adjacent.fixed',
                             '--line-every','10','--min-radius','0.000001','-q'],
    'localizer_archive_candidates': 10,
    'initial_warm_start_file': 'improvements/symmetry19/search/model002-relaxed-symmetric/points.real',
    'output_folder': str(directory/'run'), 'workers': 1, 'worker_max_threads': 1,
    'remove_flippable': True, 'localizer_attempt_levels': 1,
    'localizer_attempt_timeouts': [30], 'localizer_native_time_limit': True,
    'warm_start_retries': True, 'feedback_rounds': 12,
    'feedback_max_relaxed': 128, 'feedback_max_solves': 128,
    'feedback_seconds': 10, 'feedback_conflict_budget': 2000,
    'seed': 19103, 'solver_timeout': 90,
}
target = directory/'settings.json'
if target.exists():
    raise SystemExit('Refusing to overwrite19-point experiment settings')
target.write_text(json.dumps(settings, indent=2)+'\n')
print(target)
