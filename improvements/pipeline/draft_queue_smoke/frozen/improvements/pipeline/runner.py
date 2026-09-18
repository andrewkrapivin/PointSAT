"""Bounded SAT -> orientation relaxation -> exact-checked Localizer pipeline.

One persistent SAT checker is kept per process worker. External stages run in
their own process groups; every result, including errors and timeouts, is logged.
"""
import argparse
import atexit
from collections import deque, OrderedDict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from flippable2 import FlippabilityChecker
from sat_orient_conversion import get_orientations, inspect_realization, radial_relabel, count_caps, integer_points
from improvements.pipeline.orientation_map import OrientationMap

DEFAULTS = {
    "output_folder": "out", "workers": 1, "worker_max_threads": 1,
    "remove_flippable": True, "localizer_attempt_levels": 4,
    "localizer_attempt_timeouts": [15, 75, 300, 1500],
    "localizer_attempt_branches": [1, 1, 1],
    "localizer_attempt_thresholds": [10, 7, 4], "n": 23,
    "localizer_loc": "localizer/src/localizer",
    "cadical_loc": "cadical/debug/cadical", "continue_if_realized": False,
    "solution_generation": "scranfilize", "n_solutions": 1,
    "solver_timeout": 90, "scranfilize_timeout": 60,
    "interrupt_grace_seconds": 2, "seed": 1, "sat_seed_start": 0,
    "localizer_iterations": 10, "localizer_restarts": 30000,
    "localizer_extra_args": [], "sat_extra_args": ["--quiet", "--plain"],
    "warm_start_retries": False, "localizer_warm_start_flag": "-w",
    "localizer_native_time_limit": False, "stop_on_solution": False,
    "feedback_rounds": 0, "feedback_max_relaxed": 64,
    "feedback_max_solves": 64, "feedback_conflict_budget": 1000,
    "feedback_seconds": 5, "feedback_remove_flippable": True,
    "radial_relabel_check": False, "problem_family": None,
    "orientation_map_file": None,
    "initial_warm_start_file": None, "localizer_archive_candidates": 0,
    "shutdown_grace_seconds": 10,
    "feedback_core_choice": "hash", "feedback_radial_scaffold": False,
    "flippability_model_cache_size": 128,
}
_state = None
_active_process = None
_stop_requested = False


def executable(path):
    return str(Path(path).resolve()) if Path(path).exists() else str(path)


def parse_sat_output(data, n, projection=None):
    """Parse competition output; comments and UNKNOWN are not assignments."""
    status, model, seen_status = "UNKNOWN", {}, False
    for raw in (data or "").splitlines():
        parts = raw.strip().split()
        if not parts or parts[0] == "c":
            continue
        if parts[0] == "s":
            if len(parts) != 2 or parts[1] not in {"SATISFIABLE", "UNSATISFIABLE", "UNKNOWN"}:
                raise ValueError("Malformed SAT status line")
            if seen_status and status != parts[1]:
                raise ValueError("Conflicting SAT status lines")
            status = parts[1]
            seen_status = True
        elif parts[0] == "v":
            for token in parts[1:]:
                literal = int(token)
                if not literal:
                    continue
                if abs(literal) in model and model[abs(literal)] != literal:
                    raise ValueError("Contradictory literals in SAT model")
                model[abs(literal)] = literal
    variables = list(projection) if projection is not None else list(range(1, math.comb(n, 3)+1))
    count = len(variables)
    orientations = [model[i] for i in variables if i in model]
    if status == "SATISFIABLE" and len(orientations) != count:
        raise ValueError(f"Incomplete orientation model: {len(orientations)}/{count}")
    return status, orientations if status == "SATISFIABLE" else []


def process_sat_str(data, n):
    status, model = parse_sat_output(data, n)
    return "v " + " ".join(map(str, model)) + " 0" if status == "SATISFIABLE" else ""


def _signal_group(process, sig):
    try:
        if os.name == "posix":
            os.killpg(process.pid, sig)
        else:
            process.send_signal(sig)
    except ProcessLookupError:
        pass


