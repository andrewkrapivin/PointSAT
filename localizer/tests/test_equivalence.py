#!/usr/bin/env python3
"""Short single-thread counter/coordinate equivalence checks against frozen v6."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    binaries = ['localizer_v6','localizer','localizer_sampling','localizer_atomic','localizer_both']
    with tempfile.TemporaryDirectory(prefix='localizer-equivalence-') as directory:
        folder = Path(directory)
        variants = [([], 'plain'), (['--line-every','7'], 'line'),
                    (['--pair-every','3','--line-every','7'], 'pair-line'),
                    (['-d','0.001'], 'distance')]
        comparisons = 0
        for family in ('mixed23','holes29','gons32','caps26'):
            for extra,label in variants:
                expected = None
                for binary in binaries:
                    output = folder/f'{family}-{label}-{binary}.real'
                    command = [str(ROOT/'build'/binary),str(ROOT/'benchmarks/inputs'/f'{family}.or'),
                               '-I','1000','-r','37','-s','117','-t','1','-q','--check-every','1',
                               '-o',str(output),*extra]
                    if family=='caps26': command.append('--ordered-x')
                    process = subprocess.run(command,text=True,capture_output=True,timeout=15)
                    assert process.returncode==0,(command,process.stderr)
                    stats = [json.loads(row) for row in process.stdout.splitlines() if row.startswith('{')][-1]
                    stats.pop('seconds')
                    actual = output.read_bytes(),stats
                    if expected is None: expected=actual
                    else: assert actual==expected,(family,label,binary); comparisons+=1
        # A bounded inconsistent target exercises complete threefold orbits.
        target=folder/'symmetric.or';target.write_text('A_(1,2,3)\nB_(1,2,3)\n')
        cycles=folder/'cycles';cycles.write_text('1 2 3\n')
        expected=None
        for binary in binaries:
            output=folder/f'symmetric-{binary}.real'
            command=[str(ROOT/'build'/binary),str(target),'-c',str(cycles),'-I','1000','-r','37',
                     '-s','11','-q','--line-every','7','--check-every','1','-o',str(output)]
            process=subprocess.run(command,text=True,capture_output=True,timeout=15)
            assert process.returncode==0,process.stderr
            stats=[json.loads(row)for row in process.stdout.splitlines()if row.startswith('{')][-1];stats.pop('seconds')
            actual=output.read_bytes(),stats
            if expected is None:expected=actual
            else:assert actual==expected,binary;comparisons+=1
    print(f'{comparisons} coordinate/counter pairs match v6 across four families, resets, line/pair moves, distance penalties, and symmetry.')


if __name__=='__main__':main()
