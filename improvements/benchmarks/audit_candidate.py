#!/usr/bin/env python3
"""Snapshot and independently audit a single immutable candidate artifact."""
import argparse
import json
from pathlib import Path
import shutil
from matched import ROOT,audit,digest
parser=argparse.ArgumentParser();parser.add_argument('--real',required=True);parser.add_argument('--orient',required=True)
parser.add_argument('--output',required=True);parser.add_argument('--n',type=int,default=23)
parser.add_argument('--gon',type=int,default=7);parser.add_argument('--hole',type=int,default=6)
parser.add_argument('--cap',type=int,default=0);args=parser.parse_args()
out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
source=Path(args.real).resolve();orient=Path(args.orient).resolve()
real=out/'points.real';constraints=out/'constraints.or';shutil.copyfile(source,real);shutil.copyfile(orient,constraints)
record={'source':str(source.relative_to(ROOT)),'source_sha256':digest(source),
        'constraint_source':str(orient.relative_to(ROOT)),'constraint_sha256':digest(orient)}
record.update(audit(real,constraints,{'n':args.n,'gon':args.gon,'hole':args.hole,'cap':args.cap}))
(out/'audit.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
