#!/usr/bin/env python3
"""Bounded functional tests for warm starts, budgets, bad input and safe signals."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
def run_tests(binary):
    for flag in ['--help','-h']:
        helped=subprocess.run([str(binary),flag],text=True,capture_output=True,timeout=5)
        assert helped.returncode==0 and 'Usage:' in helped.stderr
    with tempfile.TemporaryDirectory(prefix='localizer-cli-') as temp:
        base=Path(temp)
        orient=base/'three.or'; orient.write_text('A_(1, 2, 3)\n')
        warm=base/'three.real'; warm.write_text('1 0 0\n2 1 0\n3 0 1\n')
        output=base/'output.real'
        def call(args, expected=0):
            p=subprocess.run([str(binary),str(orient),'-q','-o',str(output),*args],
                             text=True,capture_output=True,timeout=5)
            assert p.returncode==expected,(args,p.returncode,p.stdout,p.stderr)
            return p
        p=call(['-w',str(warm),'-I','1'])
        assert 'SOLVED\nViolations: 0' in p.stdout
        assert output.read_text()==warm.read_text()
        stats=json.loads(p.stdout.splitlines()[-1]); assert stats['iterations']==0
        call(['-w',str(warm),'--ordered-x','-I','1'],1)
        p=call(['--ordered-x','-I','200'])
        xs=[float(line.split()[1]) for line in output.read_text().splitlines()]
        assert all(a<b for a,b in zip(xs,xs[1:]))
        archive=base/'archive'
        p=call(['-w',str(warm),'-I','1','--archive-prefix',str(archive)])
        files=sorted(base.glob('archive-*.real'))
        assert 1<=len(files)<=10
        assert all(f.read_text()==warm.read_text() for f in files)
        for args in [['-r','0'],['-r','1'],['-i','0'],['-t','0'],['-T','nan'],['-I','0']]:
            call(args,1)
        for malformed in ['A_(1,1,3)\n','A_(0,2,3)\n','D_(1,2,3)\n','A_(1,2,82)\n',
                          'A_(1,2,3) extra\n','A_(1,2,3\n','']:
            orient.write_text(malformed); call(['-I','1'],1)
        orient.write_text('A_(1,2,3)\n')
        for malformed in ['1 0 0\n2 1 0\n','1 0 0\n1 1 0\n3 0 1\n',
                          '1 nan 0\n2 1 0\n3 0 1\n']:
            warm.write_text(malformed); call(['-w',str(warm),'-I','1'],1)
        fixed=base/'fixed'; fixed.write_text('1:nan,0\n')
        call(['-f',str(fixed),'-I','1'],1)
        cycles=base/'cycles'; cycles.write_text('1 2 2\n')
        call(['-c',str(cycles),'-I','1'],1)
        cycles.write_text('1 2 4\n'); call(['-c',str(cycles),'-I','1'],1)
        fixed.write_text('1:0,0\n2:1,0\n3:0,1\n')
        p=call(['-f',str(fixed),'-d','2','-T','0.01'])
        assert 'STOPPED\nViolations: 1' in p.stdout
        p=call(['-f',str(fixed),'-d','0.5','-I','1'])
        assert 'SOLVED\nViolations: 0' in p.stdout
        cycles.write_text('1 2 3\n')
        fixed.write_text('2:1,0\n')
        p=call(['-f',str(fixed),'-c',str(cycles),'-I','1'])
        assert 'SOLVED\nViolations: 0' in p.stdout
        point2=list(map(float,output.read_text().splitlines()[1].split()[1:]))
        assert abs(point2[0]-1)<1e-12 and abs(point2[1])<1e-12
        fixed.write_text('1:1,0\n2:1,0\n')
        call(['-f',str(fixed),'-c',str(cycles),'-I','1'],1)
        call(['-f',str(fixed),'--ordered-x','-I','1'],1)
        call(['-c',str(cycles),'--ordered-x','-I','1'],1)
        # An inconsistent A/B pair cannot solve, making stop tests deterministic.
        orient.write_text('A_(1,2,3)\nB_(1,2,3)\n')
        p=call(['--ordered-x','-I','500','-r','2','--pair-every','2','--line-every','2','--check-every','1'])
        xs=[float(line.split()[1]) for line in output.read_text().splitlines()]
        assert all(a<b for a,b in zip(xs,xs[1:]))
        p=call(['-T','0.05','-t','2'])
        assert 'STOPPED\nViolations: 1' in p.stdout
        assert len(output.read_text().splitlines())==3
        for sig in [signal.SIGINT,signal.SIGTERM]:
            process=subprocess.Popen([str(binary),str(orient),'-q','-t','2','-o',str(output)],
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            time.sleep(0.05)
            process.send_signal(sig)
            stdout,stderr=process.communicate(timeout=3)
            assert process.returncode==0,(sig,stdout,stderr)
            assert 'Violations: 1' in stdout
            assert len(output.read_text().splitlines())==3
    print('CLI validation, zero-iteration warm start, two-thread budgets and SIGINT/SIGTERM passed.')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=Path,default=ROOT/'build/localizer')
    run_tests(p.parse_args().binary.resolve())
