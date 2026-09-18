"""Create exact integer certificates and audit native 19-point incumbents."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sat_orient_conversion import integer_points


def audit(path):
    path=Path(path);points=integer_points(path)
    origin=points[0];points=[(x-origin[0],y-origin[1]) for x,y in points]
    scale=math.gcd(*(abs(v) for point in points for v in point)) or 1
    target=path.with_suffix('.exact.pts')
    target.write_text(str(len(points))+'\n'+''.join(f'{x//scale} {y//scale}\n' for x,y in points))
    result=subprocess.run(['improvements/symmetry19/verify_hexagons',str(target)],text=True,capture_output=True,check=False)
    if result.returncode not in (0,1):raise RuntimeError(result.stderr)
    record=dict(json.loads(result.stdout),input=str(path),certificate=str(target))
    path.with_suffix('.verification.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('files',nargs='+');args=parser.parse_args()
    for path in args.files:print(json.dumps(audit(path)),flush=True)
