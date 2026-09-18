"""Focused regressions for orchestration bugs and process lifetime handling."""
import concurrent.futures
import json
from pathlib import Path
import signal
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pysat.solvers import Cadical195

from improvements.pipeline import runner as p


class InlineExecutor:
    def __init__(self, **kwargs):
        self._processes = {}
    def submit(self, function, job):
        future = concurrent.futures.Future()
        future.set_result(function(job))
        return future
    def shutdown(self, **kwargs):
        pass


class PipelineTests(unittest.TestCase):
    def test_comments_and_sat_status(self):
        self.assertEqual(p.process_sat_str('c stats 99\ns SATISFIABLE\nv -1 2 0\nc done\n', 3), 'v -1 0')
        for text in ('', None, 's UNKNOWN\nv 1 0', 's UNSATISFIABLE', 'c unsat in comment'):
            self.assertEqual(p.process_sat_str(text, 3), '')

    def test_reject_incomplete_contradictory_models(self):
        for text in ('s SATISFIABLE\nv 0', 's SATISFIABLE\nv 1 -1 0', 's UNSATISFIABLE\ns SATISFIABLE\nv 1', 's UNKNOWN\ns SATISFIABLE\nv 1'):
            with self.assertRaises(ValueError):
                p.process_sat_str(text, 3)

    def test_external_nonzero_error(self):
        result = p.run_process('', [sys.executable, '-c', 'raise SystemExit(1)'], 2)
        self.assertEqual(result['returncode'], 1)
        self.assertFalse(result['timed_out'])

    def test_timeout_drains_handler_output(self):
        code = 'import signal,time,sys; signal.signal(signal.SIGINT,lambda s,f:(print("saved",flush=True),sys.exit(0))); print("ready",flush=True); time.sleep(20)'
        result = p.run_process('', [sys.executable, '-c', code], .2, True, .3)
        self.assertTrue(result['timed_out'])
        self.assertIn('saved', result['stdout'])
        self.assertLess(result['elapsed'], 2)

    def test_ignored_interrupt_is_killed(self):
        code = 'import signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); time.sleep(20)'
        result = p.run_process('', [sys.executable, '-c', code], .2, True, .2)
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['returncode'], -signal.SIGKILL)
        self.assertLess(result['elapsed'], 2)

    def test_realize_does_not_scramble_or_reparse_sat(self):
        settings = p.normalize_settings({'n': 3, 'scranfilize_loc': 'MUST_NOT_RUN'})
        solver = type('Solver', (), {'solve': lambda self, assumptions: assumptions == [1]})()
        checker = type('Checker', (), {'solver': solver})()
        p._state = {'settings': settings, 'checker': checker, 'formula': 'p cnf 1 1\n1 0\n'}
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp)/'points.real'
            real.write_text('0 0 0\n1 1 0\n2 0 1\n')
            stage = {'elapsed': .1, 'returncode': 0, 'timed_out': False, 'error': None, 'stderr': ''}
            inspected = {'bad_vars': [], 'valid': True, 'general_position': True, 'point_count': 3, 'sat_model': [1]}
            with patch.object(p, 'run_process', return_value=stage) as run, patch.object(p, 'inspect_realization', return_value=inspected):
                result = p._process_job({'id': 1, 'type': 'Realize', 'orientations_file': 'a.or', 'realization_file': str(real), 'seed': 1, 'timeout': 1})
            self.assertTrue(result['realized'])
            self.assertEqual(run.call_count, 1)
            self.assertNotIn('scranfilize', result['stage_seconds'])

    def test_retry_warm_start_and_error_does_not_hang(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)/'tiny.cnf'
            base.write_text('p cnf 1 1\n1 0\n')
            seen = []
            def fake(job):
                seen.append(dict(job))
                if job['type'] == 'SAT':
                    return dict(job, satisfiable=True, solution='v 1 0', status='SATISFIABLE')
                Path(job['realization_file']).write_text('0 0 0\n1 1 0\n2 0 1\n')
                return dict(job, realized=False, status='PARTIAL', violations=1, general_position=True)
            settings = {'base_file': str(base), 'output_folder': str(Path(tmp)/'out'), 'n': 3,
                        'workers': 1, 'n_solutions': 2, 'localizer_attempt_levels': 2,
                        'localizer_attempt_timeouts': [.1, .1], 'localizer_attempt_thresholds': [2],
                        'localizer_attempt_branches': [1], 'warm_start_retries': True}
            with patch.object(p, 'ProcessPoolExecutor', InlineExecutor), patch.object(p, '_process_job', side_effect=fake):
                result = p.run_pipeline(settings)
            self.assertEqual(result['realization_attempts'], 4)
            self.assertEqual([x['type'] for x in seen[:4]], ['SAT','Realize','Realize','SAT'])
            self.assertEqual(seen[2]['warm_start_file'], seen[1]['realization_file'])
            self.assertEqual(seen[2]['seed'], p.retry_seed(1, 1, '.0.0'))
            with self.assertRaises(FileExistsError):
                p.run_pipeline(settings)

    def test_settings_reject_bad_retries(self):
        with self.assertRaises(ValueError):
            p.normalize_settings({'localizer_attempt_levels': 3, 'localizer_attempt_timeouts': [1]})
        with self.assertRaises(ValueError):
            p.normalize_settings({'localizer_extra_args': '-c file'})
        with self.assertRaises(ValueError):
            p.normalize_settings({'solver_timeout': None})
        with self.assertRaises(ValueError):
            p.normalize_settings({'n': 26, 'problem_family': 'caps26', 'radial_relabel_check': True})
        self.assertTrue(p.normalize_settings({'n': 32, 'problem_family': 'gons32', 'radial_relabel_check': True})['radial_relabel_check'])

    def test_cli_n_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp)/'settings.json'
            settings_file.write_text('{"n": 23}')
            with patch.object(p, 'run_pipeline', return_value={'errors': 0}) as run:
                self.assertEqual(p.main([str(settings_file), '-n', '32']), 0)
            self.assertEqual(run.call_args.args[0]['n'], 32)

    def test_missing_localizer_coordinates_recorded_as_error(self):
        p._state = {'settings': p.normalize_settings({}), 'checker': None, 'formula': ''}
        stage = {'elapsed': .1, 'returncode': 1, 'timed_out': False, 'error': None, 'stderr': 'bad input'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'run_process', return_value=stage):
            result = p._process_job({'id': 1, 'type': 'Realize', 'orientations_file': 'missing.or',
                                     'realization_file': str(Path(tmp)/'missing.real'), 'seed': 1, 'timeout': 1})
        self.assertEqual(result['status'], 'ERROR')
        self.assertFalse(result['realized'])

    def test_cnf_sat_caps_are_rejected_for_primary_and_archive(self):
        solver = type('Solver', (), {'solve': lambda self, assumptions: True})()
        checker = type('Checker', (), {'solver': solver})()
        settings = p.normalize_settings({'n': 26, 'base_file': '7gon-no-5-cap-no-sb-26.cnf',
                                         'localizer_archive_candidates': 1})
        p._state = {'settings': settings, 'checker': checker, 'formula': ''}
        inspected = {'bad_vars': [], 'valid': True, 'general_position': True, 'point_count': 26, 'sat_model': [1]}
        stage = {'elapsed': .1, 'returncode': 0, 'timed_out': False, 'error': None, 'stderr': ''}
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp)/'main.real'
            real.write_text('1 0 0\n')
            Path(str(real)+'.archive-00.real').write_text('1 1 1\n')
            with patch.object(p, 'run_process', return_value=stage), patch.object(p, 'inspect_realization', return_value=inspected), patch.object(p, 'count_caps', return_value=27) as caps:
                result = p._process_job({'id': 1, 'type': 'Realize', 'orientations_file': 'a.or',
                                         'realization_file': str(real), 'seed': 1, 'timeout': 1})
            self.assertTrue(result['full_cnf_satisfiable'])
            self.assertFalse(result['realized'])
            self.assertEqual(result['status'], 'GEOMETRIC_REJECTION')
            self.assertEqual(result['convex_5_caps'], 27)
            self.assertEqual(result['archive_audits'][0]['convex_5_caps'], 27)
            self.assertEqual(caps.call_count, 2)

    def test_cnf_sat_cap_free_coordinates_are_accepted(self):
        solver = type('Solver', (), {'solve': lambda self, assumptions: True})()
        p._state = {'settings': p.normalize_settings({'n': 26, 'problem_family': 'caps26'}),
                    'checker': type('Checker', (), {'solver': solver})(), 'formula': ''}
        stage = {'elapsed': .1, 'returncode': 0, 'timed_out': False, 'error': None, 'stderr': ''}
        inspected = {'bad_vars': [], 'valid': True, 'general_position': True, 'point_count': 26, 'sat_model': [1]}
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp)/'main.real'
            real.write_text('1 0 0\n')
            with patch.object(p, 'run_process', return_value=stage), patch.object(p, 'inspect_realization', return_value=inspected), patch.object(p, 'count_caps', return_value=0):
                result = p._process_job({'id': 1, 'type': 'Realize', 'orientations_file': 'a.or',
                                         'realization_file': str(real), 'seed': 1, 'timeout': 1})
            self.assertTrue(result['realized'])
            self.assertEqual(result['convex_5_caps'], 0)

    def test_worker_stop_saves_native_incumbent(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready, saved = Path(tmp)/'ready', Path(tmp)/'saved'
            native = 'import pathlib,signal,sys,time; signal.signal(signal.SIGINT,lambda s,f:(pathlib.Path(sys.argv[2]).write_text("incumbent"),sys.exit(0))); pathlib.Path(sys.argv[1]).write_text("ready"); time.sleep(30)'
            worker = ('import json,signal,sys; from improvements.pipeline import runner as p; '
                      'signal.signal(signal.SIGUSR1,p._request_worker_stop); '
                      'print(json.dumps(p.run_process("",[sys.executable,"-c",sys.argv[1],sys.argv[2],sys.argv[3]],30,True)),flush=True)')
            process = subprocess.Popen([sys.executable, '-c', worker, native, str(ready), str(saved)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic()+3
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists())
                os.kill(process.pid, signal.SIGUSR1)
                out, err = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, err)
                self.assertEqual(saved.read_text(), 'incumbent')
                self.assertEqual(json.loads(out)['returncode'], 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_coordinator_interrupt_flushes_native_and_cancels_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            base, config = directory/'tiny.cnf', directory/'config.json'
            ready, saved = directory/'ready', directory/'saved'
            base.write_text('p cnf 1 1\n1 0\n')
            settings = {'base_file':str(base),'n':3,'workers':1,'n_solutions':2,
                        'output_folder':str(directory/'out'),'ready_file':str(ready),
                        'saved_file':str(saved),'localizer_attempt_levels':0,'shutdown_grace_seconds':2}
            config.write_text(json.dumps(settings))
            process = subprocess.Popen([sys.executable,'-m','improvements.pipeline.interrupt_fixture',str(config)],
                                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline = time.monotonic()+4
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists())
                os.kill(process.pid,signal.SIGINT)
                out, err = process.communicate(timeout=4)
                self.assertEqual(process.returncode,130,err)
                self.assertEqual(saved.read_text(),'saved incumbent')
                summary = json.loads((directory/'out/summary.json').read_text())
                self.assertTrue(summary['interrupted'])
                self.assertEqual(summary['jobs'],1)
                records = list(map(json.loads,(directory/'out/raw_results.jsonl').read_text().splitlines()))
                self.assertEqual(len(records),1)
                self.assertTrue(records[0]['interrupted'])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_core_feedback_retains_cnf_and_changes_only_relaxed_assumptions(self):
        with Cadical195(bootstrap_with=[[1, 2], [-2, 3]]) as solver:
            actual = [-1, -2, -3]
            repaired, stats = p.core_guided_feedback(solver, actual, p.normalize_settings({}), 42)
            self.assertIsNotNone(repaired)
            self.assertTrue(solver.solve(assumptions=repaired))
            self.assertFalse(solver.solve(assumptions=actual))
            relaxed = {abs(x) for x in stats['relaxed']}
            self.assertTrue(all(a == b or abs(a) in relaxed for a, b in zip(actual, repaired)))

    def test_core_feedback_reports_budget_not_unsat(self):
        with Cadical195(bootstrap_with=[[1]]) as solver:
            model, stats = p.core_guided_feedback(solver, [-1], p.normalize_settings({'feedback_max_relaxed': 0}), 1)
            self.assertIsNone(model)
            self.assertEqual(stats['status'], 'BUDGET_EXHAUSTED')

    def test_core_feedback_target_and_margin_priorities(self):
        for strategy, expected in [('target_hash', 2), ('target_margin', 2), ('margin', 1)]:
            with Cadical195(bootstrap_with=[[1, 2]]) as solver:
                settings = p.normalize_settings({'feedback_core_choice': strategy})
                model, stats = p.core_guided_feedback(solver, [-1,-2], settings, 1, [2], {1:.1,2:.9})
                self.assertEqual(stats['relaxed'], [-expected])
                self.assertTrue(solver.solve(assumptions=model))

    def test_margin_ranking_scale_translation_invariant(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp)/'first.real', Path(tmp)/'second.real'
            first.write_text('1 0 0\n2 1 0\n3 0 .01\n')
            second.write_text('1 100 -30\n2 110 -30\n3 100 -29.9\n')
            self.assertAlmostEqual(p.orientation_margins(first,3)[1], p.orientation_margins(second,3)[1])

    def test_flippability_memoization_returns_independent_results(self):
        class Checker:
            calls = 0
            last_stats = {}
            def check(self, model):
                self.calls += 1
                self.last_stats = {'flip_sat_calls': 3}
                return {2}, [1,-3]
        checker = Checker()
        p._state = {'settings': p.normalize_settings({})}
        flips, required = p._check_flippability(checker, 'v 1 2 -3 0')
        flips.add(9)
        required.append(7)
        self.assertEqual(p._check_flippability(checker, 'v 1 2 -3 0'), ({2}, [1,-3]))
        self.assertEqual(checker.calls, 1)
        self.assertTrue(checker.last_stats['cache_hit'])


if __name__ == '__main__':
    unittest.main()
