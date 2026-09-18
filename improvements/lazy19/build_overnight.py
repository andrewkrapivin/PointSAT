"""Freeze the proof-filtered producer and combine its one-core consumer queue."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]

def main():
    out=ROOT/'improvements/lazy19/overnight';frozen=out/'frozen'
    if (out/'jobs.json').exists():raise FileExistsError('queue already frozen')
    paths=['sat_orient_conversion.py','improvements/lazy19/search.py','improvements/lazy19/audit',
           'improvements/realizability/bfp.py','improvements/benchmarks/verify_bfp.py']
    checksums={}
    for relative in paths:
        source=ROOT/relative;target=frozen/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target);checksums[relative]=hashlib.sha256(target.read_bytes()).hexdigest()
    proofs=[ROOT/'improvements/realizability/results/supplied19-rational.json',
            ROOT/'improvements/realizability/results/relaxed002.json']
    for checked in sorted((ROOT/'improvements/lazy19/results/bfp19691/bfp').glob('*.checked.json')):
        path=checked.with_name(checked.name.replace('.checked.json','.proof.json'))
        if json.loads(checked.read_text()).get('verified') and path.exists():proofs.append(path)
    command=[str(ROOT/'direct/vendor/venv/bin/python'),str(frozen/'improvements/lazy19/search.py'),
             '--known',str(ROOT/'improvements/symmetry19/decoded/center19-adjacent.or'),
             '--phase-real',str(ROOT/'improvements/symmetry19/search/model002-relaxed-symmetric/points.real'),
             '--output',str(out/'corpus'),'--audit',str(frozen/'improvements/lazy19/audit'),
             '--seconds','30000','--samples','10000','--distance-limit','60','--seed','625191',
             '--bfp-seconds','30','--bfp-script',str(frozen/'improvements/realizability/bfp.py'),
             '--proof-verifier',str(frozen/'improvements/benchmarks/verify_bfp.py')]
    for proof in proofs:command+=['--proof',str(proof)]
    jobs=[{'label':'lazy19-proof-filtered-producer','workers':1,'max_seconds':30000,
           'output':str(out/'corpus'),'command':command}]
    jobs+=json.loads((ROOT/'improvements/benchmarks/lazy19_consumer_job.json').read_text())
    (out/'jobs.json').write_text(json.dumps(jobs,indent=2)+'\n')
    (out/'freeze.json').write_text(json.dumps({'source_sha256':checksums,'initial_proofs':[str(p) for p in proofs],
            'deadline_utc':'2026-09-05T14:00:00+00:00','classification':'exploratory proof-filtered producer/consumer; not paired benchmark'},indent=2)+'\n')
    print(json.dumps({'jobs':str(out/'jobs.json'),'initial_proofs':len(proofs),'workers':2}))

if __name__=='__main__':main()
