#!/usr/bin/env python3
"""Small independent fixtures, no optimizer or long solver benchmarks."""
import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import unittest

try:
    from . import compare19_audit as subject
except ImportError:
    import compare19_audit as subject

ROOT = Path(__file__).resolve().parents[1]
KNOWN = ROOT/'improvements/success19/original/points.real'
KNOWN_TARGET = ROOT/'improvements/success19/original/exact_c3.qsqrt3.or'


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pointsat-compare19-test-')
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, points):
        real = self.folder/'input.real'
        real.write_text(''.join(f'{i+1} {x} {y}\n' for i, (x, y) in enumerate(points)))
        target = self.folder/'input.or'; target.write_text('A_(1,2,3)\n')
        return real, target

    def config(self, **kwargs):
        return dict(output_directory=str(self.folder/'audit'), **kwargs)

    def test_exact_decimal(self):
        real, _ = self.fixture([(0, 0), (10**16, 10**16), (10**16, 10**16+1)])
        self.assertEqual(subject.read_points(real, 3)[2][1], 10**16+1)
        for text in ('1 nan 0\n2 1 2\n3 2 3\n', '1 0 0\n1 1 2\n3 2 3\n'):
            real.write_text(text)
            with self.assertRaises(ValueError):
                subject.read_points(real, 3)

    def test_target_parity_and_malformed(self):
        path = self.folder/'target.or'; path.write_text('B_(2,1,3)\n')
        self.assertEqual(subject.read_target(path), [((1,2,3), 1)])
        for text in ('', 'A_(1,1,2)', 'A_(1,2,20)', 'A_(1,2,3)\nB_(2,1,3)'):
            path.write_text(text)
            with self.assertRaises(ValueError):
                subject.read_target(path)

    def test_parabola_all_hexagons_empty(self):
        real, target = self.fixture([(i, i*i) for i in range(19)])
        result = subject.audit(real, target, self.config())
        self.assertFalse(result['valid_geometry'])
        self.assertTrue(result['general_position'])
        self.assertEqual(result['empty_hexagons'], 27132)
        self.assertEqual(result['hexagons_with_three_inside'], 0)
        self.assertEqual(result['orientation_violations'], 0)
        self.assertEqual(result, subject.audit(real, target, self.config()))
        target.write_text('B_(1,2,3)\n')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            subject.audit(real, target, self.config())

    def test_degenerate_geometry_rejected(self):
        points = [(i, i*i) for i in range(19)]; points[1] = points[0]
        real, target = self.fixture(points)
        result = subject.audit(real, target, self.config())
        self.assertFalse(result['accepted'])
        self.assertFalse(result['general_position'])
        self.assertEqual(result['geometry']['duplicate_pairs'], 1)

    def test_known_witness_and_optional_projection(self):
        result = subject.audit(KNOWN, KNOWN_TARGET, self.config(
            cycles_path=str(ROOT/'improvements/symmetry19/decoded/center19-adjacent.cycles')))
        self.assertTrue(result['valid_geometry'])
        self.assertEqual(result['geometry']['interior_histogram'][:5], [0,15,12,0,1])
        self.assertTrue(result['exact_C3_projection']['valid_geometry'])
        self.assertTrue(result['exact_C3_projection']['signs_preserved'])
        self.assertEqual(result['numeric_cnf']['status'], 'NOT_REQUESTED')
        summary = subject.summarize_checkpoints([result])
        self.assertTrue(summary['valid_geometry'])
        self.assertEqual(summary['minimum_forbidden_hexagons_in_GP'], 0)
        invalid_final = dict(result, valid_geometry=False, forbidden_hexagons=3)
        summary = subject.summarize_checkpoints([result, invalid_final])
        self.assertFalse(summary['final_valid_geometry'])
        self.assertFalse(summary['valid_geometry'])
        self.assertTrue(summary['any_saved_valid_geometry'])

    def test_mapping_conflict_is_not_geometric_failure(self):
        model = subject.orientation_model(subject.read_points(KNOWN))
        entries = [{'triple': list(t), 'literal': subject.sign(model[subject.colex_rank(t)-1])}
                   for t in itertools.combinations(range(1,20), 3)]
        path = self.folder/'mapping.json'
        path.write_text(json.dumps({'n': 19, 'primary_variables': 1, 'entries': entries}))
        projected, details = subject.project_model(model, path)
        self.assertEqual(projected, [1]); self.assertTrue(details['mapping_consistent'])
        entries[-1]['literal'] *= -1
        path.write_text(json.dumps({'n': 19, 'primary_variables': 1, 'entries': entries}))
        result = subject.audit(KNOWN, KNOWN_TARGET, self.config(orientation_map_path=str(path)))
        self.assertTrue(result['accepted'])
        self.assertFalse(result['numeric_cnf']['satisfiable'])
        self.assertEqual(result['numeric_cnf']['reason'], 'orbit_sign_conflict')

    def test_cnf_scan_and_failure_separate_from_geometry(self):
        if importlib.util.find_spec('pysat') is None:
            self.skipTest('Use direct/vendor/venv/bin/python for the fresh SAT check')
        first = subject.orientation_model(subject.read_points(KNOWN))[0]
        cnf = self.folder/'small.cnf'; cnf.write_text(f'p cnf 969 1\n{-first} 0\n')
        result = subject.audit(KNOWN, KNOWN_TARGET, self.config(cnf_path=str(cnf)))
        self.assertTrue(result['accepted']); self.assertEqual(result['numeric_cnf']['status'], 'UNSAT')
        cnf.write_text(f'p cnf 969 1\n{first} 0\n')
        result = subject.audit(KNOWN, KNOWN_TARGET, dict(output_directory=str(self.folder/'audit2'), cnf_path=str(cnf)))
        self.assertEqual(result['numeric_cnf']['violated_clauses'], 0)
        self.assertEqual(result['numeric_cnf']['wrong_orientation_assumptions'], 0)

    def test_frozen_hash_drift(self):
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            subject.audit(KNOWN, KNOWN_TARGET, self.config(expected_sha256={str(KNOWN): 'bad'}))

    def test_original_mapped_cnf_success(self):
        if importlib.util.find_spec('pysat') is None:
            self.skipTest('Use direct/vendor/venv/bin/python for the fresh SAT check')
        result = subject.audit(KNOWN, KNOWN_TARGET, self.config(
            cnf_path=str(ROOT/'convex_hexagon_inside_19_3sym.cnf'),
            orientation_map_path=str(ROOT/'improvements/symmetry19/variants/mapping.json')))
        self.assertTrue(result['valid_geometry'])
        self.assertEqual(result['numeric_cnf']['status'], 'SAT')
        self.assertEqual(result['numeric_cnf']['projected_variables'], 327)
        self.assertEqual(result['numeric_cnf']['clauses'], 2311196)
        self.assertEqual(result['numeric_cnf']['violated_clauses'], 0)


if __name__ == '__main__':
    unittest.main()
