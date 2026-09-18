#!/usr/bin/env python3
"""Independent, paired Localizer wall-budget benchmark and exact output audit.

All search runs use the native binary; Python only schedules and audits jobs.
The old binary has uninitialized optional filename buffers, so BOTH versions
receive explicit empty -f/-c arguments. No warm coordinate seed is supplied.
"""
import argparse
import concurrent.futures
import hashlib
import itertools
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import random
import resource
import shutil
import signal
import statistics
import subprocess
import time
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
_STOP = None

def initialize_worker(stop):
    global _STOP
    _STOP=stop
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def constraints(path):
    out = []
    for line in Path(path).read_text().splitlines():
        m = re.fullmatch(r'([ABC])_\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)', line.strip())
        if not m:
            raise ValueError('Malformed orientation constraint: ' + line)
        a, b, c = map(int, m.groups()[1:])
        if min(a,b,c) < 1 or len({a,b,c}) != 3:
            raise ValueError('Invalid orientation indices')
        out.append((a-1,b-1,c-1,{'A':1,'B':-1,'C':0}[m[1]]))
    if not out:
        raise ValueError('Empty orientation file')
    return out

def integer_points(path):
    """Treat output decimal tokens exactly, without a binary-float roundtrip."""
    rows = [line.split() for line in Path(path).read_text().splitlines() if line.strip()]
    if any(len(row) != 3 or int(row[0]) != i+1 for i,row in enumerate(rows)):
        raise ValueError('Point indices are not contiguous 1..n')
    q = [(Fraction(row[1]), Fraction(row[2])) for row in rows]
    scale = math.lcm(*(v.denominator for p in q for v in p))
    p = [(int(x*scale), int(y*scale)) for x,y in q]
    ox,oy = p[0]
    p = [(x-ox,y-oy) for x,y in p]
    common = math.gcd(*(abs(v) for point in p for v in point)) or 1
    return [(x//common,y//common) for x,y in p]

def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

def cap_count(points,k):
    if not k:
        return 0
    p = sorted(points)
    return sum(all(s[i][0] < s[i+1][0] for i in range(k-1))
               and all(cross(s[i],s[i+1],s[i+2]) < 0 for i in range(k-2))
               for s in itertools.combinations(p,k))

def index_order_projection(points):
    """Exact affine map making labels strictly x increasing, if one exists.

    Intersect open halfplanes u dot (p[i+1]-p[i]) > 0. Every nonvertical
    feasible u scales to ux=+1 or -1; each gives an open rational interval
    for uy. The perpendicular second row keeps determinant positive.
    """
    differences=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:])]
    for ux in (1,-1):
        lo=hi=None
        feasible=True
        for dx,dy in differences:
            if dy==0:
                if ux*dx<=0: feasible=False;break
            elif dy>0:
                bound=Fraction(-ux*dx,dy)
                lo=bound if lo is None else max(lo,bound)
            else:
                bound=Fraction(-ux*dx,dy)
                hi=bound if hi is None else min(hi,bound)
        if not feasible or (lo is not None and hi is not None and lo>=hi): continue
        uy=(lo+hi)/2 if lo is not None and hi is not None else lo+1 if lo is not None else hi-1 if hi is not None else Fraction(0)
        x,y=ux*uy.denominator,uy.numerator
        projected=[(x*a+y*b,-y*a+x*b) for a,b in points]
        assert all(a[0]<b[0] for a,b in zip(projected,projected[1:]))
        return projected,(x,y)
    # A strictly feasible vertical direction has a nonvertical neighborhood,
    # hence would already have been found in one of the two branches.
    return None,None

def audit(real, orient, case):
    p = integer_points(real)
    cons = constraints(orient)
    if len(p) != case['n'] or max(max(c[:3]) for c in cons) >= len(p):
        raise ValueError('Wrong number of output points')
    violations = sum(((d>0)-(d<0)) != s for a,b,c,s in cons
                     for d in [cross(p[a],p[b],p[c])])
    collinear = sum(cross(*triple)==0 for triple in itertools.combinations(p,3))
    pts = Path(real).with_suffix('.pts')
    pts.write_text(str(len(p))+'\n'+''.join(f'{x} {y}\n' for x,y in p))
    large = max(abs(v) for point in p for v in point) > 10**18
    validator = ROOT/'direct'/('verify_big' if large else 'verify')
    cmd = [str(validator),'--input',str(pts),'--gon',str(case.get('gon',0)),
           '--hole',str(case.get('hole',0))]
    if not large:
        cmd += ['--cap',str(case.get('cap',0))]
    result = subprocess.run(cmd,text=True,capture_output=True,timeout=120)
    if result.returncode not in (0,1):
        raise ValueError('Exhaustive validator failed: '+result.stderr)
    geometry = json.loads(result.stdout)
    if large and case.get('cap',0):
        geometry['convex_caps'] = cap_count(p,case['cap'])
        geometry['valid'] = geometry['valid'] and not geometry['convex_caps']
    result={'orientation_violations':violations,'constraint_count':len(cons),
            'collinear_triples_independent':collinear,'geometry':geometry,
            'integer_points':str(pts.relative_to(ROOT)),
            'integer_points_sha256':digest(pts)}
    if case.get('cap',0):
        mapped,direction=index_order_projection(p)
        result['label_order_affine_feasible']=mapped is not None
        if mapped is not None:
            mapped_caps=cap_count(mapped,case['cap'])
            mapped_path=Path(real).with_suffix('.ordered.pts')
            mapped_path.write_text(str(len(mapped))+'\n'+''.join(f'{x} {y}\n' for x,y in mapped))
            result['ordered_geometry']={'valid':not collinear and not geometry['convex_gons']
                                        and not geometry['empty_holes'] and not mapped_caps,
                                        'convex_caps':mapped_caps,'projection_direction':direction,
                                        'integer_points':str(mapped_path.relative_to(ROOT)),
                                        'integer_points_sha256':digest(mapped_path)}
    return result

