#!/usr/bin/env python3
"""Differential exact algebraic C3 versus independent rational hexagon audit."""
import decimal
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from matched import ROOT,HERE

CYCLES=ROOT/'improvements/symmetry19/decoded/center19-adjacent.cycles'

def run(points,lattice=False):
    out=subprocess.run([str(HERE/'verify_c3'),'--input',str(points),'--cycles',str(CYCLES)]+(['--lattice'] if lattice else []),text=True,capture_output=True)
    if out.returncode not in (0,1):raise RuntimeError(out.stderr)
    return json.loads(out.stdout)

class C3Tests(unittest.TestCase):
    def test_integer_lattice_embedding(self):
        rng=random.Random(260905)
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            path=Path(tmp)/'points.pts'
            for trial in range(20):
                points=[]
                for _ in range(6):
                    a,b=rng.randrange(-10000,10001),rng.randrange(-10000,10001)
                    points.extend([(a,b),(-b,a-b),(b-a,-a)])
                points.append((0,0))
                path.write_text('19\n'+''.join(f'{x} {y}\n' for x,y in points))
                got=run(path,lattice=True)
                other=subprocess.run([str(ROOT/'improvements/symmetry19/verify_hexagons'),str(path)],text=True,capture_output=True)
                self.assertIn(other.returncode,(0,1));expected=json.loads(other.stdout)
                self.assertEqual(got['orientation_changes_from_rounded_input'],0)
                self.assertEqual(got['interior_histogram'],expected['interior_histogram'])
                self.assertEqual(got['collinear_triples'],expected['collinear_triples'])

    def test_existing_symmetric_candidates(self):
        for metadata in (ROOT/'improvements/symmetry19/search').glob('*-symmetric/result.json'):
            expected=json.loads(metadata.read_text())
            points=metadata.parent/'points.pts'
            if not points.exists():continue
            got=run(points)
            self.assertEqual(got['orientation_changes_from_rounded_input'],0)
            self.assertEqual(got['interior_histogram'],expected['verification']['interior_histogram'])
            self.assertEqual(got['collinear_triples'],expected['verification']['collinear_triples'])

    def test_independent_bigint_hexagon_validator(self):
        rng=random.Random(625719)
        with decimal.localcontext() as context,tempfile.TemporaryDirectory(dir=HERE) as tmp:
            context.prec=100;D=decimal.Decimal;sqrt3=D(3).sqrt();scale=D(10)**70
            path=Path(tmp)/'points.pts'
            for trial in range(10):
                points=[]
                for _ in range(6):
                    a,b=D(rng.randrange(-1000,1001)),D(rng.randrange(-1000,1001))
                    points.extend([(a,b),((-a-b*sqrt3)/2,(-b+a*sqrt3)/2),((-a+b*sqrt3)/2,(-b-a*sqrt3)/2)])
                points.append((D(0),D(0)))
                integers=[(int((x*scale).to_integral_value()),int((y*scale).to_integral_value()))for x,y in points]
                path.write_text('19\n'+''.join(f'{x} {y}\n'for x,y in integers))
                algebraic=run(path)
                other=subprocess.run([str(ROOT/'improvements/symmetry19/verify_hexagons'),str(path)],text=True,capture_output=True)
                self.assertIn(other.returncode,(0,1));rational=json.loads(other.stdout)
                self.assertEqual(algebraic['orientation_changes_from_rounded_input'],0)
                self.assertEqual(algebraic['interior_histogram'],rational['interior_histogram'])
                self.assertEqual(algebraic['collinear_triples'],rational['collinear_triples'])

if __name__=='__main__':unittest.main()
