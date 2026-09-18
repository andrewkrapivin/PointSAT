"""Tiny SAT/controller tests only; never run the19-point generator here."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from benchmarks.compare19_inputs import ROOT, distance_clauses, load_models, validate_extension
from pysat.solvers import Cadical195


class CorpusTests(unittest.TestCase):
    def fixture(self, root):
        cnf, mapping = root/'tiny.cnf', root/'map.json'
        cnf.write_text('p cnf 4 4\n1 0\n2 -2 0\n3 -3 0\n4 -4 0\n')
        mapping.write_text(json.dumps(dict(n=4, primary_variables=4, entries=[
            dict(triple=list(triple), literal=i) for i, triple in enumerate(itertools.combinations(range(1,5),3),1)])))
        return cnf, mapping

    def run_generator(self, root, count, seconds):
        cnf, mapping = self.fixture(root)
        output = root/'corpus'
        result = subprocess.run([sys.executable, str(ROOT/'benchmarks/compare19_inputs.py'),
                                 '--output', str(output), '--cnf', str(cnf), '--orientation-map', str(mapping),
                                 '--count', str(count), '--min-distance', '1', '--seconds', str(seconds)],
                                text=True, capture_output=True, timeout=12)
        return result, output

    def test_cardinality_distance_and_fresh_auxiliary_ids(self):
        primary = [1,-2,3,-4]
        clauses, top = distance_clauses(primary, 2, 100)
        first_aux = {abs(lit) for row in clauses for lit in row if abs(lit) not in (1,2,3,4)}
        self.assertTrue(first_aux)
        self.assertGreater(min(first_aux), 100)
        second, second_top = distance_clauses([-lit for lit in primary], 2, top)
        second_aux = {abs(lit) for row in second for lit in row if abs(lit) not in (1,2,3,4)}
        self.assertTrue(first_aux.isdisjoint(second_aux))
        self.assertGreater(second_top, top)
        with Cadical195(bootstrap_with=clauses) as solver:
            for bits in itertools.product((False,True), repeat=4):
                model = [i if bit else -i for i,bit in enumerate(bits,1)]
                expected = sum(a != b for a,b in zip(primary,model)) >= 2
                self.assertEqual(solver.solve(assumptions=model), expected)

    def test_original_extension_check_rejects_bad_clause(self):
        clauses = [[1],[-2,3]]
        good = validate_extension(clauses,3,[1,-2])
        self.assertTrue(good['valid'])
        self.assertEqual(good['clauses_checked'],2)
        self.assertEqual(good['full_extension_sha256'],
                         validate_extension(clauses,3,[1,-2,-3,4])['full_extension_sha256'])
        with self.assertRaises(ValueError):
            validate_extension(clauses,3,[1,2,-3])

    def test_tiny_corpus_commits_models_and_deduplicates_types(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output = self.run_generator(Path(temp),2,5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            manifest = json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['state'],'COMPLETE')
            records = list(load_models(output))
            self.assertEqual(len(records),2)
            self.assertGreaterEqual(manifest['hamming']['primary']['minimum'],1)
            supported = [r['canonicalization']['canonical_signs'] for r in records if r['canonicalization']['supported']]
            self.assertEqual(len(set(supported)),len(supported))
            for row in records:
                self.assertEqual(len(row['primary_model']),4)
                self.assertEqual(len(row['orientations'].splitlines()),4)
                self.assertTrue(row['validation']['valid'])
            self.assertEqual(sorted(p.name for p in output.iterdir()),['corpus.sqlite','manifest.json'])

    def test_deadline_terminates_child_and_leaves_readable_corpus(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output = self.run_generator(Path(temp),100,.001)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            manifest = json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['state'],'TIME_LIMIT')
            self.assertEqual(manifest['accepted_models'],len(list(load_models(output))))
            with self.assertRaises(ProcessLookupError):
                os.kill(manifest['child_pid'],0)


if __name__ == '__main__':
    unittest.main()
