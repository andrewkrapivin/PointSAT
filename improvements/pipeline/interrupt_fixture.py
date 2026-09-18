"""Subprocess-only fixture proving coordinator cancellation flushes native output."""
import json
from pathlib import Path
import sys

from improvements.pipeline import runner as p


def fake_job(job):
    settings = p._state['settings']
    native = ('import pathlib,signal,sys,time; '
              'signal.signal(signal.SIGINT,lambda s,f:(pathlib.Path(sys.argv[2]).write_text("saved incumbent"),sys.exit(0))); '
              'pathlib.Path(sys.argv[1]).write_text("ready"); time.sleep(30)')
    stage = p.run_process('', [sys.executable,'-c',native,settings['ready_file'],settings['saved_file']],30,True)
    return dict(job,status='PARTIAL',satisfiable=False,realized=False,time_taken=stage['elapsed'])


if __name__ == '__main__':
    p._process_job = fake_job
    try:
        p.run_pipeline(json.loads(Path(sys.argv[1]).read_text()))
    except KeyboardInterrupt:
        raise SystemExit(130)
