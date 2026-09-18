#!/usr/bin/env python3
"""Code-native SVG paired residual plot; no search or statistical fitting."""
import argparse
from html import escape
import json
import math
from pathlib import Path
import sqlite3

def main():
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--output');a=p.parse_args()
    database=Path(a.database);output=Path(a.output)if a.output else database.parent/'paired_geometry.svg'
    with sqlite3.connect(database)as db:rows=[json.loads(r[0])for r in db.execute('SELECT result_json FROM trials')]
    indexed={(r['job']['case']['id'],r['job']['seed'],r['job']['arm']):r for r in rows if not r['externally_interrupted']}
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="840" viewBox="0 0 1000 840">',
         '<rect width="1000" height="840" fill="white"/>','<g font-family="Arial,sans-serif" fill="#20313a">',
         '<text x="32" y="34" font-size="23" font-weight="bold">Equal total budget: warm retries versus SAT feedback</text>',
         '<text x="32" y="59" font-size="14">Best exact forbidden-polygon count at saved checkpoints; each point is a matched target and native seed.</text>']
    names=[('mixed23','23 points: no convex7 / no empty6'),('holes29','29 points: no empty6'),
           ('gons32','32 points: no convex7'),('caps26','26 points: no convex7 / no5cap')]
    for panel,(family,title)in enumerate(names):
        left=70+(panel%2)*500;top=110+(panel//2)*335;size=260;pairs=[]
        for (case,seed,arm),r in indexed.items():
            other=indexed.get((case,seed,'core_feedback'))
            if arm!='warm_retry'or other is None or r['job']['case']['problem']!=family:continue
            x=r['posthoc']['minimum_forbidden_count'];y=other['posthoc']['minimum_forbidden_count']
            if x is not None and y is not None:pairs.append((case,seed,x,y))
        maximum=max([max(x,y)for _,_,x,y in pairs]+[1]);extent=math.log1p(maximum)*1.07
        def xpos(v):return left+size*math.log1p(v)/extent
        def ypos(v):return top+size-size*math.log1p(v)/extent
        svg.extend([f'<text x="{left-25}" y="{top-21}" font-size="16" font-weight="bold">{escape(title)}</text>',
                    f'<rect x="{left}" y="{top}" width="{size}" height="{size}" fill="#fafbfd" stroke="#c5cbd0"/>',
                    f'<line x1="{left}" y1="{top+size}" x2="{left+size}" y2="{top}" stroke="#8b959b" stroke-dasharray="5 4"/>'])
        ticks=[v for v in(0,1,3,10,30,100,300,1000,3000,10000,30000)if v<=maximum]
        for v in ticks:
            x=xpos(v);y=ypos(v)
            svg.extend([f'<line x1="{x:.2f}" y1="{top+size}" x2="{x:.2f}" y2="{top+size+4}" stroke="#596970"/>',
                        f'<text x="{x:.2f}" y="{top+size+18}" font-size="10" text-anchor="middle">{v}</text>',
                        f'<line x1="{left-4}" y1="{y:.2f}" x2="{left}" y2="{y:.2f}" stroke="#596970"/>',
                        f'<text x="{left-8}" y="{y+3:.2f}" font-size="10" text-anchor="end">{v}</text>'])
        for case,seed,x,y in pairs:
            color='#147c68'if y<x else'#b34c34'if y>x else'#4c6584'
            svg.append(f'<circle cx="{xpos(x):.2f}" cy="{ypos(y):.2f}" r="5" fill="{color}" fill-opacity=".8" stroke="white"><title>{escape(case)}, seed{seed}: retry{x}, feedback{y}</title></circle>')
        svg.extend([f'<text x="{left+size/2}" y="{top+size+38}" font-size="12" text-anchor="middle">Warm retry count (log1p scale)</text>',
                    f'<text transform="translate({left-47},{top+size/2}) rotate(-90)" font-size="12" text-anchor="middle">Feedback count (log1p scale)</text>',
                    f'<text x="{left+size+15}" y="{top+20}" font-size="12">{len(pairs)} pairs</text>'])
    svg.extend(['<text x="32" y="801" font-size="14">Below the diagonal favors feedback; above favors retries. A zero count is an exact solution.</text>',
                '<text x="32" y="823" font-size="12">Residual counts are diagnostic, not a general success-rate estimate. Independent certificate work is outside search budgets.</text>',
                '</g></svg>'])
    output.write_text('\n'.join(svg)+'\n');print(output)
if __name__=='__main__':main()