def run_one(job):
    case,binary,label,seed,seconds,outdir,extra = job
    if _STOP is not None and _STOP.is_set():return None
    directory = Path(outdir)/(case['id']+f'-s{seed}')
    directory.mkdir(parents=True,exist_ok=False)
    orient = ROOT/case['orientation']
    if digest(orient) != case['sha256']:
        raise ValueError('Orientation changed after manifest registration')
    real = directory/'points.real'
    cmd = [binary,str(orient),'-t','1','-i','10','-r','30000','-s',str(seed),
           '-f','','-c',str(ROOT/case['symmetry']) if case.get('symmetry') else '',
           '-o',str(real)]+extra
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    timed_out = False
    interrupted = False
    killed = False
    with (directory/'stdout.log').open('w') as stdout, (directory/'stderr.log').open('w') as stderr:
        proc = subprocess.Popen(cmd,stdout=stdout,stderr=stderr,start_new_session=True,cwd=ROOT)
        while True:
            remaining=seconds-(time.monotonic()-start)
            interrupted=_STOP is not None and _STOP.is_set()
            if remaining<=0 or interrupted:
                timed_out=remaining<=0
                try:os.killpg(proc.pid,signal.SIGINT)
                except ProcessLookupError:pass
                try:code=proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    killed=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
                break
            try:code=proc.wait(timeout=min(.25,remaining));break
            except subprocess.TimeoutExpired:continue
    elapsed = time.monotonic()-start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    log = re.sub(r'\x1b\[[0-9;]*m','',(directory/'stdout.log').read_text())
    reported = [int(x) for x in re.findall(r'Violations:\s*(\d+)',log)]
    iterations = [int(x) for x in re.findall(r'Total iterations:\s*(\d+)',log)]
    record = {'case':case['id'],'problem':case['problem'],'split':case['split'],
              'label':label,'binary_sha256':digest(binary),'seed':seed,'command':cmd,
              'wall_limit_seconds':seconds,'wall_seconds':elapsed,
              'cpu_user_seconds':after.ru_utime-before.ru_utime,
              'cpu_system_seconds':after.ru_stime-before.ru_stime,
              'timed_out':timed_out,'killed_after_sigint':killed,'returncode':code,
              'interrupted':interrupted,'eligible_for_matched_comparison':not interrupted,
              'reported_violations':reported[-1] if reported else None,
              'reported_iterations':iterations[-1] if iterations else None,
              'orientation_sha256':case['sha256'],'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    if real.exists():
        try:
            record.update(audit(real,orient,case))
        except Exception as error:
            record['audit_error'] = str(error)
    else:
        record['audit_error'] = 'No coordinate output'
    (directory/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

def prepare(args):
    target = HERE/'corpus'/'legacy23'
    target.mkdir(parents=True,exist_ok=False)
    cases = []
    for family in ('with_flippable','without_flippable'):
        files = sorted((ROOT/'direct'/'baseline'/family/'scratch').glob('*.or'),key=lambda p:int(p.stem))
        for path in files:
            name = family+'-'+path.stem
            dest = target/(name+'.or')
            shutil.copyfile(path,dest)
            cons = constraints(dest)
            cases.append({'id':'legacy23-'+name,'problem':'23_no7gon_no6hole','split':'legacy_tuning',
                          'n':23,'gon':7,'hole':6,'cap':0,'orientation':str(dest.relative_to(ROOT)),
                          'sha256':digest(dest),'constraint_count':len(cons),
                          'source':str(path.relative_to(ROOT)),'known_seeded':False})
    manifest = {'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'note':'Existing SAT-generated 60-file corpus is tuning only; fresh heldout generation is separate.',
                'baseline_binary_sha256':digest(ROOT/'improvements/localizer/localizer_baseline'),
                'cases':cases}
    Path(args.manifest).write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'manifest':args.manifest}))

