#!/usr/bin/env python3
"""Freeze v3's prespecified treatment before inspecting heldout outcomes."""
import json
from pathlib import Path
import time
from matched import ROOT,HERE,digest
binary=ROOT/'improvements/localizer/localizer_v3'
old=json.loads((HERE/'fresh_manifest.json').read_text())
late=json.loads((HERE/'late_holes29/manifest.json').read_text())
out={'registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
     'treatment':{'binary_sha256':digest(binary),'extra_arguments':['--line-every','10'],
                  'seeds':[1,17,101],'wall_seconds':15,'warm_start':False,
                  'selection':'Frozen by native developer using tuning only before heldout result feedback.'},
     'cases':old['cases']+late['cases'],'missing_initial_cases':old['missing_cases']}
target=HERE/'all_fresh_v3_manifest.json'
if target.exists():raise SystemExit('Refusing to replace a registered treatment')
target.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'cases':len(out['cases']),'treatment':out['treatment']}))
