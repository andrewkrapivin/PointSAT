"""Paired exact flippability benchmark on all four paper CNFs."""
import json
from pathlib import Path
import subprocess
import sys
import time
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flippable2 import FlippabilityChecker

old={}
source=subprocess.run(['git','show','HEAD:flippable2.py'],cwd=ROOT,text=True,capture_output=True,check=True).stdout
exec(compile(source,'original_flippable2.py','exec'),old)
jobs=[('mixed23','7gon-6hole-23-compact.cnf',23),('caps26','7gon-no-5-cap-no-sb-26.cnf',26),
      ('gons32','7gon-32.cnf',32),('holes29','6hole-29-compact.cnf',29)]
parser=argparse.ArgumentParser();parser.add_argument('--problem');args=parser.parse_args()
records=json.loads((ROOT/'improvements/helper_all_problems.json').read_text()) if args.problem else []
for problem,cnf,n in jobs:
    if args.problem and problem!=args.problem:continue
    records=[r for r in records if r['problem']!=problem]
    formulas=(ROOT/cnf).read_text()
    candidates=sorted((ROOT/'improvements/pipeline/fresh_corpus').glob(f'{problem}-*.model'))[:2]
    if problem=='holes29':
        candidates=sorted((ROOT/'improvements/benchmarks/late_holes29').rglob('*.model'))[:1]
        if not candidates:
            candidates=sorted((ROOT/'improvements/benchmarks/late_holes29').rglob('solver.stdout'))[:1]
    begin=time.process_time();checker=FlippabilityChecker(formulas);setup=time.process_time()-begin
    for path in candidates:
        literals={}
        for line in path.read_text().splitlines():
            if line.startswith('v '):
                for lit in map(int,line.split()[1:]):
                    if 1<=abs(lit)<=n*(n-1)*(n-2)//6:literals[abs(lit)]=lit
        if len(literals)!=n*(n-1)*(n-2)//6:raise ValueError(f'incomplete model {path}')
        model='v '+' '.join(str(literals[i]) for i in sorted(literals))+' 0'
        begin=time.process_time();reference=old['check_flippable'](formulas,model);baseline=time.process_time()-begin
        begin=time.process_time();actual=checker.check(model);optimized=time.process_time()-begin
        assert actual==reference,(problem,path)
        record={'problem':problem,'model':str(path.relative_to(ROOT)),'baseline_cpu':baseline,
                'optimized_cpu':optimized,'setup_cpu':setup,'speedup_excluding_setup':baseline/optimized,
                'flippables':len(actual[0]),'stats':checker.last_stats}
        records.append(record);print(json.dumps(record),flush=True)
    checker.close()
(ROOT/'improvements/helper_all_problems.json').write_text(json.dumps(records,indent=2)+'\n')