def run_process(task, command, timeout, interrupt=False, grace=2):
    """Drain output and reap a whole process group with bounded escalation."""
    global _active_process
    start = time.perf_counter()
    result = {"command": command, "stdout": "", "stderr": "", "returncode": None,
              "timed_out": False, "error": None}
    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=(os.name == "posix"))
        _active_process = process
        try:
            out, err = process.communicate(task, timeout=timeout)
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            _signal_group(process, signal.SIGINT if interrupt else signal.SIGKILL)
            try:
                out, err = process.communicate(timeout=grace)
            except subprocess.TimeoutExpired:
                _signal_group(process, signal.SIGKILL)
                out, err = process.communicate(timeout=grace)
        result.update(stdout=out, stderr=err, returncode=process.returncode)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        if process is not None:
            _signal_group(process, signal.SIGKILL)
            try:
                process.communicate(timeout=grace)
            except (subprocess.TimeoutExpired, OSError):
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()
            result["returncode"] = process.returncode
    finally:
        _active_process = None
        result["elapsed"] = time.perf_counter()-start
    return result


def run_external(task, program_params, timeout=None, kill_with_interrupt=False):
    """Compatibility wrapper; solver exit codes 10 and 20 are normal exits."""
    result = run_process(task, program_params, timeout, kill_with_interrupt)
    success = not result["timed_out"] and result["error"] is None and result["returncode"] in (0, 10, 20)
    return success, result["stdout"], result["stderr"] or result["error"], result["elapsed"]


def _terminate_worker(signum, frame):
    if _active_process is not None:
        _signal_group(_active_process, signal.SIGKILL)
        try:
            _active_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
    os._exit(128+signum)


def _request_worker_stop(signum, frame):
    """Let communicate() drain output while the native solver saves its best."""
    global _stop_requested
    _stop_requested = True
    if _active_process is not None:
        _signal_group(_active_process, signal.SIGINT)


def _init_worker(base_formula, settings):
    global _state, _stop_requested
    _stop_requested = False
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, _terminate_worker)
    signal.signal(signal.SIGUSR1, _request_worker_stop)
    _state = {"formula": base_formula, "settings": settings, "checker": None,
              'orientation_map': OrientationMap(settings['orientation_map_file'], settings['n']) if settings['orientation_map_file'] else None}


def _checker(timings):
    if _state["checker"] is None:
        begin = time.perf_counter()
        _state["checker"] = FlippabilityChecker(_state["formula"])
        atexit.register(_state["checker"].close)
        timings["checker_initialization"] = time.perf_counter()-begin
    return _state["checker"]


def _check_flippability(checker, model):
    """Memoize exact repeated projected assignments, preserving literal order."""
    begin = time.perf_counter()
    cache = _state.setdefault('flippability_cache', OrderedDict())
    key = tuple(model.split())
    capacity = _state['settings']['flippability_model_cache_size']
    if capacity and key in cache:
        flips, required, stats = cache.pop(key)
        cache[key] = flips, required, stats
        checker.last_stats = dict(stats, cache_hit=True, cached_flip_sat_calls=stats.get('flip_sat_calls',0),
                                  flip_sat_calls=0, initial_sat_calls=0, seconds=time.perf_counter()-begin)
        return set(flips), list(required)
    flips, required = checker.check(model)
    checker.last_stats = dict(checker.last_stats, cache_hit=False)
    if capacity:
        cache[key] = frozenset(flips), tuple(required), dict(checker.last_stats)
        while len(cache) > capacity:
            cache.popitem(last=False)
    return flips, required


def _add_assumptions(formula, literals):
    lines = formula.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("p cnf "):
            parts = line.split()
            parts[3] = str(int(parts[3])+len(literals))
            lines[i] = " ".join(parts)
            break
    else:
        raise ValueError("CNF has no problem header")
    return "\n".join(lines) + "\n" + "".join(f"{int(x)} 0\n" for x in literals)


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


