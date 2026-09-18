#!/usr/bin/env python3
"""Differential tests for all-direction cap projection search."""
import itertools
import json
from pathlib import Path
import random
import subprocess
import unittest
from cap_projection import count,cross,scan
from matched import ROOT,HERE,cap_count

def points(path):
    values=list(map(int,Path(path).read_text().split()))
    return list(zip(values[1::2],values[2::2]))

class ProjectionTests(unittest.TestCase):
    def test_chain_counts(self):
        rng=random.Random(519701)
        for n in range(5,13):
            for _ in range(10):
                p=[(i,rng.randrange(-1000,1001))for i in range(n)]
                turn=[[[cross(p[i],p[j],p[k])<0 for k in range(n)]for j in range(n)]for i in range(n)]
                for size in range(3,min(n,7)+1):
                    actual=count(list(range(n)),turn,size)
                    expected=cap_count(p,size)
                    self.assertEqual(actual,expected)

    def test_known_cap_free(self):
        p=points(ROOT/'direct/seeds/es26cap5.pts')
        result=scan(p)
        self.assertEqual(result['best']['caps'],0)

    def test_bad_control_best_bruteforce(self):
        p=points(HERE/'results/kernel_v1/control-es26cap5-r0-fast.pts')
        result=json.loads((HERE/'cap_projection_control26.json').read_text())
        self.assertEqual(result['intervals_scanned'],650)
        u=result['best']['direction']
        q=[(u[0]*x+u[1]*y,-u[1]*x+u[0]*y)for x,y in p]
        self.assertEqual(cap_count(q,5),27)

    def test_dp_native_exhaustive(self):
        rng=random.Random(3317)
        for n in range(5,13):
            p=[(i,rng.randrange(-1000,1001))for i in range(n)]
            turn=[[[cross(p[i],p[j],p[k])<0 for k in range(n)]for j in range(n)]for i in range(n)]
            text=str(n)+'\n'+''.join(f'{x} {y}\n'for x,y in p)
            process=subprocess.run([str(ROOT/'direct/verify'),'--input','-','--gon','0','--hole','0','--cap','5'],
                                   input=text,text=True,capture_output=True)
            expected=json.loads(process.stdout)['convex_caps']
            self.assertEqual(count(list(range(n)),turn,5),expected)

if __name__=='__main__':unittest.main()
