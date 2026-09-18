"""Exact predicates and deadline tests; no optimizer or SAT generation."""
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('anytime_geometry', Path(__file__).with_name('anytime_geometry.py'))
geometry = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(geometry)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pointsat-anytime-geometry-')
        self.folder = Path(self.tmp.name); self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def audit(self, source, family, seconds=30):
        self.counter += 1
        verifier = ROOT/('improvements/symmetry19/verify_hexagons' if family == 'symmetry19' else 'direct/verify_big')
        return geometry.audit(source, family, {'output_directory': self.folder/str(self.counter),
            'verifier_path': verifier, 'expected_verifier_sha256': geometry.digest(verifier.read_bytes()),
            'deadline_monotonic': time.monotonic()+seconds})

    def test_exact_decimal_and_index_validation(self):
        points = geometry.integer_points(b'1 0.1 0.2\n2 0.3 0.2\n3 0.1 0.5\n', 3)
        self.assertEqual(points, [(0,0),(2,0),(0,3)])
        for data in (b'1 nan 0\n2 1 0\n3 0 1\n', b'1 1e999999999 0\n2 1 0\n3 0 1\n',
                     b'1 0 0\n1 1 0\n3 0 1\n'):
            with self.assertRaises(ValueError):
                geometry.integer_points(data, 3)

    def test_caps_dp_matches_exhaustive(self):
        rng = random.Random(701)
        for n in range(5, 13):
            for _ in range(5):
                points = [(i, rng.randrange(-100,101)) for i in range(n)]
                expected = sum(all(geometry.cross(p[i],p[i+1],p[i+2]) < 0 for i in range(3))
                               for p in itertools.combinations(points, 5))
                self.assertEqual(geometry.count_caps(points), expected)
        for _ in range(20):
            points = sorted((rng.randrange(6), rng.randrange(-100,101)) for i in range(10))
            expected = sum(all(p[i][0] < p[i+1][0] for i in range(4)) and
                           all(geometry.cross(p[i],p[i+1],p[i+2]) < 0 for i in range(3))
                           for p in itertools.combinations(points, 5))
            self.assertEqual(geometry.count_caps(points), expected)

    def test_deadline_before_work_cannot_accept(self):
        result = self.audit(ROOT/'direct/seeds/paper23.pts', 'mixed23', seconds=-1)
        self.assertEqual(result['status'], 'DEADLINE_EXCEEDED')
        self.assertFalse(result['accepted']); self.assertIsNone(result['accepted_timestamp_monotonic'])

    def test_deadline_during_verification_kills_owned_child(self):
        sleeper = self.folder/'slow-verifier'
        sleeper.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(10)\n'); sleeper.chmod(0o755)
        before = time.monotonic()
        result = geometry.audit(ROOT/'direct/seeds/paper23.pts', 'mixed23', {
            'output_directory': self.folder/'slow', 'verifier_path': sleeper,
            'deadline_monotonic': before+.05})
        self.assertEqual(result['status'], 'DEADLINE_EXCEEDED')
        self.assertFalse(result['accepted']); self.assertIsNone(result['accepted_timestamp_monotonic'])
        self.assertLess(time.monotonic()-before, 1)

    def test_non_gp_and_caps_rejected_without_verifier(self):
        for family, points in [('mixed23', [(i,0) for i in range(23)]),
                               ('caps26', [(i,-i*i) for i in range(26)])]:
            source = self.folder/(family+'.pts')
            source.write_text(str(len(points))+'\n'+''.join(f'{x} {y}\n' for x,y in points))
            result = self.audit(source, family)
            self.assertFalse(result['accepted']); self.assertFalse(result['valid_geometry'])
            self.assertNotIn('verifier_command', result)

    def test_fake_incomplete_or_inconsistent_claim_rejected(self):
        valid = {'n': 23, 'gon': 7, 'hole': 6, 'valid': True, 'collinear_triples': 0,
                 'convex_gons': 0, 'empty_holes': 0, 'gon_subsets_checked': math.comb(23,7),
                 'hole_subsets_checked': math.comb(23,6)}
        self.assertEqual(geometry.validate_output(valid, 'mixed23', 0, 0), 0)
        for changed in ({'gon_subsets_checked': 1}, {'empty_holes': 1}, {'collinear_triples': 2}):
            with self.assertRaises(ValueError):
                geometry.validate_output(dict(valid, **changed), 'mixed23', 0, 0)

    def test_known_positive_controls_all_five_families(self):
        fixtures = {'symmetry19': 'improvements/success19/original/points.real',
                    'mixed23': 'direct/seeds/paper23.pts', 'holes29': 'benchmarks/success29/trial11/normalized.pts',
                    'gons32': 'direct/seeds/es32.pts', 'caps26': 'direct/seeds/es26cap5.pts'}
        for family, source in fixtures.items():
            with self.subTest(family=family):
                result = self.audit(ROOT/source, family)
                self.assertTrue(result['accepted'], result)
                self.assertLessEqual(result['accepted_timestamp_monotonic'], result['deadline_monotonic'])
                proof = json.loads(Path(result['certificate']).read_text())
                self.assertGreaterEqual(result['accepted_timestamp_monotonic'], proof['certificate_validated_monotonic'])
                self.assertNotIn('accepted_timestamp_monotonic', proof)
                self.assertEqual(geometry.digest(Path(result['certificate']).read_bytes()), result['certificate_sha256'])


if __name__ == '__main__':
    unittest.main()
