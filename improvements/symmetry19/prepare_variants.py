"""Build SAT-derived C3 orientation variants with exact flippability screening."""
import argparse
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from flippable2 import FlippabilityChecker
from decode_symmetry import expand


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cnf',default='convex_hexagon_inside_19_3sym.cnf')
    parser.add_argument('--model',default='improvements/symmetry19/input_sat.out')
    parser.add_argument('--output',default='improvements/symmetry19/variants')
    parser.add_argument('--samples',type=int,default=8)
    args=parser.parse_args()
    folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    original={abs(v):v for line in Path(args.model).read_text().splitlines() if line.startswith('v ')
              for v in map(int,line.split()[1:]) if v}
    mapping,cycles,count=expand({i:i for i in range(1,328)},19,18,'adjacent')
    (folder/'mapping.json').write_text(json.dumps({'n':19,'primary_variables':327,
        'entries':[{'triple':[v+1 for v in t],'literal':v} for t,v in mapping.items()],
        'cycles':[[v+1 for v in c] for c in cycles],'center':19},indent=2)+'\n')
    begin=time.perf_counter()
    checker=FlippabilityChecker(Path(args.cnf).read_text())
    checker.solver.set_phases(list(original.values()))
    print(json.dumps({'event':'initialized','seconds':time.perf_counter()-begin}),flush=True)
    primary=[original[i] for i in range(1,328)]
    rng=random.Random(19005)
    seen=set()
    for number in range(args.samples):
        begin=time.perf_counter()
        flips,_=checker.check('v '+' '.join(map(str,primary))+' 0')
        truth={abs(v):1 if v>0 else -1 for v in primary}
        prefix=folder/f'model{number:03d}'
        for partial in (False,True):
            suffix='-relaxed.or' if partial else '.or'
            prefix.with_name(prefix.name+suffix).write_text(''.join(
                f"{'A' if (1 if variable>0 else -1)*truth[abs(variable)]>0 else 'B'}_{triple}\n"
                for triple0,variable in mapping.items()
                for triple in [tuple(v+1 for v in triple0)]
                if not partial or abs(variable) not in flips))
        info={'sample':number,'primary_model':primary,'flippables':sorted(flips),
              'stats':checker.last_stats,'seconds':time.perf_counter()-begin,
              'hamming_from_input':sum(v!=original[abs(v)] for v in primary)}
        prefix.with_suffix('.json').write_text(json.dumps(info,indent=2)+'\n')
        print(json.dumps(info),flush=True)
        seen.add(tuple(primary))
        if number+1==args.samples:break
        # A short random walk in SAT space gives nearby alternative order types.
        # Flipping an individually flippable primary variable is already proved
        # SAT; recompute flippability after every step, not after simultaneous flips.
        options=list(flips);rng.shuffle(options)
        moved=False
        for variable in options:
            candidate=[-v if abs(v)==variable else v for v in primary]
            if tuple(candidate) not in seen:
                primary=candidate;moved=True;break
        if not moved:
            checker.solver.add_clause([-v for v in primary])
            checker.solver.set_phases([v if rng.random()<0.8 else -v for v in primary])
            if not checker.solver.solve():break
            model={abs(v):v for v in checker.solver.get_model()}
            primary=[model[i] for i in range(1,328)]
    checker.close()


if __name__=='__main__':main()
