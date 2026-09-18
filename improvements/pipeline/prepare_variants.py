#!/usr/bin/env python3
"""Create explicit new experiment settings without changing frozen inputs."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source')
parser.add_argument('destination')
parser.add_argument('--set-json', required=True)
args = parser.parse_args()
target = Path(args.destination)
if target.exists():
    raise SystemExit('Refusing to overwrite variant settings')
settings = json.loads(Path(args.source).read_text())
settings.update(json.loads(args.set_json))
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(settings,indent=2)+'\n')
