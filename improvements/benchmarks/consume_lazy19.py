#!/usr/bin/env python3
"""Single-core bounded consumer of completed BFP-screened abstract19 models.

This is an exploratory cold-v1 then warm-v6-line portfolio, not a paired
algorithm benchmark. When no target is ready, run bounded actual-geometry
search instead. Neither a BFP UNKNOWN nor NO_BFP_FOUND implies realizability.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import signal
import subprocess
import time
import overnight_case as bounded_runner
from independent_audit import audit_file,model_from_orientations
from matched import ROOT,digest

STOP=bounded_runner.STOP

def atomic(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)

def exact_geometry(points):
    result=subprocess.run([str(ROOT/'improvements/symmetry19/verify_hexagons'),str(points)],text=True,capture_output=True,timeout=30)
    if result.returncode not in(0,1):raise RuntimeError('Independent hexagon verifier failed: '+result.stderr)
    report=json.loads(result.stdout)
    report['raw_objective']=report['interior_histogram'][0]+report['interior_histogram'][3]+1000000*report['collinear_triples']
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--deadline',required=True);parser.add_argument('--geometry-binary',required=True);parser.add_argument('--geometry-seed',required=True)
    parser.add_argument('--geometry-extra-json',default='[]');parser.add_argument('--native-seconds',type=float,default=45)
    parser.add_argument('--warm-real',help='optional immutable indexed-real warm seed for v6; otherwise warm from v1 output')
    parser.add_argument('--fallback-seconds',type=float,default=60);parser.add_argument('--seed',type=int,default=625190)
    parser.add_argument('--allow-unscreened',action='store_true',help='test-only: include legacy NOT_RUN inputs')
    parser.add_argument('--max-models',type=int,default=0,help='test-only bound;0 keeps consuming until deadline')
    args=parser.parse_args();deadline=datetime.fromisoformat(args.deadline)
    if deadline.tzinfo is None:raise ValueError('Deadline must specify timezone')
    end=deadline.timestamp();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    source=Path(args.models).resolve();geometry_binary=Path(args.geometry_binary).resolve()
    extras=json.loads(args.geometry_extra_json)
    if not isinstance(extras,list)or any(not isinstance(v,str)for v in extras):raise ValueError('Bad geometry flags')
    for sig in(signal.SIGINT,signal.SIGTERM):signal.signal(sig,bounded_runner.stop)
    native=[ROOT/'improvements/localizer/localizer_v1',ROOT/'improvements/localizer/localizer_v6']
    registration={'arguments':vars(args),'binary_sha256':{str(p):digest(p)for p in native+[geometry_binary]},
                  'geometry_seed_sha256':digest(args.geometry_seed),'classification':'exploratory model-consumer; not paired benchmark'}
    if args.warm_real:registration['warm_real_sha256']=digest(args.warm_real)
    config=out/'registration.json'
    if config.exists():
        previous=json.loads(config.read_text())
        if previous['binary_sha256']!=registration['binary_sha256']:raise ValueError('Frozen binary changed across resume')
    else:atomic(config,registration)
    checkpoint=out/'checkpoint.json'
    if checkpoint.exists():state=json.loads(checkpoint.read_text())
    else:
        seed=out/'initial_geometry.pts';shutil.copyfile(args.geometry_seed,seed)
        state={'processed_hashes':[],'attempts':0,'fallbacks':0,'best_geometry':str(seed),
               'best_verification':exact_geometry(seed),'successes':[]}
        atomic(checkpoint,state)
    events=(out/'events.jsonl').open('a',buffering=1)
    def event(**data):
        data['utc']=datetime.now(timezone.utc).isoformat();events.write(json.dumps(data)+'\n');print(json.dumps(data),flush=True)
    def budget(limit):return max(0,min(limit,end-time.time()-5))
    while not STOP.is_set()and budget(1)>0:
        ready=[]
        for metadata in sorted(source.glob('model*.json')):
            orient=metadata.with_suffix('.or')
            if not orient.exists():continue
            try:
                info=json.loads(metadata.read_text());status=info.get('bfp_status','NOT_RUN')
                allowed={'UNKNOWN','NO_BFP_FOUND','NUMERIC_CANDIDATE_UNCERTIFIED'}
                if args.allow_unscreened:allowed.add('NOT_RUN')
                if status not in allowed:continue
                model=model_from_orientations(orient,19)
                if model is None or info.get('cube')!=model:continue
                key=digest(orient)
                if key not in state['processed_hashes']:ready.append((orient,metadata,info,key))
            except (OSError,ValueError,KeyError,TypeError,AttributeError,json.JSONDecodeError):continue
        if ready:
            orient,metadata,info,key=ready[0];number=state['attempts'];state['attempts']+=1
            atomic(checkpoint,state)
            folder=out/'models'/f'attempt{number:06d}-{key[:12]}';folder.mkdir(parents=True)
            target=folder/'target.or';shutil.copyfile(orient,target);shutil.copyfile(metadata,folder/'source.json')
            records=[];warm=Path(args.warm_real).resolve()if args.warm_real else None
            for variant,binary in enumerate(native):
                seconds=budget(args.native_seconds)
                if STOP.is_set()or seconds<=0:break
                label='v1_cold'if variant==0 else'v6_line10_warm'
                run_dir=folder/label;run_dir.mkdir();real=run_dir/'points.real'
                command=[str(binary),str(target),'-t','1','-i','10','-r','30000','-s',str(args.seed+number),
                         '-f','','-c','','-o',str(real)]
                if variant:
                    command+=['--line-every','10']
                    if warm is not None:command+=['-w',str(warm)]
                record=bounded_runner.bounded(command,run_dir/'native',seconds)
                record.update(label=label,bfp_status=info.get('bfp_status'),orientation_sha256=key,
                              warm_start=bool(variant and warm is not None),requested_seconds=args.native_seconds)
                if real.exists():
                    try:
                        certificate=audit_file(real,19,'hex19',run_dir/'independent',orient=target)
                        record['independent_certificate']=certificate
                        if warm is None:warm=real
                        if certificate['accepted']:
                            state['successes'].append(certificate['certificate'])
                            event(event='actual_geometry_success',certificate=certificate['certificate'],exact_C3=False)
                    except Exception as error:record['audit_error']=repr(error)
                atomic(run_dir/'result.json',record);records.append(record)
                atomic(checkpoint,state)
            completed=len(records)==2 and not any(r['interrupted']for r in records)
            if completed:state['processed_hashes'].append(key)
            atomic(folder/'result.json',{'source':str(orient),'hash':key,'bfp_status':info.get('bfp_status'),
                                        'complete':completed,'runs':records})
            atomic(checkpoint,state);event(event='model_complete',source=str(orient),complete=completed,attempt=number)
            if args.max_models and len(state['processed_hashes'])>=args.max_models:break
        elif state['best_verification']['raw_objective']:
            number=state['fallbacks'];state['fallbacks']+=1
            atomic(checkpoint,state)
            folder=out/'fallback'/f'run{number:06d}';folder.mkdir(parents=True);points=folder/'points.pts'
            seconds=budget(args.fallback_seconds)
            if seconds<=0:break
            command=[str(geometry_binary),'--input',state['best_geometry'],'--output',str(points),
                     '--seconds',str(seconds),'--seed',str(args.seed+1000000+number)]+extras
            record=bounded_runner.bounded(command,folder/'native',seconds+1)
            if points.exists():
                try:
                    verification=exact_geometry(points);record['independent_verification']=verification
                    if verification['raw_objective']<=state['best_verification']['raw_objective']:
                        state.update(best_geometry=str(points),best_verification=verification)
                    if verification['valid']:
                        event(event='actual_geometry_success',points=str(points),exact_C3=False)
                except Exception as error:record['audit_error']=repr(error)
            atomic(folder/'result.json',record);atomic(checkpoint,state)
            event(event='geometry_fallback',run=number,best_objective=state['best_verification']['raw_objective'])
        else:STOP.wait(min(30,budget(30)))
    state['stopped_utc']=datetime.now(timezone.utc).isoformat();state['stop_requested']=STOP.is_set()
    atomic(checkpoint,state);event(event='consumer_stopped',processed=len(state['processed_hashes']),fallbacks=state['fallbacks'])

if __name__=='__main__':main()
