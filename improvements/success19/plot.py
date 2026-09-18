#!/usr/bin/env python3
"""SVG presentation only: floating point is never used by the certificates."""
import math
from pathlib import Path
OUT=Path(__file__).resolve().parent
rows=[list(map(int,r.split()))for r in(OUT/'witness.qsqrt3').read_text().splitlines()[1:]]
points=[(a+b*math.sqrt(3),c+d*math.sqrt(3))for a,b,c,d in rows]
colors=['#006c8c','#c95818','#657a1b','#9655a2','#ca3464','#516bb3']
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="650" viewBox="0 0 1120 650">',
     '<rect width="1120" height="650" fill="#fafaf7"/>',
     '<g font-family="Arial, sans-serif" fill="#152e39">',
     '<text x="40" y="42" font-size="25" font-weight="bold">19 points · exact threefold symmetry</text>',
     '<text x="40" y="69" font-size="16">Every convex hexagon contains 1, 2, or 4 points — never 0 or 3.</text>']
def panel(left,indices,title,full=False):
    width=500;top=116;height=450
    chosen=[points[i]for i in indices]
    xlo=min(x for x,y in chosen);xhi=max(x for x,y in chosen)
    ylo=min(y for x,y in chosen);yhi=max(y for x,y in chosen)
    span=max(xhi-xlo,yhi-ylo)*1.13;cx=(xlo+xhi)/2;cy=(ylo+yhi)/2
    def pos(i):
        x,y=points[i];return left+width/2+(x-cx)*height/span,top+height/2-(y-cy)*height/span
    svg.extend([f'<text x="{left}" y="103" font-size="17" font-weight="bold">{title}</text>',
                f'<rect x="{left}" y="{top}" width="{width}" height="{height}" rx="8" fill="white" stroke="#d6dcda"/>'])
    if full:
        xy=' '.join(f'{pos(i)[0]:.3f},{pos(i)[1]:.3f}'for i in(15,16,17))
        svg.append(f'<polygon points="{xy}" fill="none" stroke="#bdc7dc" stroke-width="1.5"/>')
        inner=[pos(i)for i in list(range(15))+[18]]
        a=min(x for x,y in inner)-8;b=min(y for x,y in inner)-8
        w=max(x for x,y in inner)-a+8;h=max(y for x,y in inner)-b+8
        svg.append(f'<rect x="{a:.3f}" y="{b:.3f}" width="{w:.3f}" height="{h:.3f}" fill="none" stroke="#7f898b" stroke-dasharray="4 3"/>')
    for i in indices:
        x,y=pos(i);color=colors[i//3]if i<18 else'#152e39';radius=3 if full else 4.2
        svg.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{radius}" fill="{color}"/>')
        if not full or i in(15,16,17):
            svg.append(f'<text x="{x+6:.3f}" y="{y-6:.3f}" font-size="12" fill="{color}">{i+1}</text>')
panel(40,list(range(19)),'Full configuration',True)
panel(580,list(range(15))+[18],'Inner16 points · outer orbit omitted')
svg.extend(['<text x="40" y="603" font-size="15">28 convex hexagons: 15 contain one point, 12 contain two, and 1 contains four.</text>',
            '<text x="40" y="627" font-size="13" fill="#52626a">Colors identify rotational orbits. Coordinates and predicates are certified exactly in Q(√3); this drawing is approximate.</text>',
            '</g></svg>'])
(OUT/'solution.svg').write_text('\n'.join(svg)+'\n')