def _process_job(job):
    """An individual bad output must not strand the coordinator waiting."""
    start = time.perf_counter()
    result = dict(job)
    settings, timings = _state["settings"], {}
    result.update(satisfiable=False, realized=False, status="ERROR", stage_seconds=timings)
    if _stop_requested:
        return dict(result, status='CANCELLED', time_taken=0, interrupted=True)
    try:
        if job["type"] == "SAT":
            formula = _state["formula"]
            if settings["solution_generation"] == "scranfilize":
                stage = run_process(formula, [executable(settings["scranfilize_loc"]), "-P", "-f", "0", "-v", "0", "-s", str(job["scranfilize_seed"])], settings["scranfilize_timeout"])
                timings["scranfilize"] = stage["elapsed"]
                if stage["returncode"] != 0 or stage["timed_out"] or stage["error"]:
                    raise RuntimeError(f"scranfilize failed: {stage['error'] or stage['stderr']}")
                formula = stage["stdout"]
            elif settings["solution_generation"] == "subcases":
                formula = _add_assumptions(formula, job["assumptions"])
            stage = run_process(formula, [executable(settings["cadical_loc"])] + settings["sat_extra_args"], settings["solver_timeout"])
            timings["sat"] = stage["elapsed"]
            result["solver_returncode"] = stage["returncode"]
            if stage["timed_out"]:
                result["status"] = "TIMEOUT"
            elif stage["error"] or stage["returncode"] not in (0, 10, 20):
                raise RuntimeError(f"SAT solver failed: {stage['error'] or stage['stderr']}")
            else:
                adapter = _state.get('orientation_map')
                status, literals = parse_sat_output(stage["stdout"], settings["n"], adapter.variables if adapter else None)
                if (stage["returncode"] == 20 and status == "SATISFIABLE") or (stage["returncode"] == 10 and status != "SATISFIABLE"):
                    raise ValueError("SAT exit status conflicts with output")
                result["status"] = status
                result["satisfiable"] = status == "SATISFIABLE"
                if result["satisfiable"]:
                    result["solution"] = "v " + " ".join(map(str, literals)) + " 0"
                    if settings["remove_flippable"]:
                        checker = _checker(timings)
                        begin = time.perf_counter()
                        flippable, required = _check_flippability(checker, result["solution"])
                        timings["flippability"] = time.perf_counter()-begin
                        result["flippability_stats"] = dict(checker.last_stats)
                        result["original_solution"] = result["solution"]
                        result["flippable"] = sorted(flippable)
                        result["solution"] = "v " + " ".join(map(str, required)) + " 0"
        elif job["type"] == "Realize":
            command = [executable(settings["localizer_loc"]), job["orientations_file"], "-t", str(settings["worker_max_threads"]), "-i", str(settings["localizer_iterations"]), "-r", str(settings["localizer_restarts"]), "-s", str(job["seed"]), "-o", job["realization_file"]]
            command.extend(settings["localizer_extra_args"])
            if settings['localizer_archive_candidates']:
                command.extend(['--archive-prefix', job['realization_file']+'.archive'])
            if job.get("warm_start_file"):
                command.extend([settings["localizer_warm_start_flag"], job["warm_start_file"]])
            if settings["localizer_native_time_limit"]:
                command.extend(["-T", str(job["timeout"])])
            timeout = job["timeout"] + (settings["interrupt_grace_seconds"] if settings["localizer_native_time_limit"] else 0)
            stage = run_process("", command, timeout, True, settings["interrupt_grace_seconds"])
            timings["localizer"] = stage["elapsed"]
            result.update(localizer_returncode=stage["returncode"], localizer_timed_out=stage["timed_out"], localizer_command=command)
            if stage["error"]:
                raise RuntimeError(stage["error"])
            if not Path(job["realization_file"]).is_file():
                raise RuntimeError("Localizer produced no coordinates: " + stage["stderr"][-2000:])
            begin = time.perf_counter()
            inspected = inspect_realization(job["orientations_file"], job["realization_file"], settings["n"])
            timings["exact_decode"] = time.perf_counter()-begin
            result.update(violations=len(inspected["bad_vars"]), bad_vars=inspected["bad_vars"],
                          constraints_satisfied=inspected["valid"], general_position=inspected["general_position"],
                          point_count=inspected["point_count"])
            # A partial Localizer assignment may satisfy the CNF even when some
            # of its supplied orientation targets are violated.
            actual_model = inspected['sat_model']
            adapter = _state.get('orientation_map')
            result['feedback_preferred_variables'] = sorted({adapter.rank_to_variable[v] if adapter else v for v in inspected['bad_vars']})
            if actual_model is not None and adapter:
                actual_model, conflicts = adapter.project(actual_model)
                result['mapping_conflicts'] = conflicts
                result['mapping_consistent'] = not conflicts
            if actual_model is not None:
                checker = _checker(timings)
                begin = time.perf_counter()
                result["realized"] = checker.solver.solve(assumptions=actual_model) is True
                timings["cnf_check"] = time.perf_counter()-begin
                if settings['feedback_rounds']:
                    result['actual_model'] = actual_model
                if not result['realized'] and settings['radial_relabel_check']:
                    begin = time.perf_counter()
                    candidate = job['realization_file'] + '.radial.real'
                    relabelled = radial_relabel(job['realization_file'], candidate, settings['n'])
                    timings['radial_relabel'] = time.perf_counter()-begin
                    begin = time.perf_counter()
                    radial_sat = checker.solver.solve(assumptions=relabelled['sat_model']) is True
                    timings['radial_cnf_check'] = time.perf_counter()-begin
                    result['radial_relabel_satisfiable'] = radial_sat
                    if settings['feedback_radial_scaffold']:
                        result['feedback_actual_model'] = relabelled['sat_model']
                        result['feedback_warm_start_file'] = candidate
                        result['feedback_scaffold_permutation'] = relabelled['permutation']
                        # Old target mismatch IDs have different labels now.
                        if relabelled['permutation'] != list(range(1, settings['n']+1)):
                            result['feedback_preferred_variables'] = []
                    if radial_sat:
                        orientation_file = candidate + '.or'
                        Path(orientation_file).write_text(get_orientations(relabelled['sat_model'], settings['n']))
                        model_file = candidate + '.cnf.model'
                        Path(model_file).write_text('v '+' '.join(map(str, checker.solver.get_model()))+' 0\n')
                        result.update(realized=True, realized_after_relabel=True,
                                      accepted_realization_file=candidate,
                                      accepted_orientations_file=orientation_file,
                                      cnf_model_file=model_file,
                                      relabel_permutation=relabelled['permutation'],
                                      realization_kind='CNF-valid after unlabeled radial permutation')
                        certificate = candidate+'.certificate.json'
                        Path(certificate).write_text(json.dumps({'source_realization': job['realization_file'],
                            'accepted_realization': candidate, 'cnf': settings['base_file'],
                            'full_cnf_model': model_file, 'permutation_new_to_old': relabelled['permutation'],
                            'original_target_violations': result['violations'],
                            'original_target_realized': inspected['valid'], 'full_cnf_satisfiable': True}, indent=2)+'\n')
                        result['relabel_certificate_file'] = certificate
            result['full_cnf_satisfiable'] = result['realized']
            if result['realized'] and _requires_cap_check(settings):
                begin = time.perf_counter()
                result['convex_5_caps'] = count_caps(result.get('accepted_realization_file', job['realization_file']), 5)
                timings['exact_cap_check'] = time.perf_counter()-begin
                if result['convex_5_caps']:
                    result['realized'] = False
                    result['geometric_rejection'] = 'CNF-satisfying coordinates contain forbidden convex5-caps'
            result["status"] = "REALIZED" if result["realized"] else "PARTIAL"
            if result.get('geometric_rejection'):
                result['status'] = 'GEOMETRIC_REJECTION'
            if result.get('mapping_conflicts'):
                result['status'] = 'MAPPING_CONFLICT'
            if not result['realized'] and settings['localizer_archive_candidates']:
                begin = time.perf_counter()
                archive_audits, hashes = [], {hashlib.sha256(Path(job['realization_file']).read_bytes()).digest()}
                for index in range(settings['localizer_archive_candidates']):
                    candidate = job['realization_file']+f'.archive-{index:02d}.real'
                    if not Path(candidate).exists():
                        continue
                    digest = hashlib.sha256(Path(candidate).read_bytes()).digest()
                    if digest in hashes:
                        continue
                    hashes.add(digest)
                    audit = {'file': candidate}
                    try:
                        decoded = inspect_realization(job['orientations_file'], candidate, settings['n'])
                        archive_model = decoded['sat_model']
                        audit.update(violations=len(decoded['bad_vars']), general_position=decoded['general_position'])
                        if adapter and archive_model is not None:
                            archive_model, conflicts = adapter.project(archive_model)
                            audit['mapping_conflicts'] = len(conflicts)
                        if archive_model is not None:
                            checker = _checker(timings)
                            accepted = checker.solver.solve(assumptions=archive_model) is True
                            audit['full_cnf_satisfiable'] = accepted
                            if not accepted and settings['radial_relabel_check']:
                                radial_file = candidate+'.radial.real'
                                radial = radial_relabel(candidate, radial_file, settings['n'])
                                accepted = checker.solver.solve(assumptions=radial['sat_model']) is True
                                audit['radial_cnf_satisfiable'] = accepted
                                if accepted:
                                    candidate, archive_model = radial_file, radial['sat_model']
                                    audit['permutation_new_to_old'] = radial['permutation']
                            if accepted:
                                if _requires_cap_check(settings):
                                    audit['convex_5_caps'] = count_caps(candidate, 5)
                                    accepted = audit['convex_5_caps'] == 0
                            if accepted:
                                orientation_file = candidate+'.or'
                                Path(orientation_file).write_text(adapter.orientations(archive_model) if adapter else get_orientations(archive_model, settings['n']))
                                model_file = candidate+'.cnf.model'
                                Path(model_file).write_text('v '+' '.join(map(str, checker.solver.get_model()))+' 0\n')
                                certificate = candidate+'.certificate.json'
                                Path(certificate).write_text(json.dumps(dict(audit, accepted_realization=candidate,
                                    full_cnf_model=model_file, cnf=settings['base_file']), indent=2)+'\n')
                                result.update(realized=True, status='REALIZED', realized_via_archive=True,
                                    accepted_realization_file=candidate, accepted_orientations_file=orientation_file,
                                    cnf_model_file=model_file, archive_certificate_file=certificate,
                                    archive_target_violations=audit['violations'])
                    except ValueError as exc:
                        audit['error'] = str(exc)
                    archive_audits.append(audit)
                    if result['realized']:
                        break
                result['archive_audits'] = archive_audits
                timings['archive_exact_audit'] = time.perf_counter()-begin
            if stage["returncode"] not in (0, -signal.SIGINT) and not stage["timed_out"]:
                result["localizer_warning"] = stage["stderr"][-2000:]
        elif job['type'] == 'Feedback':
            checker = _checker(timings)
            margins = None
            if 'margin' in settings['feedback_core_choice']:
                begin = time.perf_counter()
                margins = orientation_margins(job['warm_start_file'], settings['n'], _state.get('orientation_map'))
                timings['feedback_margin_ranking'] = time.perf_counter()-begin
            projected, stats = core_guided_feedback(checker.solver, job['actual_model'], settings, job['seed'],
                                                     job.get('preferred_variables'), margins)
            result['feedback_stats'] = stats
            timings['core_feedback'] = stats['seconds']
            result['status'] = 'SAT_REPAIR' if projected is not None else 'FEEDBACK_UNRESOLVED'
            if projected is not None:
                model_str = 'v ' + ' '.join(map(str, projected)) + ' 0'
                result['original_solution'] = model_str
                if settings['feedback_remove_flippable']:
                    begin = time.perf_counter()
                    flippable, projected = _check_flippability(checker, model_str)
                    timings['feedback_flippability'] = time.perf_counter()-begin
                    result['flippable'] = sorted(flippable)
                    result['flippability_stats'] = dict(checker.last_stats)
                result['solution'] = 'v ' + ' '.join(map(str, projected)) + ' 0'
        else:
            raise ValueError(f"Unsupported job type: {job['type']}")
    except Exception as exc:
        result.update(status="ERROR", error=f"{type(exc).__name__}: {exc}")
    result["time_taken"] = time.perf_counter()-start
    if _stop_requested:
        result['interrupted'] = True
    return result


