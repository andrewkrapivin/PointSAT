"""Tiny fake subprocess tests only; no benchmark, SAT, or native search."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

SPEC = importlib.util.spec_from_file_location('suite', Path(__file__).with_name('run_scaling_suite.py'))
suite = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(suite)


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pointsat-suite-test-')
        self.root = Path(self.tmp.name)
        self.identity = {'report_output': str(self.root/'report'), 'audit_output': str(self.root/'audit.json')}

    def tearDown(self):
        self.tmp.cleanup()

    def benchmark(self, name, *, code=0, complete=True, delay=0):
        summary = self.root/(name+'.json')
        script = ('import json,time; from pathlib import Path; time.sleep('+str(delay)+'); '
                  'Path('+repr(str(summary))+').write_text('+repr(json.dumps({'complete': complete,
                      'completed_trials': 1, 'registered_trials': 1}))+'); raise SystemExit('+str(code)+')')
        return {'name': name, 'kind': 'benchmark', 'command': [sys.executable, '-c', script],
                'summary': str(summary), 'expected_trials': 1}

    def execute(self, steps, stop=None):
        return suite.execute(self.identity, steps, {}, self.root/'state', stop)

    def test_sequential_completion_and_resume(self):
        steps = [self.benchmark('first'), self.benchmark('second')]
        self.assertEqual(self.execute(steps), 0)
        state = json.loads((self.root/'state/state.json').read_text())
        self.assertEqual([h['name'] for h in state['history']], ['first', 'second'])
        self.assertEqual(state['status'], 'COMPLETE')
        self.assertEqual(self.execute(steps), 0)
        self.assertEqual(len(json.loads((self.root/'state/state.json').read_text())['history']), 4)

    def test_nonzero_never_starts_next(self):
        self.assertEqual(self.execute([self.benchmark('fail', code=3), self.benchmark('next')]), 1)
        self.assertFalse((self.root/'next.json').exists())

    def test_incomplete_summary_never_starts_next(self):
        with self.assertRaisesRegex(ValueError, 'complete, correctly counted'):
            self.execute([self.benchmark('bad', complete=False), self.benchmark('next')])
        self.assertFalse((self.root/'next.json').exists())

    def test_signal_owned_child_then_no_next(self):
        stop = threading.Event(); timer = threading.Timer(.2, stop.set); timer.start()
        try:
            self.assertEqual(self.execute([self.benchmark('slow', delay=5), self.benchmark('next')], stop), 130)
        finally:
            timer.cancel()
        state = json.loads((self.root/'state/state.json').read_text())
        self.assertEqual(state['status'], 'INTERRUPTED'); self.assertFalse((self.root/'next.json').exists())
        self.assertFalse(suite.alive(state['history'][0]['process']))

    def test_existing_output_prevents_every_stage(self):
        (self.root/'audit.json').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'Output already exists'):
            self.execute([self.benchmark('first')])
        self.assertFalse((self.root/'first.json').exists())
        self.assertEqual((self.root/'audit.json').read_text(), 'preserve')

    def test_stop_marker_prevents_start_and_must_be_removed(self):
        state = self.root/'state'; state.mkdir(); (state/'STOP').touch()
        steps = [self.benchmark('first')]
        self.assertEqual(self.execute(steps), 130)
        self.assertEqual(self.execute(steps), 130)
        self.assertFalse((self.root/'first.json').exists())
        (state/'STOP').unlink()
        self.assertEqual(self.execute(steps), 0)

    def test_stop_marker_interrupts_owned_child(self):
        timer = threading.Timer(.2, lambda: (self.root/'state/STOP').touch()); timer.start()
        try:
            self.assertEqual(self.execute([self.benchmark('slow', delay=5), self.benchmark('next')]), 130)
        finally:
            timer.cancel()
        self.assertFalse((self.root/'next.json').exists())
        state = json.loads((self.root/'state/state.json').read_text())
        self.assertFalse(suite.alive(state['history'][0]['process']))

    def test_pending_audit_is_not_passed(self):
        path = self.root/'pending.json'; path.write_text(json.dumps({'status': 'PENDING', 'integrity_ok': True}))
        with self.assertRaisesRegex(ValueError, 'not PASSED'):
            suite.validate_stage({'kind': 'audit', 'output': str(path)})


if __name__ == '__main__':
    unittest.main()
