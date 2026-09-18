#!/usr/bin/env python3
"""Run unmodified PointSAT under a wall limit and record aggregate resource use."""
import argparse
import datetime
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("settings")
    parser.add_argument("--wall-seconds", type=float, default=600)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    settings = json.loads(Path(args.settings).read_text())
    out = Path(settings["output_folder"])
    out.mkdir(parents=True, exist_ok=True)
    if (out / "raw_results.jsonl").exists():
        raise SystemExit("Refusing to overwrite an existing baseline run")
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    begin = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    command = [sys.executable, "-u", "PointSAT.py", args.settings]
    timed_out = False
    with (out / "console.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            process.wait(timeout=args.wall_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    elapsed = time.perf_counter() - begin
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    records = []
    raw = out / "raw_results.jsonl"
    if raw.exists():
        for line in raw.read_text().splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    sat = [r for r in records if r["type"] == "SAT"]
    realize = [r for r in records if r["type"] == "Realize"]
    summary = {
        "started_utc": started,
        "command": command,
        "settings": settings,
        "wall_seconds": elapsed,
        "wall_limit_seconds": args.wall_seconds,
        "cpu_user_seconds": after.ru_utime - before.ru_utime,
        "cpu_system_seconds": after.ru_stime - before.ru_stime,
        "max_rss_kib": after.ru_maxrss,
        "returncode": process.returncode,
        "timed_out": timed_out,
        "sat_jobs_completed": len(sat),
        "sat_models": sum(r.get("satisfiable", False) for r in sat),
        "sat_stage_worker_seconds": sum(r["time_taken"] for r in sat),
        "realization_attempts": len(realize),
        "realized": sum(r.get("realized", False) for r in realize),
        "realization_stage_worker_seconds": sum(r["time_taken"] for r in realize),
        "minimum_orientation_violations": min((r["violations"] for r in realize), default=None),
        "realization_files": sorted(str(p) for p in (out / "realizations").glob("*.real")),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
