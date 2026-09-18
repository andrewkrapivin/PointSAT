# Engineering and experiment report

[PointSAT-improvements.pdf](PointSAT-improvements.pdf) consolidates the workflow,
storage measurements, general-purpose compaction, Localizer ablations, matched
four-family search trials, and earlier exact geometric results. It distinguishes
native evaluation speed from time-to-solution and records unsuccessful extensions.

The report is generated from saved evidence; rebuilding never launches searches:

```sh
MPLCONFIGDIR=/tmp/pointsat-mpl direct/vendor/venv/bin/python reports/build_report.py
```

The builder needs Matplotlib and pdfLaTeX. It refuses a final build until both
registered matched-search cohorts have finished. `--draft` permits an incomplete
table and labels it as such. Generated LaTeX and vector figures are under
`reports/build/`; `report-manifest.json` records input and output SHA-256 hashes.

`storage-benchmark-20260906-v2.json` is the corrected three-repeat storage replay.
The earlier replay is retained for transparency: its comparison erroneously
treated completion order and job-ID order as equivalent. The corrected benchmark
compares identical semantic records by job ID. Neither replay runs SAT or
Localizer, so its timings measure storage/coordinator overhead only.
