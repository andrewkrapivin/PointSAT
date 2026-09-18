import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pointsat.geometry import bounded_points, describe, normalize, pts_text, read_points, signs
from pointsat.store import RunStore, unpack
from pointsat.workflow import ROOT, import_coordinates, optimize_solutions, verify_points


class GeometryTests(unittest.TestCase):
    def test_exact_formats_and_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'a.real'
            path.write_text('3 0 0.30\n1 0 0\n2 0.20 0\n')
            self.assertEqual(read_points(path), [[0, 0], [1, 0], [0, 1]])
            path.write_text('3\n-10 -10\n10 -10\n-10 20\n')
            self.assertEqual(read_points(path), [[0, 0], [1, 0], [0, 1]])

    def test_malformed_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad'
            for content in ('', '3\n0 0\n1 1\n', '1 0 0\n1 1 0\n3 0 1\n',
                            '3\n0 0\n1 nan\n0 1\n', '3\n0 0\n1 0\n0 1\nextra'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    read_points(path)

    def test_layers_and_general_position(self):
        info = describe([[0, 0], [8, 0], [0, 9], [2, 3]])
        self.assertEqual(info['hull_layers'], [3, 1])
        self.assertEqual(info['area'], 72)
        with self.assertRaises(ValueError):
            describe([[0, 0], [1, 1], [2, 2]])

    def test_bounded_rounding_preserves_all_signs(self):
        points = [[0, 0], [10**30+1, 0], [0, 10**30+3], [10**29+7, 2*10**29+9]]
        trial = bounded_points(points)
        self.assertEqual(signs(trial), signs(points))
        self.assertLessEqual(max(max(p) for p in trial), 10**12)


class StoreTests(unittest.TestCase):
    def test_content_dedup_roundtrip_and_live_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            database, artifact = Path(tmp)/'run.sqlite', Path(tmp)/'points.real'
            artifact.write_text('1 0 0\n2 1 0\n3 0 1\n')
            with RunStore(database, create=True) as store:
                for i in (1, 2):
                    store.record(dict(id=i, original_id=1, type='Realize', status='PARTIAL',
                                      realization_file=str(artifact), solution='v 1 0'))
                self.assertEqual(store.db.execute('SELECT count(*) FROM blobs').fetchone()[0], 1)
                self.assertEqual(len(list(store.events())), 2)
                with RunStore(database, readonly=True) as reader:
                    self.assertEqual(reader.status()['events'], 2)
                with self.assertRaises(FileExistsError):
                    RunStore(database, create=True)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['points.real', 'run.sqlite'])

    def test_solution_dedup_and_best(self):
        with tempfile.TemporaryDirectory() as tmp, RunStore(Path(tmp)/'run.sqlite', create=True) as store:
            points = [[0, 0], [10, 0], [0, 10]]
            identifier = store.add_solution(points, None, 'fixture', {'valid': True})
            self.assertEqual(identifier, store.add_solution(points, None, 'same', {'valid': True}))
            small = [[0, 0], [1, 0], [0, 1]]
            store.add_optimization(identifier, small, {'accepted': True, 'after': describe(small)})
            selected, info = store.best_points(next(store.solutions()))
            self.assertEqual(selected, small)
            self.assertEqual(info['area'], 1)

    def test_preservation_refers_to_original_not_prior_free_optimization(self):
        with tempfile.TemporaryDirectory() as tmp, RunStore(Path(tmp)/'run.sqlite', create=True) as store:
            original = [[0, 0], [8, 0], [0, 9], [2, 3]]
            free = [[0, 0], [1, 0], [1, 1], [0, 1]]
            identifier = store.add_solution(original, None, 'fixture', {'valid': True})
            store.add_optimization(identifier, free, {'accepted': True, 'after': describe(free)})
            solution = next(store.solutions())
            self.assertEqual(store.best_points(solution)[0], free)
            self.assertEqual(store.best_points(solution, 'layers')[0], original)
            self.assertEqual(store.best_points(solution, 'order-type')[0], original)

    @unittest.skipUnless((ROOT/'direct/verify_big').is_file(), 'build exact verifier')
    def test_automatic_import_paper(self):
        with tempfile.TemporaryDirectory() as tmp, RunStore(Path(tmp)/'run.sqlite', create=True) as store:
            rows = import_coordinates(store, ROOT/'direct/seeds/paper23.pts', 'mixed23')
            self.assertEqual(rows[0]['status'], 'imported')
            self.assertEqual(rows[0]['info']['hull_layers'], [3, 4, 4, 6, 5, 1])
            self.assertEqual(import_coordinates(store, ROOT/'direct/seeds/paper23.pts', 'mixed23')[0]['status'], 'duplicate_labeled_order_type')

    @unittest.skipUnless((ROOT/'optimizer/compact').is_file() and (ROOT/'direct/verify_big').is_file(), 'build native tools')
    def test_automatic_optimize_and_certify(self):
        with tempfile.TemporaryDirectory() as tmp, RunStore(Path(tmp)/'run.sqlite', create=True) as store:
            import_coordinates(store, ROOT/'direct/seeds/paper23.pts', 'mixed23')
            rows = optimize_solutions(store, .05, 1, 'layers')
            self.assertEqual(len(rows), 1)
            self.assertNotIn('error', rows[0], rows[0])
            self.assertTrue(rows[0]['accepted'])
            self.assertEqual(rows[0]['before']['hull_layers'], rows[0]['after']['hull_layers'])
            self.assertTrue(rows[0]['verification']['valid'])


