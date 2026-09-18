#!/usr/bin/env python3
"""Collect the fully geometric 23-point repair experiments and their certificates."""
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    base = Path(__file__).resolve().parent
    rows = []
    for dirname in ("fill_hole_runs", "fill_hole_cells_runs", "breakout_runs", "breakout_strong_runs"):
        for meta in sorted((base / dirname).glob("*.meta.json")):
            record = json.loads(meta.read_text())
            logpath = meta.with_name(meta.name.removesuffix(".meta.json") + ".jsonl")
            log = [json.loads(line) for line in logpath.read_text().splitlines() if line.strip()]
            start, last = log[0], log[-1]
            certificate = record.get("verification", {})
            args = record["args"]
            rows.append({
                "name": record["name"],
                "classification": record["classification"],
                "input": args[args.index("--input") + 1],
                "cpu_seconds": record.get("cpu_seconds"),
                "wall_seconds": record.get("wall_seconds"),
                "executable_sha256": record["executable_sha256"],
                "returncode": record["returncode"],
                "interrupted": record.get("interrupted", False),
                "initial_gons": start["gons"],
                "initial_holes": start["holes"],
                "initial_hull": start.get("hull_size"),
                "final_n": certificate.get("n"),
                "final_gons": certificate.get("convex_gons"),
                "final_holes": certificate.get("empty_holes"),
                "final_hull_layers": certificate.get("hull_layers"),
                "valid": certificate.get("valid", False),
                "proposals": last.get("proposals"),
                "evaluations": last.get("evaluations"),
                "accepted": last.get("accepted"),
                "penalty_updates": last.get("penalty_updates", 0),
                "certificate": str(meta.relative_to(root)),
                "points": str(logpath.with_suffix(".pts").relative_to(root)),
            })
    report = {
        "scope": "Fully geometric 23-point search, excluding SAT-derived and published-witness inputs",
        "runs": rows,
        "run_count": len(rows),
        "valid_witnesses": sum(row["valid"] for row in rows),
        "aggregate_cpu_seconds": sum(row["cpu_seconds"] or 0 for row in rows),
        "aggregate_worker_wall_seconds": sum(row["wall_seconds"] or 0 for row in rows),
        "minimum_final_polygon_count": min((row["final_gons"] + row["final_holes"] for row in rows), default=None),
        "caveat": "Several stages reuse earlier geometric near misses; these are not all independent cold restarts. Coordinate files with nonzero final polygons are not solutions.",
    }
    destination = base / "direct_comparison.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
