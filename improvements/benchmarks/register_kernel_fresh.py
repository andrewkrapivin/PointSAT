#!/usr/bin/env python3
"""Fixed-work speed fixture selection, independent of convergence outcomes."""
import json
from matched import HERE
all_cases=json.loads((HERE/'all_fresh_v3_manifest.json').read_text())['cases']
ids=('mixed23-seed9101','holes29-seed19501','gons32-seed9301','caps26-seed9401')
cases=[next(c for c in all_cases if c['id']==i) for i in ids]
out={'note':'First declared SAT seed/problem; the lone late29 model is used without search tuning. Identical-v1-trajectory kernel ablation only.',
     'cases':cases}
(HERE/'kernel_fresh_manifest.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'cases':list(ids)}))