def run(args):
    cases = json.loads(Path(args.manifest).read_text())['cases']
    if args.split:
        cases = [c for c in cases if c['split']==args.split]
    out = Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=False)
    source_binary = Path(args.binary).resolve()
    frozen_binary = out/'localizer'
    shutil.copy2(source_binary,frozen_binary)
    binary = str(frozen_binary)
    shutil.copyfile(args.manifest,out/'manifest.json')
    extra=args.extra+json.loads(args.extra_json)
    if not isinstance(extra,list) or any(not isinstance(x,str) for x in extra):raise ValueError('extra-json must be a JSON string array')
    jobs = [(c,binary,args.label,s,args.seconds,str(out),extra) for c in cases for s in args.seeds]
    with (out/'results.jsonl').open('w',buffering=1) as stream:
        context=multiprocessing.get_context('fork');stop=context.Event()
        for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs,mp_context=context,
                initializer=initialize_worker,initargs=(stop,)) as pool:
            futures = [pool.submit(run_one,j) for j in jobs]
            for f in concurrent.futures.as_completed(futures):
                record = f.result()
                if record is None:continue
                stream.write(json.dumps(record)+'\n')
                print(json.dumps({k:record.get(k) for k in ('case','seed','orientation_violations','wall_seconds','audit_error')}),flush=True)

def compare(args):
    def read(path):
        paths=path if isinstance(path,list) else [path]
        rows=[json.loads(line) for p in paths for line in Path(p).read_text().splitlines()]
        rows=[r for r in rows if r.get('eligible_for_matched_comparison',True)]
        result={(r['case'],r['seed']):r for r in rows}
        if len(result)!=len(rows):raise ValueError('Duplicate case/seed in input result sets')
        return result
    a,b = read(args.baseline),read(args.improved)
    pairs=[]
    for key in sorted(a.keys()&b.keys()):
        x,y=a[key],b[key]
        assert x['orientation_sha256']==y['orientation_sha256']
        assert x['wall_limit_seconds']==y['wall_limit_seconds']
        pairs.append((x,y))
    result={'pairs':len(pairs),'baseline_unmatched':len(a)-len(pairs),'improved_unmatched':len(b)-len(pairs),'groups':{}}
    for group in sorted({(x['problem'],x['split']) for x,y in pairs}):
        rows=[(x,y) for x,y in pairs if (x['problem'],x['split'])==group]
        clean=[(x,y) for x,y in rows if 'orientation_violations' in x and 'orientation_violations' in y]
        d=[x['orientation_violations']-y['orientation_violations'] for x,y in clean]
        g={'pairs':len(rows),'auditable_pairs':len(clean),'improved_wins':sum(v>0 for v in d),
           'ties':sum(v==0 for v in d),'regressions':sum(v<0 for v in d),
           'mean_violation_reduction':statistics.mean(d) if d else None,
           'median_violation_reduction':statistics.median(d) if d else None}
        if d:
            rng=random.Random(20260905)
            clusters={}
            for x,y in clean:
                clusters.setdefault(x['orientation_sha256'],[]).append(x['orientation_violations']-y['orientation_violations'])
            model_means=[statistics.mean(v) for v in clusters.values()]
            bootstrap=sorted(statistics.mean(rng.choices(model_means,k=len(model_means))) for _ in range(10000))
            g['independent_model_clusters']=len(model_means)
            g['mean_reduction_model_cluster_bootstrap_95pct']=[bootstrap[250],bootstrap[9749]] if len(model_means)>1 else None
            g['uncertainty_note']='Percentile paired bootstrap resampling unique orientation SHA256 models, averaging seeds and duplicate SAT draws within model. Exploratory; small samples and shared SAT-generation distribution. No interval is estimated from a single unique model.'
        for label,index in [('baseline',0),('improved',1)]:
            rr=[r[index] for r in rows]
            vv=[r['orientation_violations'] for r in rr if 'orientation_violations' in r]
            g[label]={'orientation_successes':sum(v==0 for v in vv),
                      'geometric_successes':sum(r.get('geometry',{}).get('valid',False) for r in rr),
                      'ordered_cap_geometric_successes':sum(r.get('ordered_geometry',{}).get('valid',False) for r in rr),
                      'mean_violations':statistics.mean(vv) if vv else None,
                      'median_violations':statistics.median(vv) if vv else None,
                      'sum_cpu_seconds':sum(r['cpu_user_seconds']+r['cpu_system_seconds'] for r in rr),
                      'sum_wall_seconds':sum(r['wall_seconds'] for r in rr),
                      'audit_errors':sum('audit_error' in r for r in rr)}
        result['groups']['/'.join(group)]=g
    if args.output:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--manifest',required=True);p.set_defaults(func=prepare)
    p=sub.add_parser('run');p.add_argument('--manifest',required=True);p.add_argument('--binary',required=True)
    p.add_argument('--label',required=True);p.add_argument('--output',required=True);p.add_argument('--seconds',type=float,default=15)
    p.add_argument('--seeds',nargs='+',type=int,default=[1]);p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--split');p.add_argument('--extra',nargs='*',default=[]);p.add_argument('--extra-json',default='[]');p.set_defaults(func=run)
    p=sub.add_parser('compare');p.add_argument('--baseline',nargs='+',required=True);p.add_argument('--improved',nargs='+',required=True);p.add_argument('--output');p.set_defaults(func=compare)
    args=parser.parse_args();args.func(args)
if __name__=='__main__':main()
