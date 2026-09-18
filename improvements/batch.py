"""Bounded, resumable unattended experiment queues (no shell commands).

Jobs: JSON list of {label,command:[...],max_seconds,workers:1,output,
                   audit_command:[...]?}. Outputs must be distinct. Each
job owns one core; maxworkers controls aggregate concurrency. Native search
budgets remain the first stop mechanism; the watchdog is a safety backstop.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
STOP=threading.Event()
LOCK=threading.Lock()


def atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    temporary.replace(path)


def tagged_processes(token):
    """Identify only this job's inherited token; never print environment data.

    The tag survives setsid and orphaning. Start ticks protect against PID
    reuse between discovery and signaling. All queued programs inherit env.
    """
    marker=b'POINTSAT_BATCH_JOB_TOKEN='+token.encode()
    found={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            if marker not in (entry/'environ').read_bytes().split(b'\0'):continue
            fields=(entry/'stat').read_text().rsplit(')',1)[1].split()
            if fields[0]!='Z':found[int(entry.name)]=fields[19]
        except (OSError,IndexError):continue
    return found


def signal_tagged(token,sig):
    found=tagged_processes(token)
    for pid,start_ticks in found.items():
        try:
            fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
            if fields[19]==start_ticks:os.kill(pid,sig)
        except (OSError,IndexError):pass
    return len(found)


def stop_process(process,token):
    # First notify the leader, then all tagged descendants. Do this even if
    # the leader already exited: native workers can own separate sessions.
    if process.poll() is None:process.send_signal(signal.SIGTERM)
    signal_tagged(token,signal.SIGTERM)
    until=time.monotonic()+12
    while time.monotonic()<until:
        process.poll()
        if not tagged_processes(token):break
        time.sleep(.1)
    if tagged_processes(token):signal_tagged(token,signal.SIGKILL)
    if process.poll() is None:process.wait(timeout=5)
    return tagged_processes(token)


def run_job(job,deadline,stop_file):
    folder=Path(job['output']).resolve();folder.mkdir(parents=True,exist_ok=True)
    record_file=folder/'batch_result.json'
    if record_file.exists():return {'label':job['label'],'skipped':'completed'}
    if STOP.is_set() or stop_file.exists() or time.time()>=deadline:return {'label':job['label'],'skipped':'deadline_or_stop'}
    duration=min(float(job['max_seconds']),deadline-time.time()-30)
    if duration<=0:return {'label':job['label'],'skipped':'deadline_grace'}
    command=list(job['command'])
    if not command or any(not isinstance(v,str) for v in command):raise ValueError('command must be nonempty string array')
    record={'label':job['label'],'command':command,'budget_seconds':duration,
            'started_utc':datetime.now(timezone.utc).isoformat(),'output':str(folder)}
    record['command_file_sha256']={v:hashlib.sha256(Path(v).read_bytes()).hexdigest()
                                   for v in command[:2] if Path(v).is_file()}
    begin=time.monotonic();forced=False
    token=uuid.uuid4().hex
    environment=dict(os.environ,POINTSAT_BATCH_JOB_TOKEN=token)
    with (folder/'batch.stdout').open('w') as stdout,(folder/'batch.stderr').open('w') as stderr:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,start_new_session=True,env=environment)
        record['pid']=process.pid;atomic_json(folder/'batch_started.json',record)
        try:
            while process.poll() is None:
                if STOP.is_set() or stop_file.exists() or time.monotonic()-begin>=duration:
                    forced=True;break
                time.sleep(.5)
        finally:
            record['remaining_tagged_pids']=stop_process(process,token)
        record.update(returncode=process.returncode,watchdog_stopped=forced,wall_seconds=time.monotonic()-begin,
                      ended_utc=datetime.now(timezone.utc).isoformat())
    audit=job.get('audit_command')
    if audit and not STOP.is_set() and not stop_file.exists() and time.time()<deadline-25:
        with (folder/'audit.stdout').open('w') as stdout,(folder/'audit.stderr').open('w') as stderr:
            auditor=subprocess.Popen(audit,cwd=ROOT,stdout=stdout,stderr=stderr,start_new_session=True,env=environment)
            audit_until=min(time.time()+60,deadline-25)
            try:
                while auditor.poll() is None:
                    if STOP.is_set() or stop_file.exists() or time.time()>=audit_until:
                        record['audit_stopped']=True;break
                    time.sleep(.25)
            finally:record['remaining_audit_pids']=stop_process(auditor,token)
            record['audit_returncode']=auditor.returncode
    atomic_json(record_file,record)
    return record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--deadline',required=True,help='ISO8601 time with explicit timezone')
    args=parser.parse_args()
    end=datetime.fromisoformat(args.deadline)
    if end.tzinfo is None:raise ValueError('deadline timezone required')
    if not 1<=args.workers<=8:raise ValueError('workers must be1..8')
    jobs=json.loads(Path(args.manifest).read_text());out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    if len({Path(j['output']).resolve() for j in jobs})!=len(jobs):raise ValueError('duplicate output directories')
    if any(j.get('workers',1)!=1 or float(j['max_seconds'])<=0 for j in jobs):raise ValueError('jobs must be single-core with positive budgets')
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    manifest_sha=hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
    atomic_json(out/'supervisor.json',{'pid':os.getpid(),'manifest':args.manifest,'manifest_sha256':manifest_sha,
                'deadline':end.isoformat(),'workers':args.workers,'jobs':len(jobs),'started_utc':datetime.now(timezone.utc).isoformat()})
    source=iter(jobs);results=[]
    def worker():
        while not STOP.is_set() and not (out/'STOP').exists() and time.time()<end.timestamp()-15:
            with LOCK:
                try:job=next(source)
                except StopIteration:return
            try:result=run_job(job,end.timestamp(),out/'STOP')
            except Exception as error:result={'label':job['label'],'error':repr(error)}
            with LOCK:
                results.append(result)
                with (out/'events.jsonl').open('a') as log:log.write(json.dumps(result)+'\n')
                print(json.dumps({k:result[k] for k in ('label','returncode','wall_seconds','skipped','error') if k in result}),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(worker) for _ in range(args.workers)]
        for future in futures:future.result()
    atomic_json(out/'summary.json',{'finished_utc':datetime.now(timezone.utc).isoformat(),'jobs_handled':len(results),
                'stop_requested':STOP.is_set() or (out/'STOP').exists(),'results':results})


if __name__=='__main__':main()
