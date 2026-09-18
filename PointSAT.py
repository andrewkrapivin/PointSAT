#!/usr/bin/env python3
"""PointSAT command-line entry point; implementation lives with pipeline tests."""
import sys
import signal
if __name__ == '__main__' and (len(sys.argv) == 1 or sys.argv[1] in {
        'run', 'doctor', 'status', 'solutions', 'import', 'optimize', 'export', 'verify', 'recover', '--help', '-h', '--version'}):
    from pointsat.cli import main as usable_main
    def usable_interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, usable_interrupt)
    raise SystemExit(usable_main(sys.argv[1:] or ['--help']))

from improvements.pipeline.runner import (
    main, normalize_settings, parse_sat_output, process_sat_str,
    retry_seed, run_external, run_pipeline, run_process,
)

if __name__ == "__main__":
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted; worker subprocess groups were stopped.", file=sys.stderr)
        raise SystemExit(130)
