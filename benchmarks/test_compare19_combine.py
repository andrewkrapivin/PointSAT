"""Synthetic four-point fixtures only: no19-point/native searches."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib

from benchmarks.compare19_combine import (ROOT, canonical_key, exclusion,
                                         primary_projection)
from benchmarks.compare19_inputs import (SCHEMA, connect, digest_file, load_models,
                                        meta)
from benchmarks.compare19_types import canonicalize
from improvements.pipeline.orientation_map import OrientationMap


class CombineTests(unittest.TestCase):
    def test_projection_requires_original_complete_assignment(self):
        self.assertEqual(primary_projection('v 1 -2 3 9 0', [1, 2, 3]), [1, -2, 3])
        for bad in ('v 1 -2 0', 'v 1 1 -2 3 0', 'v 1 -1 -2 3 0'):
            with self.assertRaises(ValueError):
                primary_projection(bad, [1, 2, 3])

    def test_control_canonical_and_distance_exclusions_are_separate(self):
        canonical = dict(supported=True, n=4, canonical_signs='0000')
        key = canonical_key(canonical)
        selected = [dict(primary_model=[1, 2, 3, 4])]
        self.assertEqual(exclusion([1, 2, 3, 4], canonical, [], set(), key, 2)[0],
                         'KNOWN_POSITIVE_CONTROL')
        self.assertEqual(exclusion([-1, -2, -3, -4], canonical, selected, {key}, None, 2)[0],
                         'CANONICAL_DUPLICATE')
        self.assertEqual(exclusion([-1, 2, 3, 4], canonical, selected, set(), None, 2),
                         ('MINIMUM_DISTANCE', 1))
        self.assertEqual(exclusion([-1, -2, 3, 4], canonical, selected, set(), None, 2), (None, 2))

    def fixture(self, root, invalid=False, active=False):
        cnf, mapping = root/'tiny.cnf', root/'map.json'
        cnf.write_text('p cnf 4 4\n1 0\n2 -2 0\n3 -3 0\n4 -4 0\n')
        mapping.write_text(json.dumps(dict(n=4, primary_variables=4, entries=[
            dict(triple=list(t), literal=i) for i, t in enumerate(itertools.combinations(range(1, 5), 3), 1)])))
        adapter = OrientationMap(mapping, 4)
        primary = [-1, 2, 3, 4] if invalid else [1, 2, 3, 4]
        orientations = adapter.orientations(primary)
        canonical = canonicalize(orientations)
        control = root/'control.or'
        for signs in itertools.product((-1, 1), repeat=4):
            candidate = adapter.orientations([i*s for i, s in enumerate(signs, 1)])
            canon = canonicalize(candidate)
            if canon['supported'] and canonical_key(canon) != canonical_key(canonical):
                control.write_text(candidate)
                break
        else:
            self.fail('Fixture needs a different supported control type')
        fresh = root/'fresh'
        fresh.mkdir()
        db = connect(fresh/'corpus.sqlite')
        db.executescript(SCHEMA)
        registration = dict(cnf_sha256=digest_file(cnf), orientation_map_sha256=digest_file(mapping), seed=42)
        state = 'GENERATING' if active else 'TIME_LIMIT'
        primary_bytes = json.dumps(primary, separators=(',', ':')).encode()
        with db:
            meta(db, 'registration', registration)
            meta(db, 'state', state)
            db.execute('INSERT INTO models VALUES(?,?,?,?,?,?,?,?)', (
                1, zlib.compress(primary_bytes), zlib.compress(orientations.encode()),
                hashlib.sha256(primary_bytes).hexdigest(), hashlib.sha256(orientations.encode()).hexdigest(),
                json.dumps(dict(valid=True)), json.dumps(dict(solve_cpu_seconds=.5)), json.dumps(canonical)))
        db.close()
        (fresh/'manifest.json').write_text(json.dumps(dict(registration=registration, state=state,
            accepted_models=1, generation_child_cpu_seconds=1.25, generation_wall_seconds=2.5)))
        historical = root/'historical'
        historical.mkdir()
        (historical/'settings.json').write_text(json.dumps(dict(base_file=str(cnf))))
        log = historical/'raw_results.jsonl'
        log.write_text('\n'.join(json.dumps(row) for row in [
            dict(type='Feedback', original_solution='v -1 -2 -3 -4 0', satisfiable=True),
            dict(type='SAT', solution='v 1 2 3 4 0', satisfiable=True),
            dict(type='SAT', id=2, original_solution='v 1 2 3 4 0', satisfiable=True)])+'\n')
        return cnf, mapping, control, fresh, log

    def run_combine(self, root, invalid=False, active=False, seconds=5):
        cnf, mapping, control, fresh, log = self.fixture(root, invalid, active)
        before = {str(p): digest_file(p) for p in fresh.iterdir() if p.is_file()}
        out = root/'combined'
        result = subprocess.run([sys.executable, str(ROOT/'benchmarks/compare19_combine.py'),
            '--fresh-corpus', str(fresh), '--output', str(out), '--count', '1', '--min-distance', '1',
            '--seconds', str(seconds), '--cnf', str(cnf), '--orientation-map', str(mapping),
            '--control-orientation', str(control), '--historical-log', str(log)],
            text=True, capture_output=True, timeout=12)
        for path, digest in before.items():
            self.assertEqual(digest_file(path), digest, 'Builder changed the source corpus')
        return result, out

    def test_complete_original_validation_same_loader_provenance_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output = self.run_combine(Path(temp))
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            rows = list(load_models(output))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['generation']['origin']['stratum'], 'fresh')
            self.assertTrue(rows[0]['validation']['valid'])
            self.assertEqual(rows[0]['validation']['clauses_checked'], 4)
            summary = json.loads((output/'manifest.json').read_text())
            self.assertEqual(summary['generation_child_cpu_seconds'], 1.25)
            self.assertGreater(summary['combine_validation_child_cpu_seconds'], 0)
            self.assertEqual(summary['exclusion_counts']['NOT_SAT_OR_NO_ORIGINAL_SOLUTION'], 1)
            self.assertEqual(summary['exclusion_counts']['TARGET_COUNT_FILLED'], 1)
            self.assertEqual(len(summary['registration']['candidates']), 2, 'Feedback must never be a candidate')
            self.assertEqual(sorted(p.name for p in output.iterdir()), ['corpus.sqlite', 'manifest.json'])

    def test_invalid_source_is_error_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output = self.run_combine(Path(temp), invalid=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads((output/'manifest.json').read_text())['state'], 'ERROR')
            self.assertEqual(list(load_models(output)), [])

    def test_historical_original_sat_selected_when_fresh_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cnf, mapping, control, fresh, log = self.fixture(root)
            with sqlite3.connect(fresh/'corpus.sqlite') as db:
                db.execute('DELETE FROM models')
            manifest = json.loads((fresh/'manifest.json').read_text())
            manifest['accepted_models'] = 0
            (fresh/'manifest.json').write_text(json.dumps(manifest))
            out = root/'combined'
            command = [sys.executable, str(ROOT/'benchmarks/compare19_combine.py'),
                '--fresh-corpus', str(fresh), '--output', str(out), '--count', '1', '--min-distance', '1',
                '--seconds', '5', '--cnf', str(cnf), '--orientation-map', str(mapping),
                '--control-orientation', str(control), '--historical-log', str(log)]
            result = subprocess.run(command, text=True, capture_output=True, timeout=12)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            row, = list(load_models(out))
            self.assertEqual(row['generation']['origin']['stratum'], 'historical_initial_sat')
            self.assertEqual(row['generation']['origin']['line'], 3)
            self.assertEqual(row['primary_model'], [1, 2, 3, 4])
            before = digest_file(out/'corpus.sqlite')
            repeated = subprocess.run(command, text=True, capture_output=True, timeout=12)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(digest_file(out/'corpus.sqlite'), before)

    def test_active_fresh_source_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output = self.run_combine(Path(temp), active=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('terminal SQLite state', result.stderr)
            self.assertFalse(output.exists())

    def test_outer_deadline_reaps_child_and_preserves_readable_database(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output = self.run_combine(Path(temp), seconds=.001)
            self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
            manifest = json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['state'], 'TIME_LIMIT')
            self.assertEqual(manifest['accepted_models'], len(list(load_models(output))))
            with self.assertRaises(ProcessLookupError):
                os.kill(manifest['child_pid'], 0)


if __name__ == '__main__':
    unittest.main()
