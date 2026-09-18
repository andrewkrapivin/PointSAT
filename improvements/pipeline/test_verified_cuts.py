"""Soundness regression tests using the independently checked 19-point proofs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from improvements.pipeline.orientation_map import OrientationMap
from improvements.pipeline import runner
from improvements.pipeline.verified_cuts import load_verified_proof, mapped_clause, supported_by_target
from sat_orient_conversion import orient, parse_constraints

ROOT = Path(__file__).resolve().parents[2]


class VerifiedCutsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = OrientationMap(ROOT/'improvements/symmetry19/variants/mapping.json', 19)
        cls.full = load_verified_proof(ROOT/'improvements/realizability/results/supplied19-rational.json', 19)
        cls.partial = load_verified_proof(ROOT/'improvements/realizability/results/relaxed002.json', 19)
        cls.target = ROOT/'improvements/symmetry19/variants/model002-relaxed.or'

    def test_partial_projection(self):
        self.assertEqual(len(mapped_clause(self.full, self.adapter)), 327)
        self.assertEqual(len(mapped_clause(self.partial, self.adapter)), 318)
        self.assertEqual(self.partial['verified']['blocking_literals'], 939)

    def test_all_premises_required(self):
        self.assertTrue(supported_by_target(self.partial, self.target))
        wanted = -self.partial['blocking_clause'][0]
        rows = self.target.read_text().splitlines()
        constraints = parse_constraints(self.target)
        index = next(i for i, (sign, triple) in enumerate(constraints) if sign*orient(*triple) == wanted)
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)/'missing.or'
            candidate.write_text('\n'.join(rows[:index]+rows[index+1:])+'\n')
            self.assertFalse(supported_by_target(self.partial, candidate))

    def test_corrupt_proof_rejected(self):
        proof = json.loads(Path(self.partial['path']).read_text())
        proof['certificate'][0]['weight'] += 1
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)/'bad.json'
            candidate.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                load_verified_proof(candidate, 19)

    def test_native_is_not_called_for_certified_target(self):
        settings = runner.normalize_settings({'n':19, 'nonrealizability_proof_files':[self.partial['path']]})
        state = {'settings':settings, 'verified_proofs':[self.partial]}
        with patch.object(runner, '_state', state), patch.object(runner, '_stop_requested', False), \
             patch.object(runner, 'run_process') as process:
            result = runner._process_job({'type':'Realize', 'orientations_file':str(self.target)})
        self.assertEqual(result['status'], 'PROVED_NONREALIZABLE')
        self.assertFalse(result['realized'])
        process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
