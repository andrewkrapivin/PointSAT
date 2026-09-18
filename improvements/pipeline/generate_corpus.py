#!/usr/bin/env python3
"""Freeze tuning/held-out seeds before generating independent SAT orientations."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sat_orient_conversion import get_orientations

PROBLEMS = [(23, "7gon-6hole-23-compact.cnf", "mixed23"),
            (29, "6hole-29-compact.cnf", "holes29"),
            (32, "7gon-32.cnf", "gons32"),
            (26, "7gon-no-5-cap-no-sb-26.cnf", "caps26")]


def generate(job):
    start = time.perf_counter()
    formula = (ROOT / job["cnf"]).read_text()
    prefix = ROOT / job["prefix"]
    scramble = subprocess.run([str(ROOT / "direct/vendor/scranfilize/scranfilize"),
                               "-P", "-f", "0", "-v", "0", "-s", str(job["seed"])],
                              input=formula, capture_output=True, text=True, timeout=60)
    job["scramble_seconds"] = time.perf_counter() - start
    sat_start = time.perf_counter()
    try:
        result = subprocess.run([str(ROOT / "direct/vendor/kissat/build/kissat"), "--quiet", "--plain"],
                                input=scramble.stdout, capture_output=True, text=True, timeout=90)
        job["returncode"] = result.returncode
        job["status"] = next((line[2:] for line in result.stdout.splitlines() if line.startswith("s ")), "UNKNOWN")
        if result.returncode == 10 and job["status"] == "SATISFIABLE":
            literals = [int(x) for line in result.stdout.splitlines() if line.startswith("v ")
                        for x in line[2:].split() if int(x) != 0]
            count = job["n"] * (job["n"] - 1) * (job["n"] - 2) // 6
            orientations = [x for x in literals if abs(x) <= count]
            if len(orientations) != count:
                raise ValueError("SAT orientation assignment is incomplete")
            prefix.with_suffix(".model").write_text("v " + " ".join(map(str, orientations)) + " 0\n")
            prefix.with_suffix(".or").write_text(get_orientations(orientations, job["n"]))
            job["orientation_file"] = str(prefix.with_suffix(".or").relative_to(ROOT))
            job["orientation_sha256"] = hashlib.sha256(prefix.with_suffix(".or").read_bytes()).hexdigest()
    except subprocess.TimeoutExpired:
        job["status"] = "TIMEOUT"
    except Exception as exc:
        job["status"] = "ERROR"
        job["error"] = str(exc)
    job["sat_seconds"] = time.perf_counter() - sat_start
    job["wall_seconds"] = time.perf_counter() - start
    prefix.with_suffix(".json").write_text(json.dumps(job, indent=2) + "\n")
    print(json.dumps(job), flush=True)
    return job


if __name__ == "__main__":
    folder = ROOT / "improvements/pipeline/fresh_corpus"
    folder.mkdir(parents=True, exist_ok=True)
    jobs = [{"n": n, "cnf": cnf, "problem": name, "seed": 9101 + 100*p + i,
             "split": "tuning" if i < 2 else "heldout",
             "prefix": str((folder / f"{name}-seed{9101 + 100*p + i}").relative_to(ROOT))}
            for p, (n, cnf, name) in enumerate(PROBLEMS) for i in range(5)]
    manifest = folder / "frozen_manifest.json"
    if manifest.exists():
        raise SystemExit("Refusing to overwrite a frozen corpus")
    manifest.write_text(json.dumps({"split_rule": "First two seeds per problem are tuning; last three heldout, declared before generation.",
                                    "jobs": jobs}, indent=2) + "\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(generate, jobs))
    (folder / "results.json").write_text(json.dumps(results, indent=2) + "\n")
