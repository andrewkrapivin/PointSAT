"""Persistence regressions; solver stages are mocked, never long-running searches."""
import concurrent.futures
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from pointsat import cli
from pointsat.geometry import describe, normalize, read_points, real_text, signs
from pointsat.store import RunStore
from pointsat import workflow
from pointsat.workflow import ROOT


TRIANGLE = '1 0 0\n2 1 0\n3 0 1\n'


class InlineExecutor:
    def __init__(self, **kwargs):
        self._processes = {}

    def submit(self, function, job):
        future = concurrent.futures.Future()
        future.set_result(function(job))
        return future

    def shutdown(self, **kwargs):
        pass


class ThreadWorkers(concurrent.futures.ThreadPoolExecutor):
    """Actual concurrency, without native processes or worker initialization."""
    def __init__(self, max_workers, **kwargs):
        super().__init__(max_workers=max_workers)
        self._processes = {}


class AtomicStoreTests(unittest.TestCase):
    def test_solution_failure_rolls_back_event_blobs_and_solution(self):
        for exception in (KeyboardInterrupt, sqlite3.OperationalError):
            with self.subTest(exception=exception.__name__), tempfile.TemporaryDirectory() as temp:
                path = Path(temp)/'candidate.real'
                path.write_text(TRIANGLE)
                result = dict(id=1, original_id=1, type='Realize', status='REALIZED',
                              realized=True, realization_file=str(path))
                with RunStore(Path(temp)/'run.sqlite', create=True) as store:
                    insert = store._insert_solution

                    def fail_after_insert(*args, **kwargs):
                        insert(*args, **kwargs)
                        self.assertEqual(store.db.execute('SELECT count(*) FROM solutions').fetchone()[0], 1)
                        raise exception('injected persistence failure')

                    with patch.object(store, '_insert_solution', side_effect=fail_after_insert):
                        with self.assertRaises(exception):
                            store.record(result, register_solution=True)
                    for table in ('events', 'artifacts', 'blobs', 'solutions'):
                        self.assertEqual(store.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)
                    self.assertEqual(path.read_text(), TRIANGLE)
                    store.record(result, register_solution=True)
                    self.assertEqual(store.status()['solutions'], 1)

    def test_export_recovers_artifacts_after_scratch_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifact = root/'candidate.real'
            artifact.write_text(TRIANGLE)
            database = root/'run.sqlite'
            with RunStore(database, create=True) as store:
                store.record(dict(id=3, original_id=1, type='Realize', status='PARTIAL',
                                  realization_file=str(artifact)))
            artifact.unlink()
            exported = root/'export'
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['export', str(database), '--out', str(exported),
                                           '--events', '--artifacts']), 0)
            event = json.loads((exported/'events.jsonl').read_text())
            self.assertEqual(event['id'], 3)
            with zipfile.ZipFile(exported/'artifacts.zip') as archive:
                index = json.loads(archive.read('index.json'))
                self.assertEqual(len(index), 1)
                self.assertEqual(index[0]['event_id'], event['id'])
                self.assertEqual(index[0]['role'], 'realization_file')
                self.assertEqual(index[0]['original_name'], artifact.name)
                restored = archive.read(index[0]['archive_path'])
                self.assertEqual(restored, TRIANGLE.encode())
                self.assertEqual(hashlib.sha256(restored).hexdigest(), index[0]['sha256'])

    def test_legacy_status_does_not_require_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'summary.json').write_text(json.dumps({'jobs': 2, 'realized': 1}))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli.main(['status', str(root), '--json']), 0)
            self.assertEqual(json.loads(output.getvalue())['storage'], 'legacy')
            self.assertFalse((root/'run.sqlite').exists())

    def test_rejected_optimization_displays_retained_geometry(self):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.print_optimizations([dict(solution_id=1, accepted=False,
                                         before=dict(width=4, height=5, hull_layers=[3]),
                                         after=dict(width=40, height=50, hull_layers=[3]))])
        self.assertIn('4 × 5', output.getvalue())
        self.assertNotIn('40 × 50', output.getvalue())


