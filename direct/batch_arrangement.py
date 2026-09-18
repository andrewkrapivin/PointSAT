#!/usr/bin/env python3
"""Scan every single-point deletion of a23-point candidate by exact cells."""
import argparse
import json
import pathlib
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", default="direct/arrangement")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = pathlib.Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for i in range(1, 24):
        source = pathlib.Path(args.input_dir)/f"delete-{i}.pts"
        result = subprocess.run([args.solver, "--input", str(source), "--allow-base-holes", "--crosscheck",
                                 "--seconds", "30", "--output", str(output/f"extension-{i}.pts")],
                                capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        report["deleted_point"] = i
        reports.append(report)
        print(json.dumps(report), flush=True)
    (output/"summary.json").write_text(json.dumps(reports, indent=2)+"\n")


if __name__ == "__main__":
    main()
