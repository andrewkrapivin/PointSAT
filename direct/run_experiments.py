#!/usr/bin/env python3
"""Bounded local portfolio; C++ does all geometric search and verification.

Each job records its executable hash, arguments, wall/CPU time, log, best
coordinates and an independent exhaustive certificate. No external services.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import time


def run_job(job, directory):
    name = job["name"]
    base = directory / name
    executable = Path(job["executable"]).resolve()
    binary_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    target_n = job.get("target_n")
    if target_n is None and "--n" in job["args"]:
        target_n = int(job["args"][job["args"].index("--n")+1])
    command = [str(executable), *map(str, job["args"]), "--output", str(base.with_suffix(".pts"))]
    start = time.monotonic()
    # /usr/bin/time measures the particular child, avoiding concurrent global
    # RUSAGE_CHILDREN accounting. Its data is kept separately from program logs.
    timed = ["/usr/bin/time", "-f", "%e %U %S %M", "-o", str(base.with_suffix(".time")), *command]
    with base.with_suffix(".jsonl").open("w") as out, base.with_suffix(".stderr").open("w") as err:
        result = subprocess.run(timed, stdout=out, stderr=err, check=False)
    record = dict(job, command=command, executable_sha256=binary_hash,
                  elapsed=time.monotonic()-start, returncode=result.returncode)
    timing = base.with_suffix(".time").read_text().strip().splitlines()
    if timing:
        try:
            wall, user, system, rss = map(float, timing[-1].split())
            record.update(wall_seconds=wall, cpu_seconds=user+system, max_rss_kib=rss)
        except ValueError:
            record["time_output"] = timing
    if base.with_suffix(".pts").exists():
        cert = subprocess.run([str(Path(__file__).parent / "verify"), "--input", str(base.with_suffix(".pts")),
                               "--gon", str(job.get("gon", 7)), "--hole", str(job.get("hole", 6)),
                               "--cap", str(job.get("cap", 0))], capture_output=True, text=True, check=False)
        if cert.stdout.strip():
            record["verification"] = json.loads(cert.stdout)
            record["target_met"] = record["verification"]["valid"] and (target_n is None or record["verification"]["n"] >= target_n)
        record["verification_exit"] = cert.returncode
    base.with_suffix(".meta.json").write_text(json.dumps(record, indent=2)+"\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON list of jobs: name, executable, args, gon, hole, cap")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > (os.cpu_count() or 1):
        parser.error("workers must be between 1 and available logical CPUs")
    jobs = json.loads(args.manifest.read_text())
    names = [j["name"] for j in jobs]
    if len(set(names)) != len(names) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in names):
        parser.error("job names must be unique plain filenames")
    args.output.mkdir(parents=True, exist_ok=True)
    if any((args.output / n).with_suffix(".meta.json").exists() for n in names):
        parser.error("an output job already exists; choose a fresh output directory/name")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_job, j, args.output): j["name"] for j in jobs}
        for future in concurrent.futures.as_completed(futures):
            print(json.dumps(future.result()), flush=True)


if __name__ == "__main__":
    main()
