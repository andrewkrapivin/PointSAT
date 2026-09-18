#!/usr/bin/env python3
"""Compare independent integer verifiers across affine maps beyond128bits."""
import json
from pathlib import Path
import random
import subprocess

root=Path(__file__).parent
rng=random.Random(99123)
fixtures=[[(i,i*i) for i in range(8)],[(0,0),(8,0),(8,8),(0,8),(3,4)]]
fixtures.extend([[(rng.randrange(100),rng.randrange(100)) for _ in range(10)] for _ in range(8)])
comparisons=0
for points in fixtures:
    for gon,hole in [(4,4),(7,6)]:
        def call(program,pts):
            text=str(len(pts))+"\n"+"".join(f"{x} {y}\n" for x,y in pts)
            result=subprocess.run([str(root/program),"--input","-","--gon",str(gon),"--hole",str(hole)],input=text,text=True,capture_output=True)
            assert result.returncode in (0,1),result.stderr
            return json.loads(result.stdout)
        reference=call("verify",points)
        scale=10**75+39
        transformed=[(scale*(2*x+3*y)+10**90,scale*(x+y)-10**100) for x,y in points]
        actual=call("verify_big",transformed)
        for key in ["valid","convex_gons","empty_holes","collinear_triples"]:
            assert reference[key]==actual[key],(key,reference,actual)
        comparisons+=1
print(json.dumps(dict(arbitrary_precision_affine_comparisons=comparisons,passed=True)))
