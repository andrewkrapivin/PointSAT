#!/usr/bin/env python3
"""Recover timing/certificates after intentionally cancelling a paused job queue."""
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    base = Path(__file__).resolve().parent
    jobs = json.loads((base / "breakout_jobs.json").read_text())
    directory = base / "breakout_runs"
    for job in jobs[:2]:
        prefix = directory / job["name"]
        destination = prefix.with_suffix(".meta.json")
        if destination.exists():
            continue
        timing = prefix.with_suffix(".time").read_text().strip().splitlines()
        if not timing:
            raise RuntimeError("The trial has not finished: " + job["name"])
        wall, user, system, rss = map(float, timing[-1].split())
        interrupted = any("signal" in line for line in timing[:-1])
        executable = root / job["executable"]
        points = prefix.with_suffix(".pts")
        result = subprocess.run([str(root / "direct/verify"), "--input", str(points),
                                 "--gon", "7", "--hole", "6"],
                                capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr)
        record = dict(job,
            command=[str(executable), *job["args"], "--output", str(points.relative_to(root))],
            executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            elapsed=wall, wall_seconds=wall, cpu_seconds=user+system, max_rss_kib=rss,
            returncode=143 if interrupted else 0, interrupted=interrupted,
            verification=json.loads(result.stdout), verification_exit=result.returncode,
            recovered_after_queue_cancel=True,
            interruption_reason="Reallocated a weaker four-hull search to a new fully geometric triangular one-hole 23-point candidate; the other running worker completed normally.")
        destination.write_text(json.dumps(record, indent=2) + "\n")
    cancelled = [{"name": job["name"], "status": "cancelled_before_start",
                  "reason": "Prioritized the new triangular one-hole 23-point geometric seed"}
                 for job in jobs[2:]]
    (directory / "cancelled.json").write_text(json.dumps(cancelled, indent=2) + "\n")
    print(json.dumps({"recovered": [job["name"] for job in jobs[:2]], "cancelled": cancelled}, indent=2))


if __name__ == "__main__":
    main()