class OptimizerSelectionTests(unittest.TestCase):
    def test_listing_and_export_choose_requested_preservation(self):
        original = normalize([[0, 0], [8, 0], [0, 9], [2, 3]])
        layer_only = [[0, 0], [0, 3], [3, 0], [1, 1]]
        free = [[0, 0], [1, 0], [1, 1], [0, 1]]
        self.assertEqual(describe(original)['hull_layers'], describe(layer_only)['hull_layers'])
        self.assertNotEqual(signs(original), signs(layer_only))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root/'run.sqlite'
            with RunStore(database, create=True) as store:
                identifier = store.add_solution(original, 'mixed23', 'mock fixture', {'valid': True})
                for candidate in (free, layer_only):
                    store.add_optimization(identifier, candidate, {'accepted': True, 'after': describe(candidate)})
            for mode, expected in ((None, free), ('best', free), ('layers', layer_only), ('order-type', original)):
                with self.subTest(mode=mode):
                    flags = ['--mode', mode] if mode else []
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(cli.main(['solutions', str(database), '--json', *flags]), 0)
                    rows = json.loads(output.getvalue())
                    self.assertEqual(len(rows), 1)
                    info = describe(expected)
                    for key in ('area', 'width', 'height', 'hull_layers'):
                        self.assertEqual(rows[0][key], info[key])
                    destination = root/f'export-{mode or "default"}'
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(cli.main(['export', str(database), '--out', str(destination), *flags]), 0)
                    self.assertEqual(read_points(destination/'solution-0001.pts'), expected)

    @unittest.skipUnless(all((ROOT/'optimizer'/name).is_file() for name in ('compact', 'compact_v2')),
                         'build both optimizer strategies')
    def test_strategy_engine_and_source_preservation_are_independent(self):
        original = normalize([[0, 0], [8, 0], [0, 9], [2, 3]])
        free = [[0, 0], [1, 0], [1, 1], [0, 1]]
        for strategy, binary in (('standard', 'compact'), ('experimental', 'compact_v2')):
            for mode in ('layers', 'order-type', 'free'):
                with self.subTest(strategy=strategy, mode=mode), tempfile.TemporaryDirectory() as temp:
                    with RunStore(Path(temp)/'run.sqlite', create=True) as store:
                        identifier = store.add_solution(original, 'mixed23', 'mock fixture', {'valid': True})
                        store.add_optimization(identifier, free, {'accepted': True, 'after': describe(free)})
                        expected = free if mode == 'free' else original

                        def native(command, timeout):
                            self.assertEqual(Path(command[0]).name, binary)
                            source = Path(command[command.index('--input')+1])
                            output = Path(command[command.index('--output')+1])
                            self.assertEqual(signs(read_points(source)), signs(expected))
                            self.assertEqual('--preserve-layers' in command, mode == 'layers')
                            self.assertEqual('--preserve-order-type' in command, mode == 'order-type')
                            output.write_text(source.read_text())
                            return dict(returncode=0, stdout='', stderr='', timed_out=False, wall_seconds=0)

                        # This test checks orchestration on tiny mock geometry;
                        # exact family validation has separate native tests.
                        with patch.object(workflow, 'native', side_effect=native) as launch, \
                                patch.object(workflow, 'verify_points', return_value={'valid': True}):
                            reports = workflow.optimize_solutions(store, .1, mode=mode, strategy=strategy)
                        launch.assert_called_once()
                        self.assertTrue(reports[0]['accepted'], reports)
                        self.assertEqual(reports[0]['strategy'], strategy)
                        self.assertEqual(reports[0]['before']['orientation_sha256'],
                                         describe(expected)['orientation_sha256'])

    def test_cli_optimizer_defaults_and_explicit_experimental_selection(self):
        for explicit in ([], ['--strategy', 'experimental']):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as temp:
                database = Path(temp)/'run.sqlite'
                with RunStore(database, create=True):
                    pass
                with patch.object(cli, 'optimize_solutions', return_value=[]) as optimize, \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['optimize', str(database), *explicit]), 1)
                args = optimize.call_args.args
                self.assertEqual(args[3], 'layers')
                self.assertEqual(args[5], 'experimental' if explicit else 'standard')


