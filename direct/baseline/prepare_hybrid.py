#!/usr/bin/env python3
"""Select independently checked SAT partials for a bounded C++ repair portfolio."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = Path(__file__).with_name("hybrid_inputs")
    target.mkdir(exist_ok=True)
    records = []
    for run in args.runs:
        for line in (run / "exact_verification.jsonl").read_text().splitlines():
            record = json.loads(line)
            if not record["collinear_triples"] and not record["duplicate_pairs"]:
                records.append(record)
    records.sort(key=lambda r: (r["convex_gons"] + r["empty_holes"], r["source"]))
    jobs = []
    for i, record in enumerate(records[:args.count], 1):
        source = root / record["integer_points"]
        normalized = target / f"candidate_{i}.pts"
        subprocess.run([sys.executable, str(Path(__file__).with_name("normalize_points.py")),
                        str(source), str(normalized)], check=True)
        coordinates = [int(x) for x in normalized.read_text().split()][1:]
        if any(abs(x) > 10**9 for x in coordinates):
            raise ValueError(f"Normalized coordinates exceed search bound: {normalized}")
        verify = subprocess.run([str(root / "direct/verify"), "--input", str(normalized),
                                 "--gon", "7", "--hole", "6"], capture_output=True,
                                text=True, check=False)
        if verify.returncode not in (0, 1):
            raise RuntimeError(verify.stderr)
        checked = json.loads(verify.stdout)
        if (checked["convex_gons"], checked["empty_holes"]) != (record["convex_gons"], record["empty_holes"]):
            raise ValueError("Normalization unexpectedly changed forbidden polygon counts")
        seed = 4100 + i
        jobs.append({
            "name": f"hybrid_sat_partial_{i}_seed{seed}",
            "executable": "direct/search",
            "args": ["--input", str(normalized.relative_to(root)), "--n", "23",
                     "--gon", "7", "--hole", "6", "--mode", "repair",
                     "--seconds", str(args.seconds), "--temperature", "0.5",
                     "--seed", str(seed), "--grid", "1000000", "--stop-on-solution"],
            "gon": 7, "hole": 6, "cap": 0,
            "classification": "hybrid SAT + Localizer partial realization + direct coordinate repair",
            "source_realization": record["source"],
            "source_integer_points": record["integer_points"],
            "initial_verification": checked,
        })
    manifest = Path(__file__).with_name("hybrid_jobs.json")
    manifest.write_text(json.dumps(jobs, indent=2) + "\n")
    print(json.dumps({"manifest": str(manifest), "jobs": len(jobs),
                      "selected": [{"source": r["source"], "gons": r["convex_gons"],
                                    "holes": r["empty_holes"]} for r in records[:args.count]]}, indent=2))


if __name__ == "__main__":
    main()
