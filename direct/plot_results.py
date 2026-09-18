#!/usr/bin/env python3
"""Plot independently verified coordinate files from a JSON panel manifest."""
import argparse
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def layers(points):
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    remaining = sorted(points)
    result = []
    while remaining:
        if len(remaining) < 3:
            result.append(remaining)
            break
        lo, hi = [], []
        for p in remaining:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        for p in reversed(remaining):
            while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
                hi.pop()
            hi.append(p)
        hull = lo[:-1]+hi[:-1]
        result.append(hull)
        selected = set(hull)
        remaining = [p for p in remaining if p not in selected]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="output stem, writes PNG/SVG/PDF")
    parser.add_argument("--title", default="PointSAT: direct geometric constructions and search")
    args = parser.parse_args()
    panels = json.loads(args.manifest.read_text())
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":10, "axes.spines.top":False,
                         "axes.spines.right":False, "axes.edgecolor":"#d0d5dd", "text.color":"#243247"})
    rows = (len(panels)+2)//3
    fig, axes = plt.subplots(rows, 3, figsize=(15, 5*rows), squeeze=False)
    colors = ["#205f8f", "#db7046", "#479887", "#8164a5", "#bb9640", "#64809a", "#ae5f86"]
    certs = []
    for ax, panel in zip(axes.flat, panels):
        path = Path(panel["path"])
        cmd = [str(Path(__file__).parent/"verify"), "--input", str(path), "--gon", str(panel.get("gon",7)),
               "--hole", str(panel.get("hole",6)), "--cap", str(panel.get("cap",0))]
        cert = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(cert.stdout)
        certs.append(dict(path=str(path), **data))
        words = list(map(int, path.read_text().split()))
        points = list(zip(words[1::2], words[2::2]))
        for i, layer in enumerate(layers(points)):
            x, y = zip(*layer)
            color = colors[i % len(colors)]
            if len(layer)>2:
                ax.plot([*x,x[0]], [*y,y[0]], lw=.7, alpha=.5, color=color)
            ax.scatter(x,y,s=22,color=color,zorder=3,edgecolor="white",linewidth=.35)
        if panel.get("labels",False):
            for i,(x,y) in enumerate(points,1):
                ax.annotate(str(i),(x,y),xytext=(3,4),textcoords="offset points",fontsize=6)
        ax.set_aspect("equal",adjustable="box")
        ax.margins(.09)
        ax.tick_params(labelsize=8,color="#d0d5dd")
        ax.set_title(panel["title"],loc="left",fontweight="bold",fontsize=12,pad=12)
        ax.set_xlabel(f'{data["n"]} points · {data["bbox_width"]} × {data["bbox_height"]} integer grid\n'
                      +panel["provenance"],fontsize=9,labelpad=12)
    for ax in list(axes.flat)[len(panels):]:
        ax.set_visible(False)
    fig.suptitle(args.title,fontsize=19,x=.06,ha="left",fontweight="bold")
    fig.text(.06,.025,"Every panel checked by exhaustive subset enumeration with exact integer determinants. Colors identify convex hull layers.",fontsize=9,color="#607086")
    fig.tight_layout(rect=[.035,.055,.99,.94],h_pad=3,w_pad=3)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ["png","svg","pdf"]:
        fig.savefig(args.output.with_suffix("."+suffix),dpi=190,facecolor="white")
    args.output.with_suffix(".certificates.json").write_text(json.dumps(certs,indent=2)+"\n")


if __name__ == "__main__":
    main()
