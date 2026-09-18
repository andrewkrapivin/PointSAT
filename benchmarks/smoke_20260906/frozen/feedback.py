import time, math, hashlib
from sat_orient_conversion import integer_points

def orientation_margins(point_file, n, adapter=None):
    """Heuristic normalized squared altitudes; exact predicates still certify."""
    import itertools
    exact = integer_points(point_file)
    min_x, min_y = min(p[0] for p in exact), min(p[1] for p in exact)
    span = max(max(p[0] for p in exact)-min_x, max(p[1] for p in exact)-min_y, 1)
    points = [((p[0]-min_x)/span, (p[1]-min_y)/span) for p in exact]
    margins = {}
    for a, b, c in itertools.combinations(range(n), 3):
        x, y, z = points[a], points[b], points[c]
        determinant = (y[0]-x[0])*(z[1]-x[1])-(y[1]-x[1])*(z[0]-x[0])
        longest = max((x[0]-y[0])**2+(x[1]-y[1])**2, (x[0]-z[0])**2+(x[1]-z[1])**2,
                      (y[0]-z[0])**2+(y[1]-z[1])**2, 1e-300)
        rank = a+1+b*(b-1)//2+c*(c-1)*(c-2)//6
        variable = adapter.rank_to_variable[rank] if adapter else rank
        margin = determinant*determinant/longest
        margins[variable] = min(margins.get(variable, math.inf), margin)
    return margins

def core_guided_feedback(solver, actual_model, settings, seed, preferred_variables=None, margins=None):
    """Keep a geometric scaffold while relaxing only assumptions in UNSAT cores.

    No permanent clauses are added. A failed Localizer run is NOT a proof of
    non-realizability and never licenses blocking its abstract orientation type.
    Conflict limits bound each SAT query; a wall check bounds the query loop.
    """
    start = time.perf_counter()
    assumptions = dict((abs(lit), lit) for lit in actual_model)
    removed, calls, core_sizes = [], 0, []
    preferred, margins = set(preferred_variables or []), margins or {}
    choice = settings['feedback_core_choice']
    termination = 'SOLVE_LIMIT'
    solver.set_phases(actual_model)
    try:
        for _ in range(settings['feedback_max_solves']):
            if time.perf_counter()-start >= settings['feedback_seconds']:
                termination = 'TIME_LIMIT'
                break
            solver.conf_budget(settings['feedback_conflict_budget'])
            status = solver.solve_limited(assumptions=list(assumptions.values()))
            calls += 1
            if status is True:
                model = {abs(lit): lit for lit in solver.get_model()}
                projected = [model[abs(lit)] for lit in actual_model]
                return projected, {'sat_calls': calls, 'relaxed': removed, 'core_sizes': core_sizes,
                                   'orientation_changes': sum(a != b for a, b in zip(projected, actual_model)),
                                   'seconds': time.perf_counter()-start, 'status': 'SAT', 'core_choice': choice}
            if status is None:
                termination = 'CONFLICT_LIMIT'
                break
            core = solver.get_core() or []
            core_sizes.append(len(core))
            if not core or len(removed) >= settings['feedback_max_relaxed']:
                termination = 'EMPTY_CORE' if not core else 'RELAXATION_LIMIT'
                break
            # Reproducible tie-break, varied across rounds; no geometric claim
            # is made that this greedy deletion is a minimum correction set.
            def priority(literal):
                variable = abs(literal)
                target = 0 if not choice.startswith('target') or variable in preferred else 1
                margin = margins.get(variable, math.inf) if 'margin' in choice else 0
                tie = hashlib.sha256(f'{seed}:{len(removed)}:{literal}'.encode()).digest()
                return target, margin, tie
            chosen = min(core, key=priority)
            assumptions.pop(abs(chosen))
            removed.append(chosen)
    finally:
        solver.conf_budget(-1)
    return None, {'sat_calls': calls, 'relaxed': removed, 'core_sizes': core_sizes,
                  'seconds': time.perf_counter()-start, 'status': 'BUDGET_EXHAUSTED',
                  'termination_reason': termination, 'core_choice': choice}
