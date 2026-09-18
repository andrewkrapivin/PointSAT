"""Whole-workflow timing regressions; fake processes/clocks, no search runs."""
import json
import io
import itertools
import math
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock
import zlib

from benchmarks import anytime_compare
from benchmarks import anytime_geometry
from benchmarks import anytime_worker


ROOT = Path(__file__).resolve().parents[1]


class FakeClock:
    """Mutable monotonic clock, so a 120-second trajectory can test instantly."""
    def __init__(self, initial=1000.0):
        self.now = initial

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
        return self.now


class AcceptanceDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-anytime-timing-')
        self.folder = Path(self.temp.name)
        self.clock = FakeClock()
        self.verifier = self.folder/'fake-verifier'
        self.verifier.write_text('Never executed: subprocess is replaced in these timing tests.\n')

    def tearDown(self):
        self.temp.cleanup()

    def audit(self, verifier_delay=0, commit_delay=0):
        geometry = {'n': 23, 'gon': 7, 'hole': 6, 'valid': True, 'collinear_triples': 0,
                    'convex_gons': 0, 'empty_holes': 0, 'gon_subsets_checked': math.comb(23, 7),
                    'hole_subsets_checked': math.comb(23, 6)}
        clock = self.clock

        class FakeVerifier:
            returncode = 0

            def communicate(self, timeout=None):
                clock.advance(verifier_delay)
                return json.dumps(geometry).encode(), b''

            def poll(self):
                return self.returncode

        original_replace = Path.replace

        def delayed_commit(path, target):
            result = original_replace(path, target)
            if Path(target).name == 'certificate.json':
                clock.advance(commit_delay)
            return result

        config = {'output_directory': self.folder/'audit', 'verifier_path': self.verifier,
                  'deadline_monotonic': 1010.0}
        with mock.patch.object(anytime_geometry.time, 'monotonic', side_effect=clock.monotonic), \
                mock.patch.object(anytime_geometry.subprocess, 'Popen', return_value=FakeVerifier()), \
                mock.patch.object(Path, 'replace', delayed_commit):
            return anytime_geometry.audit(ROOT/'direct/seeds/paper23.pts', 'mixed23', config)

    def test_valid_certificate_completed_after_deadline_is_not_accepted(self):
        result = self.audit(commit_delay=10.001)
        self.assertTrue(result['valid_geometry'])
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['accepted_timestamp_monotonic'])
        self.assertEqual(result['status'], 'DEADLINE_EXCEEDED')
        self.assertTrue((self.folder/'audit/certificate.json').exists())

    def test_verifier_finishing_after_deadline_cannot_be_retroactively_accepted(self):
        result = self.audit(verifier_delay=10.001)
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['accepted_timestamp_monotonic'])
        self.assertEqual(result['status'], 'DEADLINE_EXCEEDED')

    def test_acceptance_timestamp_includes_verifier_and_certificate_commit(self):
        result = self.audit(verifier_delay=2.0, commit_delay=3.0)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['accepted_timestamp_monotonic'], 1005.0)
        self.assertEqual(result['check_wall_seconds'], 5.0)
        certificate = json.loads((self.folder/'audit/certificate.json').read_text())
        self.assertNotIn('accepted_timestamp_monotonic', certificate)


class WorkerTrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-anytime-worker-test-')
        self.folder = Path(self.temp.name)
        self.serial = 0

    def tearDown(self):
        self.temp.cleanup()

    def run_trajectory(self, arm='v6_plain', startup=0, preparation=20,
                       native_durations=(7,), audit_duration=5, feedback_duration=7,
                       force_late_acceptance=False):
        self.serial += 1
        folder = self.folder/str(self.serial)
        folder.mkdir()
        work = folder/'work'
        work.mkdir()
        cnf = folder/'tiny.cnf'
        cnf.write_text('p cnf 1 1\n1 0\n')
        clock = FakeClock(1000+startup)
        full = 'A_(1, 2, 3)\n'
        case = {'id': 'case0', 'family': 'mixed23', 'n': 23, 'seed': 17,
                'primary_model': [1], 'initial_full_sha256': anytime_worker.hashlib.sha256(full.encode()).hexdigest(),
                'cnf': str(cnf)}
        config = {'cases': [case], 'arms_for_family': {'mixed23': [arm]},
                  'horizon_seconds': 120, 'native_slice_seconds': 15,
                  'verification_reserve_seconds': 3, 'save_grace_seconds': .1,
                  'feedback_seconds': 10, 'paths': {'original': 'original', 'v4': 'v4', 'v6': 'v6',
                  'mapping': 'unused', 'verifier_paper': 'fake_verifier'},
                  'frozen_sha256': {'fake_verifier': 'unused'}}
        registration = folder/'registration.json'
        registration.write_text(json.dumps(config))
        modules = {name: ModuleType(name) for name in
                   ('flippable2', 'legacy_flippable', 'sat_orient_conversion', 'orientation_map', 'anytime_geometry', 'feedback')}
        calls = {'native': [], 'audit': [], 'checker_instances': [], 'feedback': [], 'legacy': []}

        class FakeChecker:
            def __init__(self, formula):
                self.solver = object()
                self.last_stats = {'fake': True}
                self.check_count = 0
                self.closed = False
                calls['checker_instances'].append(self)

            def check(self, model):
                self.check_count += 1
                clock.advance(preparation if self.check_count == 1 else 2)
                return [], [int(model.split()[1])]

            def close(self):
                self.closed = True

        modules['flippable2'].FlippabilityChecker = FakeChecker
        def legacy_check(formula, model):
            calls['legacy'].append({'formula': formula, 'model': model})
            clock.advance(preparation)
            return [], [int(model.split()[1])]
        modules['legacy_flippable'].check_flippable = legacy_check
        modules['orientation_map'].OrientationMap = object
        modules['sat_orient_conversion'].get_orientations = lambda model, n: ('A' if model[0] > 0 else 'B')+'_(1, 2, 3)\n'
        modules['sat_orient_conversion'].inspect_realization = lambda *args: {'sat_model': [1], 'bad_vars': [1]}
        modules['feedback'].orientation_margins = lambda *args: {1: .01}

        def feedback(solver, actual, settings, seed, preferred, margins):
            calls['feedback'].append({'solver': solver, 'settings': settings, 'seed': seed})
            clock.advance(feedback_duration)
            return [-1], {'status': 'SAT'}

        modules['feedback'].core_guided_feedback = feedback

        def native(config, case, actual_arm, target, output, seed, seconds, warm=None):
            index = len(calls['native'])
            calls['native'].append({'arm': actual_arm, 'target': Path(target).read_text(),
                                    'seconds': seconds, 'seed': seed, 'warm': warm,
                                    'start_elapsed': clock.now-1000})
            duration = native_durations[index] if index < len(native_durations) else seconds
            clock.advance(min(seconds, duration))
            output.write_text('opaque coordinate fixture; exact audit replaced for timing tests\n')
            return {'file': output.name, 'output_saved': True, 'seed': seed,
                    'warm_start': warm is not None, 'requested_native_seconds': seconds}

        def audit(output, family, settings):
            index = len(calls['audit'])
            calls['audit'].append({'deadline': settings['deadline_monotonic'], 'start_elapsed': clock.now-1000})
            clock.advance(audit_duration)
            valid = index == len(native_durations)-1
            on_time = clock.now <= settings['deadline_monotonic']
            accepted = valid and (on_time or force_late_acceptance)
            return {'status': 'VALID' if on_time else 'DEADLINE_EXCEEDED', 'valid_geometry': valid,
                    'accepted': accepted, 'accepted_timestamp_monotonic': clock.now if accepted else None}

        modules['anytime_geometry'].audit = audit
        args = SimpleNamespace(registration=str(registration), case='case0', arm=arm,
                               work=str(work), started=1000.0)
        old_path = list(sys.path)
        error = None
        try:
            with mock.patch.dict(sys.modules, modules), \
                    mock.patch.object(anytime_worker.time, 'monotonic', side_effect=clock.monotonic), \
                    mock.patch.object(anytime_worker.time, 'sleep', side_effect=clock.advance), \
                    mock.patch.object(anytime_worker, 'native', side_effect=native):
                try:
                    anytime_worker.worker(args)
                except RuntimeError as caught:
                    error = caught
        finally:
            sys.path[:] = old_path
        report = json.loads((work/'result.json').read_text())
        return report, calls, error

    def test_startup_preparation_native_and_audit_all_charge_same_clock(self):
        report, calls, error = self.run_trajectory(startup=5, preparation=20, native_durations=(7,), audit_duration=5)
        self.assertIsNone(error)
        self.assertEqual(calls['native'][0]['seconds'], 92)  # 120 - startup5 - preparation20 - reserve3.
        self.assertEqual(calls['native'][0]['start_elapsed'], 25)
        self.assertEqual(calls['audit'][0]['deadline'], 1120)
        self.assertEqual(report['first_verified_seconds'], 37)
        self.assertEqual(report['status'], 'SOLVED')
        self.assertTrue(calls['checker_instances'][0].closed)

    def test_preparation_exhausting_deadline_never_launches_native(self):
        report, calls, error = self.run_trajectory(startup=5, preparation=120)
        self.assertIsNone(error)
        self.assertEqual(calls['native'], [])
        self.assertEqual(calls['audit'], [])
        self.assertIsNone(report['first_verified_seconds'])
        self.assertEqual(report['status'], 'TIME_LIMIT')

    def test_original_uses_legacy_preparation_under_the_same_clock(self):
        original, before, error = self.run_trajectory(arm='original', startup=5, preparation=20)
        revised, after, revised_error = self.run_trajectory(arm='v6_plain', startup=5, preparation=20)
        self.assertIsNone(error)
        self.assertIsNone(revised_error)
        self.assertEqual(len(before['legacy']), 1)
        self.assertEqual(before['checker_instances'], [])
        self.assertEqual(after['legacy'], [])
        self.assertEqual(before['native'][0]['seconds'], 92)
        self.assertEqual(before['native'][0]['target'], after['native'][0]['target'])
        self.assertEqual(original['first_verified_seconds'], revised['first_verified_seconds'])
        self.assertEqual(original['initial_flippability_stats']['implementation'], 'legacy_git_snapshot')

    def test_retry_and_feedback_share_first_slice_seed_target_and_warm_policy(self):
        retry, retry_calls, retry_error = self.run_trajectory(arm='v6_retry', preparation=5,
                                                             native_durations=(15, 15), audit_duration=2)
        adaptive, adaptive_calls, adaptive_error = self.run_trajectory(arm='v6_feedback', preparation=5,
                                                                      native_durations=(15, 15), audit_duration=2)
        self.assertIsNone(retry_error)
        self.assertIsNone(adaptive_error)
        for calls in (retry_calls, adaptive_calls):
            self.assertEqual(len(calls['native']), 2)
            self.assertEqual(calls['native'][0]['seconds'], 15)
            self.assertEqual(calls['native'][0]['seed'], 17)
            self.assertEqual(calls['native'][1]['seed'], 1000020)
            self.assertIsNone(calls['native'][0]['warm'])
            self.assertIsNotNone(calls['native'][1]['warm'])
            self.assertEqual(len(calls['checker_instances']), 1)
        self.assertEqual(retry_calls['native'][0]['target'], adaptive_calls['native'][0]['target'])
        self.assertEqual(retry_calls['native'][1]['target'], retry_calls['native'][0]['target'])
        self.assertNotEqual(adaptive_calls['native'][1]['target'], adaptive_calls['native'][0]['target'])
        self.assertEqual(retry_calls['feedback'], [])
        self.assertEqual(len(adaptive_calls['feedback']), 1)
        self.assertIs(adaptive_calls['feedback'][0]['solver'], adaptive_calls['checker_instances'][0].solver)
        self.assertEqual(retry['first_verified_seconds'], 39)
        self.assertEqual(adaptive['first_verified_seconds'], 48)  # Same slices/checks plus 7s feedback + 2s reflippability.

    def test_sat_feedback_exhausting_deadline_prevents_second_native(self):
        report, calls, error = self.run_trajectory(arm='v6_feedback', preparation=1,
                                                  native_durations=(15, 15), audit_duration=1,
                                                  feedback_duration=105)
        self.assertIsNone(error)
        self.assertEqual(len(calls['native']), 1)
        self.assertIsNone(report['first_verified_seconds'])
        self.assertEqual(report['status'], 'TIME_LIMIT')

    def test_worker_defensively_rejects_falsely_credited_late_audit(self):
        report, calls, error = self.run_trajectory(preparation=110, native_durations=(6,),
                                                  audit_duration=5, force_late_acceptance=True)
        self.assertIsInstance(error, RuntimeError)
        self.assertIsNone(report['first_verified_seconds'])
        self.assertEqual(report['status'], 'ERROR')

    def test_credit_time_boundaries_do_not_backdate_milestones(self):
        for elapsed in (0, 30, 60, 120):
            self.assertEqual(anytime_worker.credit_time(1000+elapsed, 1000, 120), elapsed)
        self.assertGreater(anytime_worker.credit_time(1030.001, 1000, 120), 30)
        for timestamp in (999.999, 1120.001, None, float('nan'), float('inf')):
            self.assertIsNone(anytime_worker.credit_time(timestamp, 1000, 120))