def _requires_cap_check(settings):
    return settings.get('problem_family') == 'caps26' or Path(settings.get('base_file', '')).name == '7gon-no-5-cap-no-sb-26.cnf'


def _save_realization(result, folder):
    if result.get('realized'):
        shutil.copy2(result.get('accepted_realization_file', result['realization_file']), folder)
        shutil.copy2(result.get('accepted_orientations_file', result['orientations_file']), folder)
        for key in ('cnf_model_file', 'relabel_certificate_file', 'archive_certificate_file'):
            if result.get(key):
                shutil.copy2(result[key], folder)


def normalize_settings(settings):
    settings = dict(DEFAULTS, **settings)
    for key in ("workers", "worker_max_threads", "n"):
        if not isinstance(settings[key], int) or settings[key] < (3 if key == "n" else 1):
            raise ValueError(f"Invalid {key}")
    levels = settings["localizer_attempt_levels"]
    if not isinstance(levels, int) or levels < 0:
        raise ValueError("localizer_attempt_levels must be a nonnegative integer")
    for key, count in (("localizer_attempt_timeouts", levels), ("localizer_attempt_branches", max(0, levels-1)), ("localizer_attempt_thresholds", max(0, levels-1))):
        if len(settings[key]) < count:
            raise ValueError(f"{key} needs at least {count} entries")
    for key in ("localizer_extra_args", "sat_extra_args"):
        if not isinstance(settings[key], list) or any(not isinstance(x, str) for x in settings[key]):
            raise ValueError(f"{key} must be a list of strings")
    if settings["solution_generation"] not in ("scranfilize", "subcases"):
        raise ValueError("solution_generation must be scranfilize or subcases")
    if any(float(x) <= 0 for x in settings["localizer_attempt_timeouts"][:levels]):
        raise ValueError("Localizer timeouts must be positive")
    for key in ('feedback_rounds', 'feedback_max_relaxed', 'feedback_max_solves', 'feedback_conflict_budget', 'flippability_model_cache_size'):
        if not isinstance(settings[key], int) or settings[key] < 0:
            raise ValueError(f'{key} must be a nonnegative integer')
    if not isinstance(settings['localizer_archive_candidates'], int) or not 0 <= settings['localizer_archive_candidates'] <= 10:
        raise ValueError('localizer_archive_candidates must be an integer in0..10')
    for key in ('solver_timeout', 'scranfilize_timeout', 'interrupt_grace_seconds', 'shutdown_grace_seconds', 'feedback_seconds'):
        if not isinstance(settings[key], (int, float)) or not math.isfinite(settings[key]) or settings[key] <= 0:
            raise ValueError(f'{key} must be a finite positive number')
    for value in settings['localizer_attempt_branches'][:max(0, levels-1)]:
        if not isinstance(value, int) or value < 0:
            raise ValueError('Retry branch counts must be nonnegative integers')
    if settings['radial_relabel_check']:
        permitted = {'mixed23': 23, 'holes29': 29, 'gons32': 32}
        if permitted.get(settings['problem_family']) != settings['n']:
            raise ValueError('radial_relabel_check requires an explicit unlabeled problem_family: mixed23, holes29, or gons32; not valid for caps or label-sensitive inputs')
        if settings['orientation_map_file']:
            raise ValueError('Radial relabeling is not supported with compressed/signed orientation maps')
    if settings['feedback_radial_scaffold'] and not settings['radial_relabel_check']:
        raise ValueError('feedback_radial_scaffold requires radial_relabel_check')
    if settings['feedback_core_choice'] not in ('hash', 'target_hash', 'margin', 'target_margin'):
        raise ValueError('Unknown feedback_core_choice')
    return settings


