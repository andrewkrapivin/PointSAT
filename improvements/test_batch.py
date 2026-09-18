"""Watchdog regressions: native checkpoint, setsid orphan, audit stop flag."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import batch


def child(folder,ignore=False):
    folder=Path(folder)
    def end(*_):
        (folder/'saved').write_text('checkpoint\n')
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,signal.SIG_IGN if ignore else end)
    (folder/'ready').write_text('ready\n')
    while True:time.sleep(.1)


def main():
    if len(sys.argv)>1:
        if sys.argv[1]=='child':child(sys.argv[2]);return
        if sys.argv[1]=='parent':
            folder=Path(sys.argv[2]);p=subprocess.Popen([sys.executable,__file__,'child',str(folder)],start_new_session=True)
            while not (folder/'ready').exists():time.sleep(.01)
            (folder/'child_pid').write_text(str(p.pid))
            if sys.argv[3]=='wait':
                while True:time.sleep(.1)
            return
    root=Path(tempfile.mkdtemp(prefix='pointsat-batch-test-'))
    for mode in ('exit','wait'):
        folder=root/mode;folder.mkdir()
        job={'label':mode,'output':str(folder),'command':[sys.executable,__file__,'parent',str(folder),mode],
             'max_seconds':1,'workers':1}
        result=batch.run_job(job,time.time()+60,root/'STOP')
        assert (folder/'saved').exists(),result
        assert not result['remaining_tagged_pids'],result
        pid=int((folder/'child_pid').read_text())
        try:state=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]
        except FileNotFoundError:state=None
        assert state in (None,'Z'),(pid,state)
    folder=root/'stopped';folder.mkdir();(root/'STOP').write_text('stop\n')
    result=batch.run_job({'label':'stopped','output':str(folder),'command':['false'],'max_seconds':1},time.time()+60,root/'STOP')
    assert result['skipped']=='deadline_or_stop'
    print(json.dumps({'passed':True,'tests':3,'artifacts':str(root)}))


if __name__=='__main__':main()