class PipelinePersistenceTests(unittest.TestCase):
    def setUp(self):
        try:
            from improvements.pipeline import runner
        except ImportError:
            self.skipTest('python-sat not installed')
        self.runner = runner

    def settings(self, root, **overrides):
        base = root/'base.cnf'
        base.write_text('p cnf 1 1\n1 0\n')
        settings = dict(base_file=str(base), output_folder=str(root/'run'), n=3,
                        workers=1, n_solutions=1, localizer_attempt_levels=1,
                        localizer_attempt_timeouts=[.1], output_storage='sqlite', quiet_progress=True)
        settings.update(overrides)
        return settings

    def interrupt_run(self, settings, coordinates=TRIANGLE, before_record=False):
        def fake(job):
            if job['type'] == 'SAT':
                return dict(job, satisfiable=True, solution='v 1 0', status='SATISFIABLE')
            Path(job['realization_file']).write_text(coordinates)
            return dict(job, realized=True, status='REALIZED', violations=0, general_position=True)

        original_record = RunStore.record

        def interrupted_record(store, result, **kwargs):
            if result.get('realized'):
                raise KeyboardInterrupt('before transaction')
            return original_record(store, result, **kwargs)

        hook = (patch.object(RunStore, 'record', interrupted_record) if before_record else
                patch.object(RunStore, '_insert_solution', side_effect=KeyboardInterrupt('inside transaction')))
        with patch.object(self.runner, 'ProcessPoolExecutor', InlineExecutor), \
                patch.object(self.runner, '_process_job', side_effect=fake), hook:
            with self.assertRaises(KeyboardInterrupt):
                self.runner.run_pipeline(settings)

    def test_interruption_retains_uncommitted_coordinates_and_honest_counts(self):
        for before in (True, False):
            with self.subTest(before_record=before), tempfile.TemporaryDirectory() as temp:
                settings = self.settings(Path(temp))
                self.interrupt_run(settings, before_record=before)
                with RunStore(Path(settings['output_folder'])/'run.sqlite', readonly=True) as store:
                    status = store.status()
                    self.assertEqual(status['state'], 'interrupted')
                    self.assertEqual(status['events'], 1)  # SAT committed; realization did not.
                    self.assertEqual(status['solutions'], 0)
                    self.assertEqual(status['summary']['realized'], 0)
                    self.assertEqual(status['summary']['distinct_realized_samples'], 0)
                    self.assertEqual(status['summary']['uncommitted_records'], 1)
                    self.assertEqual(store.db.execute('SELECT count(*) FROM blobs').fetchone()[0], 0)
                    files = list(Path(status['recovery_workspace']).glob('*.real'))
                    self.assertEqual(len(files), 1)
                    self.assertEqual(files[0].read_text(), TRIANGLE)

    @unittest.skipUnless((ROOT/'direct/verify_big').is_file(), 'build exact verifier')
    def test_recover_exactly_validates_deduplicates_and_retains_files(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = self.settings(Path(temp), n=23, problem_family='mixed23')
            coordinates = real_text(read_points(ROOT/'direct/seeds/paper23.pts'))
            self.interrupt_run(settings, coordinates)
            out = settings['output_folder']
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['recover', out]), 0)
                self.assertEqual(cli.main(['recover', out]), 0)
            with RunStore(Path(out)/'run.sqlite', readonly=True) as store:
                solutions = list(store.solutions())
                self.assertEqual(len(solutions), 1)
                self.assertTrue(solutions[0]['verification']['valid'])
                self.assertTrue(solutions[0]['verification']['independent_geometric_audit'])
                self.assertEqual(store.get_meta('last_recovery')[0]['status'], 'duplicate_labeled_order_type')
                self.assertTrue(list(Path(store.status()['recovery_workspace']).glob('*.real')))

    def test_two_workers_preserve_active_archive_and_queued_warm_references(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = self.settings(Path(temp), workers=2, n_solutions=2,
                                     localizer_attempt_levels=2, localizer_attempt_timeouts=[.1, .1],
                                     localizer_attempt_thresholds=[2], localizer_attempt_branches=[2],
                                     warm_start_retries=True)
            a_started, archive_ready = threading.Event(), threading.Event()
            first_retry_started, b_committed = threading.Event(), threading.Event()
            shared = {}
            retries = []

            def wait_for(event):
                self.assertTrue(event.wait(5), 'mock worker rendezvous timed out')

            def fake(job):
                sample = job['original_id']
                if job['type'] == 'SAT':
                    if sample == 2:
                        wait_for(a_started)
                    return dict(job, satisfiable=True, solution='v 1 0', status='SATISFIABLE')
                self.assertTrue(Path(job['orientations_file']).is_file())
                output = Path(job['realization_file'])
                output.write_text(TRIANGLE)
                if sample == 2:
                    # Created after A starts; must survive GC while B is active.
                    archive = Path(str(output)+'-archive-00.real')
                    archive.write_text(TRIANGLE)
                    shared['archive'] = archive
                    archive_ready.set()
                    wait_for(first_retry_started)
                    self.assertTrue(archive.is_file())
                    return dict(job, realized=False, status='PARTIAL', violations=99,
                                general_position=True, archive_audits=[{'file': str(archive)}])
                if job['attempt'] == 1:
                    a_started.set()
                    wait_for(archive_ready)
                    shared['warm'] = output
                    return dict(job, realized=False, status='PARTIAL', violations=1, general_position=True)
                # Both retries refer to the same parent's coordinates. The
                # second remains queued while B and the first retry run.
                warm = Path(job['warm_start_file'])
                self.assertEqual(warm, shared['warm'])
                self.assertEqual(warm.read_text(), TRIANGLE)
                retries.append(job['retry_path'])
                if len(retries) == 1:
                    self.assertTrue(shared['archive'].is_file())
                    first_retry_started.set()
                    wait_for(b_committed)
                return dict(job, realized=True, status='REALIZED', violations=0, general_position=True)

            original_record = RunStore.record

            def record(store, result, **kwargs):
                original_record(store, result, **kwargs)
                if result['original_id'] == 2 and result['type'] == 'Realize':
                    b_committed.set()

            with patch.object(self.runner, 'ProcessPoolExecutor', ThreadWorkers), \
                    patch.object(self.runner, '_process_job', side_effect=fake), \
                    patch.object(RunStore, 'record', record):
                summary = self.runner.run_pipeline(settings)
            self.assertEqual(summary['errors'], 0)
            self.assertEqual(summary['jobs'], 6)
            self.assertEqual(len(retries), 2)
            self.assertEqual(summary['realized'], 2)
            out = Path(settings['output_folder'])
            self.assertEqual([p.name for p in out.iterdir()], ['run.sqlite'])
            with RunStore(out/'run.sqlite', readonly=True) as store:
                self.assertEqual(store.db.execute("SELECT count(*) FROM artifacts WHERE role='archive'").fetchone()[0], 1)
                self.assertEqual(store.status()['solutions'], 1)

    def test_explicit_conflicting_problem_never_launches_pipeline(self):
        conflicts = ({'n': 23}, {'problem_family': 'mixed23'},
                     {'base_file': '7gon-6hole-23-compact.cnf', 'n': 26, 'problem_family': 'caps26'})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'settings.json'
            for settings in conflicts:
                with self.subTest(settings=settings):
                    path.write_text(json.dumps(settings))
                    error = io.StringIO()
                    with patch.object(self.runner, 'run_pipeline') as launch, redirect_stderr(error):
                        self.assertEqual(cli.main(['run', '--settings', str(path), '--problem', 'caps26']), 2)
                    launch.assert_not_called()
                    self.assertIn('--problem conflicts', error.getvalue())


if __name__ == '__main__':
    unittest.main()
