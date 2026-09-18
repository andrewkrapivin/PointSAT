#!/usr/bin/env python3
"""Produce independently valid 22-point deletions of a geometric 23 near miss."""
import argparse
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("input",type=Path)
parser.add_argument("--output",required=True,type=Path)
parser.add_argument("--include-invalid",action="store_true",help="also save deletions with holes, for general exact relocation")
args=parser.parse_args()
words=list(map(int,args.input.read_text().split()))
assert words[0]==23 and len(words)==47
points=list(zip(words[1::2],words[2::2]))
args.output.mkdir(parents=True,exist_ok=True)
kept=[]
for deleted in range(23):
    remaining=points[:deleted]+points[deleted+1:]
    content="22\n"+"".join(f"{x} {y}\n" for x,y in remaining)
    result=subprocess.run([str(Path(__file__).parent/"verify"),"--input","-","--gon","7","--hole","6"],
                          input=content,text=True,capture_output=True,check=False)
    if result.returncode==0 or (args.include_invalid and result.returncode==1):
        path=args.output/f"delete-{deleted+1}.pts"
        path.write_text(content)
        kept.append(dict(path=str(path),deleted_index=deleted+1,verification=json.loads(result.stdout)))
args.output.joinpath("manifest.json").write_text(json.dumps(dict(source=str(args.input),deletions=kept),indent=2)+"\n")
print(json.dumps(dict(saved_22_deletions=len(kept),valid_22_deletions=sum(k["verification"]["valid"] for k in kept),paths=[k["path"] for k in kept])))
