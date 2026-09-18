import json
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from improvements.pipeline.orientation_map import OrientationMap
from improvements.pipeline.runner import parse_sat_output


class OrientationMapTests(unittest.TestCase):
    def test_signed_noncontiguous_projection(self):
        data = {'n': 4, 'primary_variables': 2,
                'entries': [{'triple': t, 'literal': lit} for t, lit in
                            [([1,2,3],5),([1,2,4],-5),([1,3,4],8),([2,3,4],-8)]]}
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp)/'map.json'
            filename.write_text(json.dumps(data))
            adapter = OrientationMap(filename, 4)
            self.assertEqual(adapter.variables, [5,8])
            self.assertEqual(adapter.orientations([5,-8]), 'A_(1, 2, 3)\nB_(1, 2, 4)\nB_(1, 3, 4)\nA_(2, 3, 4)\n')
            self.assertEqual(adapter.project([1,-2,-3,4]), ([5,-8], []))
            projected, conflicts = adapter.project([-1,-2,-3,4])
            self.assertIsNone(projected)
            self.assertEqual(conflicts[0]['variable'], 5)
            self.assertEqual(len(adapter.orientations([-8]).splitlines()), 2)
            status, projected = parse_sat_output('s SATISFIABLE\nv 5 -8 99 0', 4, adapter.variables)
            self.assertEqual(projected, [5,-8])
            with self.assertRaises(ValueError):
                parse_sat_output('s SATISFIABLE\nv 5 0', 4, adapter.variables)

    def test_actual_c3_map_roundtrip(self):
        directory = Path('improvements/symmetry19/variants')
        if not (directory/'mapping.json').exists():
            self.skipTest('Optional user-provided19-point input is not present')
        adapter = OrientationMap(directory/'mapping.json', 19)
        self.assertEqual(len(adapter.variables), 327)
        model = json.loads((directory/'model000.json').read_text())['primary_model']
        self.assertEqual(adapter.orientations(model), (directory/'model000.or').read_text())
        assignment = {abs(lit): 1 if lit > 0 else -1 for lit in model}
        colex = [0]*969
        for triple, literal, rank in adapter.entries:
            colex[rank-1] = rank*assignment[abs(literal)]*(1 if literal > 0 else -1)
        self.assertEqual(adapter.project(colex), (model, []))
        counts = Counter(abs(literal) for _, literal, _ in adapter.entries)
        rank = next(rank for _, literal, rank in adapter.entries if counts[abs(literal)] > 1)
        colex[rank-1] *= -1
        self.assertIsNone(adapter.project(colex)[0])


if __name__ == '__main__':
    unittest.main()