def retry_seed(seed, original_id, path):
    """Stable across worker completion order."""
    digest = hashlib.sha256(f"{seed}:{original_id}:{path}".encode()).digest()
    return int.from_bytes(digest[:4], "little") & 0x7fffffff


def run_pipeline(settings):
    settings = normalize_settings(settings)
    folder = Path(settings["output_folder"])
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / "raw_results.jsonl"
    if raw.exists():
        raise FileExistsError(f"Refusing to overwrite {raw}; choose a fresh --out directory")
    scratch, realized_dir = folder / "scratch", folder / "realizations"
    scratch.mkdir(exist_ok=True)
    realized_dir.mkdir(exist_ok=True)
    (folder / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    formula = Path(settings["base_file"]).read_text()
    adapter = OrientationMap(settings['orientation_map_file'], settings['n']) if settings['orientation_map_file'] else None
    def orientation_text(literals):
        return adapter.orientations(literals) if adapter else get_orientations(literals, settings['n'])
    provenance = {'python': sys.version, 'cnf_sha256': hashlib.sha256(formula.encode()).hexdigest(),
                  'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'executables': {}}
    if adapter:
        provenance['orientation_map_sha256'] = hashlib.sha256(Path(settings['orientation_map_file']).read_bytes()).hexdigest()
        provenance['primary_variables'] = len(adapter.variables)
    for key in ('localizer_loc', 'cadical_loc', 'scranfilize_loc'):
        if key in settings:
            path = Path(executable(settings[key]))
            if path.is_file():
                provenance['executables'][key] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (folder/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    if settings["solution_generation"] == "scranfilize":
        jobs = [{"type": "SAT", "id": i+1, "original_id": i+1,
                 "scranfilize_seed": settings["sat_seed_start"]+i} for i in range(settings["n_solutions"])]
    else:
        cases = [line.split() for line in Path(settings["cubes_file"]).read_text().splitlines() if line.strip() and not line.lstrip().startswith("c")]
        jobs = [{"type": "SAT", "id": i+1, "original_id": i+1,
                 "assumptions": [int(x) for x in case if x not in ("a", "v", "0")]} for i, case in enumerate(cases)]
    ready, next_id, records = deque(jobs), len(jobs)+1, []
    start, first_realized = time.perf_counter(), None
    executor = ProcessPoolExecutor(max_workers=settings["workers"], initializer=_init_worker, initargs=(formula, settings))
    pending = {}
    interrupted = False

    def make_realize(parent, attempt, branch):
        nonlocal next_id
        path = parent.get("retry_path", "") + f".{branch}"
        job = {"id": next_id, "original_id": parent["original_id"], "type": "Realize", "attempt": attempt,
               "meta": ["initial_try", "second_try", "third_try", "fourth_try"][attempt-1] if attempt <= 4 else f"try_{attempt}",
               "retry_path": path, "timeout": settings["localizer_attempt_timeouts"][attempt-1],
               "orientations_file": parent.get('orientations_file', str(scratch / f"{parent['original_id']}.or")),
               "realization_file": str(scratch / f"{parent['original_id']}_{next_id}.real"),
               "seed": settings["seed"] if attempt == 1 else retry_seed(settings["seed"], parent["original_id"], path),
               "feedback_round": parent.get('feedback_round', 0)}
        next_id += 1
        if settings["warm_start_retries"] and parent.get("best_realization_file"):
            job["warm_start_file"] = parent["best_realization_file"]
        if parent['type'] == 'SAT' and settings['initial_warm_start_file']:
            job['warm_start_file'] = settings['initial_warm_start_file']
        for key in ("best_realization_file", "best_violations"):
            if key in parent:
                job[key] = parent[key]
        return job

    try:
        with raw.open("x") as log:
            while ready or pending:
                while ready and len(pending) < settings["workers"]:
                    job = ready.popleft()
                    pending[executor.submit(_process_job, job)] = job
                done, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                for future in done:
                    original = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = dict(original, status="ERROR", error=f"Worker failed: {exc}", realized=False, satisfiable=False)
                    result["completed_after_seconds"] = time.perf_counter()-start
                    if result["type"] == "Realize" and result.get("general_position"):
                        if result.get("best_violations") is None or result["violations"] < result["best_violations"]:
                            result.update(best_violations=result["violations"], best_realization_file=result["realization_file"])
                    records.append(result)
                    print(json.dumps(result), file=log, flush=True)
                    print(f"job {result['id']} {result['type']}: {result['status']} ({result.get('time_taken', 0):.3f}s)", flush=True)
                    if result["type"] == "SAT" and result.get("satisfiable") and settings["localizer_attempt_levels"] and not (settings['stop_on_solution'] and first_realized is not None):
                        literals = [int(x) for x in result["solution"].split()[1:] if x != "0"]
                        (scratch / f"{result['original_id']}.or").write_text(orientation_text(literals))
                        ready.appendleft(make_realize(result, 1, 0))
                    elif result["type"] == "Realize":
                        if result.get("realized"):
                            if first_realized is None:
                                first_realized = time.perf_counter()-start
                            _save_realization(result, realized_dir)
                            if settings["stop_on_solution"]:
                                ready.clear()
                        attempt = result["attempt"]
                        allowed = not result.get("realized") or settings["continue_if_realized"]
                        if settings["stop_on_solution"] and first_realized is not None:
                            allowed = False
                        if allowed and attempt < settings["localizer_attempt_levels"] and result.get("violations", math.inf) <= settings["localizer_attempt_thresholds"][attempt-1]:
                            for branch in reversed(range(settings["localizer_attempt_branches"][attempt-1])):
                                ready.appendleft(make_realize(result, attempt+1, branch))
                        elif allowed and result.get('actual_model') and not result.get('geometric_rejection') and result.get('feedback_round', 0) < settings['feedback_rounds']:
                            ready.appendleft({'id': next_id, 'type': 'Feedback', 'original_id': result['original_id'],
                                              'actual_model': result.get('feedback_actual_model', result['actual_model']), 'feedback_round': result.get('feedback_round', 0)+1,
                                              'preferred_variables': result.get('feedback_preferred_variables', []),
                                              'warm_start_file': result.get('feedback_warm_start_file', result['realization_file']),
                                              'seed': retry_seed(settings['seed'], result['original_id'], f"feedback{result.get('feedback_round', 0)+1}")})
                            next_id += 1
                    elif result['type'] == 'Feedback' and result.get('solution') and not (settings['stop_on_solution'] and first_realized is not None):
                        orientation_file = scratch / f"{result['original_id']}_feedback_{result['id']}.or"
                        literals = [int(x) for x in result['solution'].split()[1:] if x != '0']
                        orientation_file.write_text(orientation_text(literals))
                        parent = dict(result, orientations_file=str(orientation_file))
                        job = make_realize(parent, 1, 0)
                        job['warm_start_file'] = result['warm_start_file']
                        ready.appendleft(job)
    except BaseException:
        interrupted = True
        # Do not submit queued jobs. Ask current external stages to save first;
        # only hard-stop workers after a bounded flush/validation interval.
        ready.clear()
        processes = list((executor._processes or {}).values())
        for future in pending:
            future.cancel()
        for process in processes:
            if process.is_alive():
                os.kill(process.pid, signal.SIGUSR1)
        deadline = time.perf_counter()+settings['shutdown_grace_seconds']
        with raw.open('a') as log:
            while pending and time.perf_counter() < deadline:
                done, _ = wait(pending, timeout=min(.2, max(0, deadline-time.perf_counter())), return_when=FIRST_COMPLETED)
                for future in done:
                    original = pending.pop(future)
                    if future.cancelled():
                        continue
                    try:
                        result = dict(future.result(), interrupted=True, completed_after_seconds=time.perf_counter()-start)
                        records.append(result)
                        print(json.dumps(result), file=log, flush=True)
                        _save_realization(result, realized_dir)
                    except Exception as exc:
                        print(json.dumps(dict(original, status='INTERRUPTED', error=str(exc))), file=log, flush=True)
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        stage_totals = {}
        for record in records:
            for stage, elapsed in record.get("stage_seconds", {}).items():
                stage_totals[stage] = stage_totals.get(stage, 0)+elapsed
        summary = {"wall_seconds": time.perf_counter()-start, "jobs": len(records),
                   "sat_models": sum(r.get("satisfiable", False) for r in records if r["type"] == "SAT"),
                   "realization_attempts": sum(r["type"] == "Realize" for r in records),
                   "feedback_attempts": sum(r['type'] == 'Feedback' for r in records),
                   "realized": sum(r.get("realized", False) for r in records),
                   "distinct_realized_samples": len({r['original_id'] for r in records if r.get('realized')}),
                   "errors": sum(r.get("status") == "ERROR" for r in records),
                   "first_realized_seconds": first_realized, "stage_worker_seconds": stage_totals,
                   "interrupted": interrupted}
        (folder / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("settings_file")
    parser.add_argument("--base", dest="base_file")
    parser.add_argument("--cubes", dest="cubes_file")
    parser.add_argument("--out", dest="output_folder")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--worker_max_threads", type=int)
    parser.add_argument("-n", type=int, help="Number of points in the CNF orientation encoding")
    args = vars(parser.parse_args(argv))
    settings = json.loads(Path(args.pop("settings_file")).read_text())
    settings.update({key: value for key, value in args.items() if value is not None})
    summary = run_pipeline(settings)
    print(json.dumps(summary, indent=2))
    return 1 if summary["errors"] else 0
