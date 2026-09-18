#!/usr/bin/env python3
"""Summarize paired PointSAT runs, preserving raw outcomes for future analysis."""
import argparse
import json
from pathlib import Path
import statistics


def describe(values):
    return {"count": len(values), "minimum": min(values, default=None),
            "median": statistics.median(values) if values else None,
            "mean": statistics.mean(values) if values else None,
            "maximum": max(values, default=None)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args()
    summaries = []
    for run in args.runs:
        data = [json.loads(x) for x in (run / "raw_results.jsonl").read_text().splitlines()]
        sat = [r for r in data if r["type"] == "SAT"]
        realize = [r for r in data if r["type"] == "Realize"]
        summary = json.loads((run / "summary.json").read_text())
        summary["run"] = str(run)
        summary["sat_worker_seconds"] = describe([r["time_taken"] for r in sat])
        summary["realize_worker_seconds"] = describe([r["time_taken"] for r in realize])
        summary["orientation_violations"] = describe([r["violations"] for r in realize])
        summary["omitted_flippables"] = describe([len(r.get("flippable", [])) for r in sat])
        exact = run / "exact_verification.jsonl"
        if exact.exists():
            geometry = [json.loads(x) for x in exact.read_text().splitlines()]
            summary["independently_valid"] = sum(r["valid"] for r in geometry)
            summary["convex_gons"] = describe([r["convex_gons"] for r in geometry])
            summary["empty_holes"] = describe([r["empty_holes"] for r in geometry])
        summaries.append(summary)
    report = {"runs": summaries}
    if len(args.runs) == 2:
        records = []
        for run in args.runs:
            data = [json.loads(x) for x in (run / "raw_results.jsonl").read_text().splitlines()]
            records.append({r["scranfilize_seed"]: r for r in data if r["type"] == "Realize"})
        paired = sorted(set(records[0]) & set(records[1]))
        report["paired_seeds"] = paired
        report["paired_orientation_violations"] = {
            str(run): describe([record[seed]["violations"] for seed in paired])
            for run, record in zip(args.runs, records)
        }
        report["paired_valid"] = {
            str(run): sum(record[seed]["realized"] for seed in paired)
            for run, record in zip(args.runs, records)
        }
    print(json.dumps(report, indent=2))
    destination = Path(__file__).with_name("comparison.json")
    destination.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
