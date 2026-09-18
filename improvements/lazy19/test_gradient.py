"""Native gradient verification and a nontrivial convex feasibility repair."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sat_orient_conversion import get_orientations,inspect_realization
from search import point_cube


def main():
    binary=ROOT/'improvements/lazy19/gradient'
    test=subprocess.run([str(binary),'--self-test'],capture_output=True,text=True,check=True)
    output=Path(tempfile.mkdtemp(prefix='pointsat-gradient-test-'))
    target=[(0,0),(4,0),(0,4),(1,1)]
    warm=[(0,0),(4,0),(0,4),(3,3)]
    orient=output/'target.or';orient.write_text(get_orientations(point_cube(target),4))
    source=output/'warm.real';source.write_text(''.join(f'{i} {x} {y}\n' for i,(x,y) in enumerate(warm,1)))
    assert len(inspect_realization(orient,source,4)['bad_vars'])==1
    result=output/'result.real'
    run=subprocess.run([str(binary),str(orient),str(source),str(result),'1','421','0.00001'],capture_output=True,text=True,check=True)
    report=inspect_realization(orient,result,4)
    assert report['valid'],(run.stdout,report)
    print(json.dumps({'passed':True,'gradient':json.loads(test.stdout),'four_point_repair_exact':report['valid'],
                      'artifacts':str(output),'native':run.stdout}))


if __name__=='__main__':main()