class CoordinatorProcessTests(unittest.TestCase):
    """Tiny real Python children exercise signals; no solver executable is used."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-anytime-process-test-')
        self.folder = Path(self.temp.name)
        anytime_compare.STOP.clear()

    def tearDown(self):
        anytime_compare.STOP.clear()
        self.temp.cleanup()

    def fixture(self, body):
        frozen = self.folder/'frozen'
        frozen.mkdir()
        (frozen/'anytime_worker.py').write_text(
            'import json,os,pathlib,signal,subprocess,sys,time\n'
            "work=pathlib.Path(sys.argv[sys.argv.index('--work')+1])\n"+body)
        registration = self.folder/'registration.json'
        registration.write_text('{}\n')
        work = self.folder/'work'
        work.mkdir()
        config = {'python': sys.executable, 'horizon_seconds': .15,
                  'posthoc_seconds': .15, 'save_grace_seconds': .1}
        return config, registration, work

    @staticmethod
    def process_running(pid):
        try:
            stat = Path(f'/proc/{pid}/stat').read_text()
            return stat[stat.rfind(')')+2:].split()[0] not in ('Z', 'X')
        except FileNotFoundError:
            return False

    def test_watchdog_saves_sigint_checkpoint_with_parent_clock(self):
        config, registration, work = self.fixture(
            'def save(*args):\n'
            " (work/'result.json').write_text(json.dumps({'status':'TIME_LIMIT','started':float(sys.argv[sys.argv.index('--started')+1])}))\n"
            ' raise SystemExit(0)\n'
            'signal.signal(signal.SIGINT,save)\n'
            'time.sleep(30)\n')
        result = anytime_compare.isolated(config, registration, {'id': 'mixed23-0'}, 'original', work)
        self.assertEqual(result['returncode'], 0)
        self.assertTrue(result['deadline_censored'])
        self.assertFalse(result['forced_kill'])
        self.assertFalse(result['external_stop'])
        self.assertEqual(result['worker_record']['started'], result['started_monotonic'])
        self.assertAlmostEqual(result['deadline_monotonic']-result['started_monotonic'], .15)
        self.assertLess(result['parent_wall_seconds'], 2)

    def test_ignored_interrupt_is_killed_and_no_checkpoint_is_explicit(self):
        config, registration, work = self.fixture('signal.signal(signal.SIGINT,signal.SIG_IGN)\ntime.sleep(30)\n')
        result = anytime_compare.isolated(config, registration, {'id': 'mixed23-0'}, 'original', work)
        self.assertEqual(result['returncode'], -signal.SIGKILL)
        self.assertTrue(result['forced_kill'])
        self.assertTrue(result['deadline_censored'])
        self.assertEqual(result['worker_record']['status'], 'NO_CHECKPOINT')
        self.assertLess(result['parent_wall_seconds'], 2)

    def test_worker_exit_still_kills_its_owned_descendant(self):
        config, registration, work = self.fixture(
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
            "(work/'descendant.pid').write_text(str(p.pid))\n"
            "(work/'result.json').write_text(json.dumps({'status':'FINISHED'}))\n")
        config['horizon_seconds'] = 2
        result = anytime_compare.isolated(config, registration, {'id': 'mixed23-0'}, 'original', work)
        pid = int((work/'descendant.pid').read_text())
        try:
            deadline = time.monotonic()+1
            while self.process_running(pid) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse(self.process_running(pid))
            self.assertFalse(result['deadline_censored'])
            self.assertEqual(result['returncode'], 0)
        finally:
            if self.process_running(pid):
                os.kill(pid, signal.SIGKILL)

    def test_stop_file_is_not_mislabeled_as_budget_expiration(self):
        config, registration, work = self.fixture('time.sleep(30)\n')
        config['horizon_seconds'] = 10
        (registration.parent/'STOP').write_text('test external stop\n')
        result = anytime_compare.isolated(config, registration, {'id': 'mixed23-0'}, 'original', work)
        self.assertTrue(result['external_stop'])
        self.assertFalse(result['deadline_censored'])
        self.assertLess(result['parent_wall_seconds'], 2)

    def test_posthoc_has_its_own_bound_and_no_online_start_argument(self):
        config, registration, work = self.fixture(
            "assert sys.argv[1]=='posthoc'\n"
            "assert '--started' not in sys.argv and '--arm' not in sys.argv\n"
            "(work/'posthoc-result.json').write_text(json.dumps({'status':'AUDITED','audits':[]}))\n")
        config['horizon_seconds'] = 120
        result = anytime_compare.isolated(config, registration, {'id': 'mixed23-0'}, 'original', work, phase='posthoc')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['worker_record']['status'], 'AUDITED')
        self.assertAlmostEqual(result['deadline_monotonic']-result['started_monotonic'], .15)


class CoordinatorIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-anytime-integrity-test-')
        self.folder = Path(self.temp.name)
        anytime_compare.STOP.clear()

    def tearDown(self):
        anytime_compare.STOP.clear()
        self.temp.cleanup()

    def fixture(self):
        cnf = self.folder/'tiny.cnf'
        cnf.write_text('p cnf 1 1\n1 0\n')
        full = b'A_(1, 2, 3)\n'
        config = {'frozen_sha256': {}, 'horizon_seconds': 120, 'milestones': [30, 60, 120],
                  'family_arms': {'mixed23': ['original', 'v6_plain']},
                  'cases': [{'id': 'mixed23-0', 'family': 'mixed23', 'seed': 17, 'n': 23,
                             'initial_full_sha256': anytime_compare.hashlib.sha256(full).hexdigest(),
                             'cnf': str(cnf), 'cnf_sha256': anytime_compare.sha(cnf),
                             'condition_order': ['original', 'v6_plain']}],
                  'report_output': str(self.folder/'report'), 'report_python': sys.executable}
        registration = self.folder/'registration.json'
        registration.write_text(json.dumps(config))
        return registration, config, full

    def invoke(self, registration, isolated):
        args = SimpleNamespace(registration=str(registration), workers=2)
        with mock.patch.object(anytime_compare, 'isolated', side_effect=isolated), \
                mock.patch.object(anytime_compare.os, 'sched_getaffinity', return_value={4, 5, 6, 7}), \
                mock.patch.object(anytime_compare.os, 'sched_setaffinity') as affinity, \
                mock.patch.object(anytime_compare.signal, 'signal'), \
                mock.patch.object(anytime_compare, 'bounded_report', return_value={
                    'returncode': 0, 'deadline_censored': False, 'external_stop': False}) as reporter, \
                mock.patch('sys.stdout', new_callable=io.StringIO):
            anytime_compare.run(args)
        affinity.assert_called_once_with(0, [4, 5])
        return reporter

    def test_first_time_must_match_finite_timely_online_certificates(self):
        self.assertIsNone(anytime_compare.first_verified({'posthoc': [{'valid_geometry': True}]}, 120))
        for value in (0, 30, 60, 120):
            self.assertEqual(anytime_compare.first_verified({'first_verified_seconds': value,
                'certificates': [{'accepted': True, 'accepted_elapsed_seconds': value}]}, 120), value)
        cases = [
            {'first_verified_seconds': 30, 'certificates': []},
            {'first_verified_seconds': None, 'certificates': [{'accepted': True, 'accepted_elapsed_seconds': 30}]},
            {'first_verified_seconds': 30, 'certificates': [{'accepted': True, 'accepted_elapsed_seconds': 31}]},
        ]
        cases += [{'first_verified_seconds': x, 'certificates': [{'accepted': True, 'accepted_elapsed_seconds': x}]}
                  for x in (-1, 120.001, float('nan'), float('inf'), True)]
        for record in cases:
            with self.subTest(record=record), self.assertRaises(ValueError):
                anytime_compare.first_verified(record, 120)

    def test_durable_preinsert_matched_pair_artifacts_and_no_duplicate_resume(self):
        registration, config, full = self.fixture()
        calls = []
        database = self.folder/'results.sqlite'

        def isolated(settings, path, case, arm, work, phase='worker'):
            calls.append((arm, phase))
            with sqlite3.connect(database) as db:
                pending = db.execute('SELECT complete,record FROM trials WHERE case_id=? AND arm=? ORDER BY id DESC LIMIT 1',
                                     (case['id'], arm)).fetchone()
            self.assertEqual(pending[0], 0)
            self.assertEqual(json.loads(pending[1])['work_directory'], str(work))
            (work/'full.or').write_bytes(full)
            (work/'initial.or').write_bytes(full)
            (work/'late-native.real').write_text('explicit late artifact retained, not a primary success\n')
            record = {'status': 'TIME_LIMIT', 'first_verified_seconds': None, 'certificates': [],
                      'initial_target_sha256': anytime_compare.hashlib.sha256(full).hexdigest()}
            if phase == 'posthoc':
                record = {'status': 'AUDITED', 'audits': [{'valid_geometry': True, 'outside_online_deadline': True}]}
            return {'worker_record': record, 'parent_wall_seconds': 120 if phase == 'worker' else .1,
                    'parent_cpu_seconds': .01, 'started_monotonic': 1000, 'deadline_monotonic': 1120,
                    'returncode': 0, 'deadline_censored': phase == 'worker',
                    'forced_kill': False, 'external_stop': False}

        reporter = self.invoke(registration, isolated)
        reporter.assert_called_once()
        self.assertEqual(calls, [('original', 'worker'), ('original', 'posthoc'), ('v6_plain', 'worker'), ('v6_plain', 'posthoc')])
        with sqlite3.connect(database) as db:
            rows = list(db.execute('SELECT id,complete,record FROM trials ORDER BY id'))
            for identifier, complete, encoded in rows:
                report = json.loads(encoded)
                self.assertEqual(complete, 1)
                self.assertEqual(report['seed'], 17)
                self.assertIsNone(report['first_verified_seconds'])
                self.assertEqual(report['posthoc'][0]['valid_geometry'], True)
                artifact = db.execute('SELECT sha256,data FROM artifacts WHERE trial_id=? AND name=?',
                                      (identifier, 'late-native.real')).fetchone()
                self.assertEqual(anytime_compare.hashlib.sha256(zlib.decompress(artifact[1])).hexdigest(), artifact[0])
        summary = anytime_compare.summarize(registration)
        self.assertTrue(summary['complete'])
        self.assertEqual(summary['completed_trials'], 2)
        self.assertTrue(anytime_compare.verify(registration)['integrity_ok'])
        for arm in config['family_arms']['mixed23']:
            self.assertEqual(summary['families']['mixed23']['arms'][arm]['milestones'], {'30': 0, '60': 0, '120': 0})
        self.invoke(registration, isolated)
        self.assertEqual(len(calls), 4)
        with sqlite3.connect(database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trials').fetchone()[0], 2)

    def test_controller_failure_retains_running_attempt_and_work_for_resume(self):
        registration, config, full = self.fixture()

        def failed(settings, path, case, arm, work, phase='worker'):
            (work/'diagnostic.txt').write_text('owned partial evidence\n')
            raise RuntimeError('synthetic controller failure')

        with self.assertRaisesRegex(RuntimeError, 'synthetic controller failure'):
            self.invoke(registration, failed)
        with sqlite3.connect(self.folder/'results.sqlite') as db:
            rows = list(db.execute('SELECT complete,record FROM trials'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 0)
        old = json.loads(rows[0][1])
        self.assertEqual(old['status'], 'RUNNING')
        self.assertTrue((Path(old['work_directory'])/'diagnostic.txt').is_file())
        self.assertFalse(anytime_compare.summarize(registration)['complete'])

        # A new coordinator invocation retries the condition, without overwriting
        # the incomplete attempt or its surviving work-directory evidence.
        anytime_compare.STOP.clear()
        restarted = []

        def resumed(settings, path, case, arm, work, phase='worker'):
            restarted.append((arm, phase, str(work)))
            return {'worker_record': {'status': 'TIME_LIMIT', 'first_verified_seconds': None,
                                     'certificates': [], 'audits': []},
                    'parent_wall_seconds': 120, 'parent_cpu_seconds': .01,
                    'started_monotonic': 1000, 'deadline_monotonic': 1120,
                    'returncode': 0, 'deadline_censored': True, 'forced_kill': False, 'external_stop': False}

        self.invoke(registration, resumed)
        self.assertEqual([(arm, phase) for arm, phase, _ in restarted],
                         [('original', 'worker'), ('original', 'posthoc'), ('v6_plain', 'worker'), ('v6_plain', 'posthoc')])
        self.assertTrue(all(work != old['work_directory'] for _, _, work in restarted))
        with sqlite3.connect(self.folder/'results.sqlite') as db:
            self.assertEqual(list(db.execute('SELECT complete FROM trials ORDER BY id')), [(0,), (1,), (1,)])
        self.assertEqual((Path(old['work_directory'])/'diagnostic.txt').read_text(), 'owned partial evidence\n')
        summary = anytime_compare.summarize(registration)
        self.assertTrue(summary['complete'])
        self.assertEqual(summary['incomplete_attempts'], 1)

    def test_external_stop_retains_incomplete_archived_attempt(self):
        registration, config, full = self.fixture()
        calls = []

        def stopped(settings, path, case, arm, work, phase='worker'):
            calls.append((arm, phase))
            anytime_compare.STOP.set()
            (work/'partial.real').write_text('partial snapshot saved under STOP\n')
            return {'worker_record': {'status': 'INTERRUPTED', 'first_verified_seconds': None, 'certificates': []},
                    'parent_wall_seconds': 2, 'parent_cpu_seconds': .01,
                    'started_monotonic': 1000, 'deadline_monotonic': 1120,
                    'returncode': 0, 'deadline_censored': False, 'forced_kill': False, 'external_stop': True}

        reporter = self.invoke(registration, stopped)
        reporter.assert_not_called()
        self.assertEqual(calls, [('original', 'worker')])
        with sqlite3.connect(self.folder/'results.sqlite') as db:
            complete, encoded = db.execute('SELECT complete,record FROM trials').fetchone()
            self.assertEqual(complete, 0)
            record = json.loads(encoded)
            self.assertTrue(record['external_stop'])
            self.assertEqual(record['posthoc_status'], 'SKIPPED_EXTERNAL_STOP')
            self.assertIsNotNone(db.execute("SELECT 1 FROM artifacts WHERE name='partial.real'").fetchone())
        self.assertFalse(anytime_compare.summarize(registration)['complete'])

    def test_integrity_rejects_mismatched_initial_targets_and_artifact_corruption(self):
        registration, config, full = self.fixture()
        database = self.folder/'results.sqlite'
        with sqlite3.connect(database) as db:
            db.executescript(anytime_compare.SCHEMA)
            for index, arm in enumerate(('original', 'v6_plain')):
                partial = full if index == 0 else b'B_(1, 2, 3)\n'
                digest = anytime_compare.hashlib.sha256(partial).hexdigest()
                record = dict(config['cases'][0], arm=arm, case_id='mixed23-0',
                              initial_target_sha256=digest, certificates=[], first_verified_seconds=None)
                identifier = db.execute('INSERT INTO trials(case_id,arm,complete,record) VALUES(?,?,1,?)',
                                        ('mixed23-0', arm, json.dumps(record))).lastrowid
                db.execute('INSERT INTO artifacts VALUES(?,?,?,?)',
                           (identifier, 'initial.or', digest, zlib.compress(partial)))
        with self.assertRaisesRegex(ValueError, 'differs across arms'):
            anytime_compare.verify(registration)
        with sqlite3.connect(database) as db:
            db.execute("UPDATE artifacts SET data=? WHERE trial_id=1", (zlib.compress(b'tampered'),))
        with self.assertRaisesRegex(ValueError, 'Artifact hash mismatch'):
            anytime_compare.verify(registration)

    def test_frozen_dependency_drift_and_more_than_two_slots_rejected(self):
        registration, config, full = self.fixture()
        with mock.patch.object(anytime_compare, 'isolated') as isolated:
            for workers in (0, 3):
                with self.assertRaises(ValueError):
                    anytime_compare.run(SimpleNamespace(registration=str(registration), workers=workers))
            frozen = self.folder/'frozen'
            frozen.mkdir()
            dependency = frozen/'helper.py'
            dependency.write_text('original fixture\n')
            config['frozen_sha256'][dependency.name] = anytime_compare.sha(dependency)
            registration.write_text(json.dumps(config))
            dependency.write_text('changed fixture\n')
            with self.assertRaisesRegex(ValueError, 'Frozen source/binary changed'):
                anytime_compare.run(SimpleNamespace(registration=str(registration), workers=1))
            isolated.assert_not_called()


class LegacyPreparationParityTests(unittest.TestCase):
    def test_legacy_and_revised_omissions_match_with_truth_table_backend(self):
        """Run the actual Python algorithms, substituting a 3-variable table.

        No native SAT library is imported or queried by this test.
        """
        formula_module, solver_module = ModuleType('pysat.formula'), ModuleType('pysat.solvers')

        class TinyCNF:
            def __init__(self, from_string):
                self.clauses = []
                pending = []
                self.nv = 0
                for line in from_string.splitlines():
                    fields = line.split()
                    if not fields or fields[0] == 'c':
                        continue
                    if fields[0] == 'p':
                        self.nv = int(fields[2])
                        continue
                    for field in fields:
                        lit = int(field)
                        if lit:
                            pending.append(lit)
                            self.nv = max(self.nv, abs(lit))
                        else:
                            self.clauses.append(pending)
                            pending = []

        class TruthTable:
            def __init__(self, bootstrap_with):
                self.clauses = bootstrap_with
                self.nv = max((abs(v) for clause in bootstrap_with for v in clause), default=0)
                self.model = None

            def solve(self, assumptions):
                n = max(self.nv, max(map(abs, assumptions), default=0))
                for signs in itertools.product((-1, 1), repeat=n):
                    witness = {i*sign for i, sign in enumerate(signs, 1)}
                    if all(lit in witness for lit in assumptions) and all(any(v in witness for v in c) for c in self.clauses):
                        self.model = [i*sign for i, sign in enumerate(signs, 1)]
                        return True
                return False

            def get_model(self):
                return self.model

            def delete(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                self.delete()

        formula_module.CNF, solver_module.Cadical195 = TinyCNF, TruthTable
        legacy_source = subprocess.check_output(['git', 'show', 'HEAD:flippable2.py'], cwd=ROOT, text=True)
        legacy, revised = {}, {}
        with mock.patch.dict(sys.modules, {'pysat': ModuleType('pysat'), 'pysat.formula': formula_module,
                                           'pysat.solvers': solver_module}):
            exec(compile(legacy_source, 'legacy_flippable_fixture.py', 'exec'), legacy)
            exec(compile((ROOT/'flippable2.py').read_text(), 'revised_flippable_fixture.py', 'exec'), revised)
            comparisons = 0
            for formula in ('p cnf 3 1\n1 2 0\n',
                            'p cnf 3 2\n1 0\n2 3 0\n',
                            'p cnf 3 3\n1 2 0\n-1 3 0\n-2 -3 0\n',
                            'p cnf 3 3\n1 -1 0\n2 3 0\n-2 -3 0\n'):
                oracle = TruthTable(TinyCNF(formula).clauses)
                checker = revised['FlippabilityChecker'](formula)
                for size in (2, 3):
                    for signs in itertools.product((-1, 1), repeat=size):
                        model = [i*sign for i, sign in enumerate(signs, 1)]
                        if not oracle.solve(model):
                            continue
                        text = 'v '+' '.join(map(str, model))+' 0'
                        with self.subTest(formula=formula, model=model):
                            self.assertEqual(legacy['check_flippable'](formula, text), checker.check(text))
                        comparisons += 1
                checker.close()
        self.assertGreaterEqual(comparisons, 20)


if __name__ == '__main__':
    unittest.main()
