#!/usr/bin/env python3
"""Harness safety tests using short fake Python children, never native searches."""
import json
import io
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

from benchmarks import compare19 as subject


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-harness-test-')
        self.folder = Path(self.temp.name)
        self.config = {'paths': {'original': 'fake-original', 'improved': 'fake-improved',
                                 'fixed': 'fixed.txt', 'cycles': 'cycles.txt'},
                       'native_save_grace': .15, 'native_seconds': .15}
        subject.STOP.clear()

    def tearDown(self):
        subject.STOP.clear()
        self.temp.cleanup()

    def run_fake_native(self, script, arm='original', warm=None):
        popen = subprocess.Popen

        def fake(command, **kwargs):
            output = command[command.index('-o')+1]
            return popen([sys.executable, '-c', script, output], **kwargs)

        with mock.patch.object(subject.subprocess, 'Popen', side_effect=fake):
            return subject.native(self.config, arm, self.folder/'input.or', self.folder/'stage.real',
                                  17, .15, warm=warm)

    def test_original_sigint_saves_before_grace_expires(self):
        result = self.run_fake_native(
            "import pathlib,signal,sys,time\n"
            "def save(*args):\n"
            " pathlib.Path(sys.argv[1]).write_text('saved-on-SIGINT\\n')\n"
            " raise SystemExit(0)\n"
            "signal.signal(signal.SIGINT,save)\n"
            "time.sleep(30)\n")
        self.assertTrue(result['budget_signal'])
        self.assertFalse(result['forced_kill'])
        self.assertTrue(result['output_saved'])
        self.assertEqual(result['returncode'], 0)
        self.assertEqual((self.folder/'stage.real').read_text(), 'saved-on-SIGINT\n')
        command = result['command']
        self.assertEqual(command[command.index('-t')+1], '1')
        self.assertNotIn('-T', command)
        self.assertNotIn('-w', command)
        self.assertLess(result['native_wall_seconds'], 2)

    def test_original_ignored_interrupt_is_killed_and_missing(self):
        result = self.run_fake_native(
            "import signal,time\nsignal.signal(signal.SIGINT,signal.SIG_IGN)\ntime.sleep(30)\n")
        self.assertTrue(result['budget_signal'])
        self.assertTrue(result['forced_kill'])
        self.assertFalse(result['output_saved'])
        self.assertEqual(result['returncode'], -signal.SIGKILL)
        self.assertLess(result['native_wall_seconds'], 2)

    def test_clean_exit_without_output_is_not_saved(self):
        result = self.run_fake_native('pass\n')
        self.assertEqual(result['returncode'], 0)
        self.assertFalse(result['output_saved'])
        self.assertFalse(result['budget_signal'])

    def test_improved_command_has_same_single_thread_and_bounded_warm_start(self):
        warm = self.folder/'previous.real'
        result = self.run_fake_native('pass\n', arm='improved_feedback', warm=warm)
        command = result['command']
        self.assertEqual(command[command.index('-t')+1], '1')
        self.assertEqual(float(command[command.index('-T')+1]), .15)
        self.assertEqual(command[command.index('-w')+1], str(warm))

    def fake_worker(self, body):
        frozen = self.folder/'frozen'
        frozen.mkdir(exist_ok=True)
        (frozen/'compare19.py').write_text(
            "import json,os,pathlib,signal,subprocess,sys,time\n"
            "work=pathlib.Path(sys.argv[sys.argv.index('--work')+1])\n"+body)
        registration = self.folder/'registration.json'
        registration.write_text('{}\n')
        work = self.folder/'work'
        work.mkdir()
        return registration, work

    @staticmethod
    def process_running(pid):
        try:
            # A killed, not-yet-reaped descendant may briefly remain a zombie.
            stat = Path(f'/proc/{pid}/stat').read_text()
            return stat[stat.rfind(')')+2:].split()[0] not in ('Z', 'X')
        except FileNotFoundError:
            return False

    def test_worker_exit_also_kills_owned_descendant(self):
        registration, work = self.fake_worker(
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
            "(work/'descendant.pid').write_text(str(p.pid))\n"
            "(work/'result.json').write_text(json.dumps({'status':'FINISHED'}))\n")
        result = subject.isolated({'python': sys.executable}, registration, {'id': 0},
                                  'original', work, 2)
        pid = int((work/'descendant.pid').read_text())
        try:
            deadline = time.monotonic()+1
            while self.process_running(pid) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse(self.process_running(pid))
            self.assertEqual(result['returncode'], 0)
            self.assertFalse(result['overhead_watchdog'])
        finally:
            if self.process_running(pid):
                os.kill(pid, signal.SIGKILL)

    def test_worker_watchdog_is_bounded(self):
        registration, work = self.fake_worker(
            "signal.signal(signal.SIGINT,signal.SIG_IGN)\ntime.sleep(30)\n")
        result = subject.isolated({'python': sys.executable}, registration, {'id': 0},
                                  'original', work, .15)
        self.assertTrue(result['overhead_watchdog'])
        self.assertFalse(result['externally_interrupted'])
        self.assertEqual(result['returncode'], -signal.SIGKILL)
        self.assertLess(result['parent_wall_seconds'], 3)

    def test_stop_is_distinct_from_budget_expiration(self):
        registration, work = self.fake_worker('time.sleep(30)\n')
        subject.STOP.set()
        result = subject.isolated({'python': sys.executable}, registration, {'id': 0},
                                  'original', work, 10)
        self.assertTrue(result['externally_interrupted'])
        self.assertFalse(result['overhead_watchdog'])
        self.assertLess(result['parent_wall_seconds'], 3)

    def test_frozen_dependency_drift_rejected_before_any_work(self):
        frozen = self.folder/'frozen'
        frozen.mkdir()
        dependency = frozen/'compare19_audit.py'
        dependency.write_text('original audit fixture\n')
        config = {'frozen_sha256': {dependency.name: subject.sha(dependency)}}
        registration = self.folder/'registration.json'
        registration.write_text(json.dumps(config))
        dependency.write_text('changed audit fixture\n')
        args = SimpleNamespace(registration=str(registration), workers=2)
        with mock.patch.object(subject, 'isolated') as isolated:
            with self.assertRaises((AssertionError, ValueError)):
                subject.run(args)
            isolated.assert_not_called()

    def test_failed_feedback_never_promotes_first_checkpoint_to_primary(self):
        config = dict(self.config, cases=[{'id': 0, 'seed': 17}])
        config['paths'] = dict(config['paths'], mapping='unused-mapping')
        registration = self.folder/'registration.json'
        registration.write_text(json.dumps(config))
        work = self.folder/'work'
        work.mkdir()
        (work/'initial.or').write_text('A_(1,2,3)\n')
        modules = {name: ModuleType(name) for name in
                   ('orientation_map', 'flippable2', 'sat_orient_conversion', 'feedback')}
        modules['orientation_map'].OrientationMap = lambda *args: object()
        modules['flippable2'].FlippabilityChecker = object

        def bad_inspection(*unused):
            raise ValueError('simulated feedback failure')

        modules['sat_orient_conversion'].inspect_realization = bad_inspection
        modules['feedback'].orientation_margins = object
        modules['feedback'].core_guided_feedback = object

        def save_first(config, arm, target, output, seed, seconds, warm=None):
            output.write_text('saved first checkpoint\n')
            return {'file': output.name, 'output_saved': True}

        args = SimpleNamespace(registration=str(registration), case=0,
                               arm='improved_feedback', work=str(work), budget=.15)
        path_before = list(sys.path)
        try:
            with mock.patch.dict(sys.modules, modules), mock.patch.object(subject, 'native', side_effect=save_first):
                with self.assertRaisesRegex(ValueError, 'simulated feedback'):
                    subject.worker(args)
        finally:
            sys.path[:] = path_before
        report = json.loads((work/'result.json').read_text())
        self.assertEqual(report['status'], 'ERROR')
        self.assertEqual(report['final_checkpoint'], 'stage1.real')
        self.assertFalse((work/'stage1.real').exists())

    def test_multibudget_resume_final_endpoint_affinity_and_late_artifacts(self):
        """All runner orchestration is mocked; real SQLite exercises durability."""
        frozen = self.folder/'frozen'
        frozen.mkdir()
        cnf = self.folder/'input.cnf'
        cnf.write_text('p cnf 1 1\n1 0\n')
        budgets = [10, 30, 60]
        case = {'id': 0, 'seed': 17, 'primary_model': [1],
                'experiments': [{'arm': arm, 'budget': budget}
                                for arm in subject.ARMS for budget in budgets]}
        config = dict(self.config, cases=[case], budgets=budgets, cnf=str(cnf),
                      cnf_sha256=subject.sha(cnf), frozen_sha256={},
                      prepare_seconds=1, trial_overhead_cap=1, audit_seconds=1)
        config['paths'] = dict(config['paths'], mapping='unused')
        registration = self.folder/'registration.json'
        registration.write_text(json.dumps(config))
        calls = []
        fail_once = [True]

        def fake_isolated(config, registration, selected, arm, work, limit, budget=0):
            calls.append((arm, budget))
            common = dict(parent_cpu_seconds=.001, parent_wall_seconds=.001,
                          returncode=0, overhead_watchdog=False,
                          externally_interrupted=False, cpu_accounting_flag=False)
            if arm == 'prepare':
                return dict(common, status='PREPARED', partial_model=[1], flippables=[])
            if arm == 'audit':
                late = work/'nested'
                late.mkdir()
                (late/'late-audit.txt').write_text('created only during posthoc auditing')
                audits = [{'checkpoint': path.name, 'valid_geometry': True}
                          for path in work.glob('stage*.real')]
                return dict(common, status='AUDITED', audits=audits)
            if fail_once[0]:
                fail_once[0] = False
                raise RuntimeError('simulated controller failure after attempt registration')
            if arm != 'original':
                (work/'stage0.real').write_text('first checkpoint')
            return dict(common, status='MISSING_OUTPUT' if arm == 'original' else 'FINISHED',
                        final_checkpoint='stage1.real' if arm == 'improved_feedback' else 'stage0.real',
                        stages=[{'file': 'stage0.real', 'output_saved': arm != 'original',
                                 'native_cpu_seconds': .001, 'native_wall_seconds': .001}])

        adapter_module = SimpleNamespace(OrientationMap=lambda *args: SimpleNamespace(
            orientations=lambda model: 'A_(1,2,3)\n'))
        args = SimpleNamespace(registration=str(registration), workers=2)
        with mock.patch.object(subject, 'isolated', side_effect=fake_isolated), \
                mock.patch.object(subject, 'module', return_value=adapter_module), \
                mock.patch.object(subject.os, 'sched_getaffinity', return_value={9, 3, 5}), \
                mock.patch.object(subject.os, 'sched_setaffinity') as affinity, \
                mock.patch.object(subject.signal, 'signal'), mock.patch('sys.stdout', new_callable=io.StringIO):
            with self.assertRaisesRegex(RuntimeError, 'simulated controller failure'):
                subject.run(args)
            with sqlite3.connect(self.folder/'results.sqlite') as db:
                attempts = db.execute('SELECT complete,record FROM trials').fetchall()
                self.assertEqual(len(attempts), 1)
                self.assertEqual(attempts[0][0], 0)
                pending = json.loads(attempts[0][1])
                self.assertEqual(pending['status'], 'RUNNING')
                self.assertTrue(Path(pending['workspace']).is_dir())
            subject.STOP.clear()  # A real resumed CLI starts a fresh interpreter.
            subject.run(args)
            before_resume = list(calls)
            subject.run(args)
            self.assertEqual(calls, before_resume)
            self.assertEqual(affinity.call_args_list, [mock.call(0, [3, 5])]*3)
        self.assertEqual(calls.count(('prepare', 0)), 1)
        for arm in subject.ARMS:
            for budget in budgets:
                self.assertEqual(calls.count((arm, budget)), 2 if (arm, budget) == ('original', 10) else 1)
        with sqlite3.connect(self.folder/'results.sqlite') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM trials').fetchone()[0], 10)
            rows = db.execute('SELECT case_id,arm,budget,complete,record FROM trials WHERE complete=1').fetchall()
            self.assertEqual(len(rows), 9)
            self.assertEqual(len({row[:3] for row in rows}), 9)
            for _, arm, _, complete, record in rows:
                report = json.loads(record)
                self.assertEqual(complete, 1)
                self.assertEqual(report['primary_valid_geometry'], arm == 'improved_fixed')
                self.assertEqual(report['any_saved_valid_geometry'], arm != 'original')
            artifacts = db.execute("SELECT data FROM artifacts WHERE name='nested/late-audit.txt'").fetchall()
            self.assertEqual(len(artifacts), 9)
            self.assertTrue(all(zlib.decompress(row[0]) == b'created only during posthoc auditing'
                                for row in artifacts))


if __name__ == '__main__':
    unittest.main()
