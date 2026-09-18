#!/usr/bin/env python3
"""Independent exact-decimal and cap regression tests for matched.py."""
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from matched import ROOT, audit, cap_count, constraints, integer_points, index_order_projection, cross

class AuditTests(unittest.TestCase):
    def test_decimal_not_float(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'improvements/benchmarks') as tmp:
            p=Path(tmp)/'p.real'
            p.write_text('1 0 0\n2 10000000000000000 10000000000000000\n3 10000000000000000 10000000000000001\n')
            self.assertEqual(integer_points(p)[2][1],10000000000000001)

    def test_complete_audit(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'improvements/benchmarks') as tmp:
            p=Path(tmp)/'p.real'; o=Path(tmp)/'p.or'
            p.write_text('1 0 0\n2 1.25 0\n3 0 0.1\n')
            o.write_text('A_(1, 2, 3)\n')
            r=audit(p,o,{'n':3,'gon':0,'hole':0})
            self.assertEqual(r['orientation_violations'],0)
            self.assertTrue(r['geometry']['valid'])
            o.write_text('B_(1, 2, 3)\n')
            self.assertEqual(audit(p,o,{'n':3})['orientation_violations'],1)
            p.write_text('1 0 0\n2 1 0\n3 2 0\n');o.write_text('C_(1, 2, 3)\n')
            r=audit(p,o,{'n':3})
            self.assertEqual(r['orientation_violations'],0)
            self.assertFalse(r['geometry']['valid'])

    def test_cap_differential(self):
        rng=random.Random(1597)
        for n in range(5,11):
            for _ in range(5):
                p=[(rng.randrange(-8,9),rng.randrange(-8,9)) for _ in range(n)]
                text=str(n)+'\n'+''.join(f'{x} {y}\n' for x,y in p)
                r=subprocess.run([str(ROOT/'direct/verify'),'--input','-','--gon','0','--hole','0','--cap','5'],input=text,text=True,capture_output=True)
                self.assertEqual(cap_count(p,5),json.loads(r.stdout)['convex_caps'])

    def test_bad_constraints(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'improvements/benchmarks') as tmp:
            p=Path(tmp)/'p.or'
            for text in ['', 'D_(1, 2, 3)', 'A_(1, 1, 3)', 'A_(0, 2, 3)','A_(1,2,3) extra']:
                p.write_text(text)
                with self.assertRaises(ValueError): constraints(p)

    def test_index_order_projection(self):
        p=[(0,0),(0,1),(0,2)]
        out,direction=index_order_projection(p)
        self.assertTrue(all(a[0]<b[0] for a,b in zip(out,out[1:])))
        self.assertIsNone(index_order_projection([(0,0),(1,0),(0,1),(0,0)])[0])
        rng=random.Random(896)
        for _ in range(100):
            p=[(i,rng.randrange(-100,100)) for i in range(10)]
            q=[(-2*x+3*y,-5*x+7*y) for x,y in p]  # determinant +1
            out,_=index_order_projection(q)
            self.assertIsNotNone(out)
            for a,b,c in __import__('itertools').combinations(range(10),3):
                d=cross(q[a],q[b],q[c]); e=cross(out[a],out[b],out[c])
                self.assertEqual((d>0)-(d<0),(e>0)-(e<0))

if __name__=='__main__': unittest.main()
