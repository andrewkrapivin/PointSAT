#!/usr/bin/env python3
"""Independent property, order-type, CLI and bounded-shutdown tests."""
from itertools import combinations
import argparse
import json
import random
from pathlib import Path
import signal
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'optimizer/compact'
PAPER=ROOT/'direct/seeds/paper23.pts'
def points(path):
    a=list(map(int,path.read_text().split()));assert len(a)==1+2*a[0]
    return list(zip(a[1::2],a[2::2]))
def signs(p):
    return [((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])>0) for a,b,c in combinations(p,3)]
def audit(path):
    r=subprocess.run([str(ROOT/'direct/verify'),'--input',str(path)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr+r.stdout
    return json.loads(r.stdout)
def main():
    global BINARY
    parser=argparse.ArgumentParser();parser.add_argument('--binary',type=Path,default=BINARY);parser.add_argument('--experimental',action='store_true');options=parser.parse_args();BINARY=options.binary.resolve()
    cases=0
    with tempfile.TemporaryDirectory(prefix='pointsat-optimizer-tests-') as folder:
        folder=Path(folder);out=folder/'result.pts'
        for mode in ([],['--preserve-order-type'],['--preserve-layers']):
            r=subprocess.run([str(BINARY),'--input',str(PAPER),'--output',str(out),'--seconds','2','--iterations','10000',*mode],capture_output=True,text=True,timeout=4)
            assert r.returncode==0,r.stderr
            report=json.loads(r.stdout.splitlines()[-1]);v=audit(out)
            assert report['area']==v['bbox_area'] and report['layers']==v['hull_layers']
            if '--preserve-order-type' in mode:assert signs(points(PAPER))==signs(points(out))
            if mode:assert report['input_layers']==report['layers']
            cases+=1
        r=subprocess.run([str(BINARY),'--input',str(PAPER),'--output',str(out),'--seconds','0'],capture_output=True,text=True)
        assert r.returncode==0 and signs(points(PAPER))==signs(points(out));cases+=1
        invalid=['3\n0 0\n1 1\n2 2\n','3\n0 0\n1 0\n0 1000000000001\n','3\n0 0\n1 0\n0 1\ntrailing\n','3\n0 0\n1 0\n']
        for i,data in enumerate(invalid):
            path=folder/f'invalid{i}.pts';path.write_text(data)
            r=subprocess.run([str(BINARY),'--input',str(path),'--output',str(out),'--seconds','0'],capture_output=True,text=True)
            assert r.returncode==2,(data,r.stdout,r.stderr);cases+=1
        bad_options=[['--seconds','nan'],['--seconds','-1'],['--family','unknown']]
        if options.experimental:bad_options += [['--seconds','1junk'],['--seed','-1'],['--iterations','-1'],['--target-width','64'],['--preserve-order-type','--geometry-repair']]
        for args in bad_options:
            r=subprocess.run([str(BINARY),'--input',str(PAPER),'--output',str(out),*args],capture_output=True,text=True)
            assert r.returncode==2,r.stdout+r.stderr;cases+=1
        # Complete counting, not just Boolean agreement, with an exhaustive
        # independent subset/hull oracle on unrelated random configurations.
        rng=random.Random(92061)
        for trial in range(30):
            n=rng.randrange(6,13)
            while True:
                q=[(rng.randrange(-1000000,1000000),rng.randrange(-1000000,1000000)) for _ in range(n)]
                if all((b[0]-a[0])*(c[1]-a[1])!=(b[1]-a[1])*(c[0]-a[0]) for a,b,c in combinations(q,3)):break
            path=folder/'random.pts';path.write_text(str(n)+'\n'+''.join(f'{x} {y}\n' for x,y in q))
            for family,g,h,c in (('mixed23',7,6,0),('holes29',0,6,0),('gons32',7,0,0),('caps26',7,0,5)):
                r=subprocess.run([str(BINARY),'--input',str(path),'--family',family,'--check'],capture_output=True,text=True)
                actual=json.loads(r.stdout)
                r=subprocess.run([str(ROOT/'direct/verify'),'--input',str(path),'--gon',str(g),'--hole',str(h),'--cap',str(c)],capture_output=True,text=True)
                expected=json.loads(r.stdout)
                assert (actual['gons'],actual['holes'],actual['caps'],actual['valid'],actual['layers'])==(expected['convex_gons'],expected['empty_holes'],expected['convex_caps'],expected['valid'],expected['hull_layers'])
                cases+=1
        # No wrapper cancellation: signal and reap the actual native process.
        for sig in (signal.SIGINT,signal.SIGTERM):
            p=subprocess.Popen([str(BINARY),'--input',str(PAPER),'--output',str(out),'--seconds','30'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            first=p.stdout.readline();assert json.loads(first)['event']=='start'
            p.send_signal(sig);stdout,stderr=p.communicate(timeout=3)
            assert p.returncode==0 and json.loads(stdout.splitlines()[-1])['event']=='final',stderr
            audit(out);cases+=1
    print(json.dumps({'passed':True,'cases':cases,'binary':str(BINARY),'experimental':options.experimental}))
if __name__=='__main__':main()
