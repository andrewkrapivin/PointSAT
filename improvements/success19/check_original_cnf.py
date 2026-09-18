#!/usr/bin/env python3
"""Recheck the compact exact witness against the original mapped19 CNF."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from improvements.benchmarks.independent_audit import check_cnf,model_from_orientations
report=check_cnf(model_from_orientations(OUT/'witness.or',19),19,ROOT/'convex_hexagon_inside_19_3sym.cnf',
                 ROOT/'improvements/symmetry19/variants/mapping.json',OUT,'compact')
assert report['satisfiable']and not report['violated_clauses']and not report['wrong_orientation_assumptions']
(OUT/'original_cnf_check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