class InlineExecutor:
    def __init__(self, **kwargs):
        self._processes = {}

    def submit(self, function, job):
        future = concurrent.futures.Future()
        future.set_result(function(job))
        return future

    def shutdown(self, **kwargs):
        pass


class CompactPipelineTests(unittest.TestCase):
    def test_bounded_temporary_files_and_warm_retries(self):
        try:
            from improvements.pipeline import runner
        except ImportError:
            self.skipTest('python-sat not installed')
        with tempfile.TemporaryDirectory() as tmp:
            base, out = Path(tmp)/'base.cnf', Path(tmp)/'run'
            base.write_text('p cnf 1 1\n1 0\n')
            peak = 0
            def fake(job):
                nonlocal peak
                peak = max(peak, len(list(out.rglob('*.real'))))
                if job['type'] == 'SAT':
                    return dict(job, satisfiable=True, solution='v 1 0', status='SATISFIABLE')
                self.assertTrue(Path(job['orientations_file']).is_file())
                if job.get('warm_start_file'):
                    self.assertTrue(Path(job['warm_start_file']).is_file())
                Path(job['realization_file']).write_text('1 0 0\n2 1 0\n3 0 1\n')
                return dict(job, realized=job['attempt']==2, status='REALIZED' if job['attempt']==2 else 'PARTIAL',
                            violations=0 if job['attempt']==2 else 1, general_position=True)
            settings = dict(base_file=str(base), output_folder=str(out), n=3, workers=1,
                            n_solutions=50, localizer_attempt_levels=2, localizer_attempt_timeouts=[.1, .1],
                            localizer_attempt_thresholds=[2], localizer_attempt_branches=[1],
                            warm_start_retries=True, output_storage='sqlite', quiet_progress=True)
            with patch.object(runner, 'ProcessPoolExecutor', InlineExecutor), patch.object(runner, '_process_job', side_effect=fake):
                summary = runner.run_pipeline(settings)
            self.assertEqual(summary['realized'], 50)
            self.assertLessEqual(peak, 2)
            self.assertEqual([p.name for p in out.iterdir()], ['run.sqlite'])
            with RunStore(out/'run.sqlite', readonly=True) as store:
                self.assertEqual(store.status()['events'], 150)
                self.assertEqual(store.status()['solutions'], 1)
                self.assertEqual(store.get_meta('state'), 'finished')
                self.assertEqual(len(list(store.events())), 150)

    def test_storage_and_deadline_settings_validation(self):
        try:
            from improvements.pipeline.runner import normalize_settings
        except ImportError:
            self.skipTest('python-sat not installed')
        for settings in ({'output_storage': 'typo'}, {'wall_time_limit': float('nan')}, {'wall_time_limit': -1}):
            with self.assertRaises(ValueError):
                normalize_settings(settings)


if __name__ == '__main__':
    unittest.main()
