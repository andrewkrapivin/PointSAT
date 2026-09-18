#!/usr/bin/env python3
"""Reproduce deterministic construction timing with child CPU and wall clocks."""
import argparse
import hashlib
import json
import pathlib
import resource
import statistics
import subprocess
import tempfile
import time


def summary(samples):
    return {"min": min(samples), "median": statistics.median(samples), "max": max(samples),
            "mean": statistics.mean(samples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--construct", default="direct/construct")
    parser.add_argument("--verify", default="direct/verify")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = {"method": "known_erdos_szekeres_construction", "runs_per_target": args.runs,
              "timing_units": "seconds", "cpu_scope": "child user+system time, including process startup and output write",
              "construction_wall_scope": "C++ steady_clock, construction plus output write; excludes process startup",
              "targets": []}
    with tempfile.TemporaryDirectory(prefix="pointsat-construction-benchmark-") as temporary:
        fixture = pathlib.Path(temporary)/"constructed.pts"
        for n, cap in ((32, 0), (26, 5)):
            cpu_samples, wall_samples, process_samples, digests = [], [], [], set()
            for _ in range(args.runs):
                before_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
                before_wall = time.monotonic()
                run = subprocess.run([args.construct, "--gon", "7", "--cap", str(cap), "--output", str(fixture)],
                                     capture_output=True, text=True, check=True)
                after_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
                process_samples.append(time.monotonic()-before_wall)
                cpu_samples.append(after_cpu.ru_utime+after_cpu.ru_stime-before_cpu.ru_utime-before_cpu.ru_stime)
                stats = json.loads(run.stdout)
                assert stats["n"] == n
                wall_samples.append(stats["seconds"])
                digests.add(hashlib.sha256(fixture.read_bytes()).hexdigest())
            assert len(digests) == 1, "non-deterministic construction output"
            certificate = subprocess.run([args.verify, "--input", str(fixture), "--gon", "7", "--hole", "0", "--cap", str(cap)],
                                         capture_output=True, text=True, check=True)
            report["targets"].append({"n": n, "gon": 7, "cap": cap, "deterministic_sha256": digests.pop(),
                                      "cpu_seconds": summary(cpu_samples), "construction_wall_seconds": summary(wall_samples),
                                      "process_wall_seconds": summary(process_samples), "verification": json.loads(certificate.stdout)})
    pathlib.Path(args.output).write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
