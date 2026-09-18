#!/usr/bin/env python3
"""Draw the certified C3 witness, without changing or optimizing coordinates.

Rechecks all triples and six-subsets in exact Q(sqrt(3)) arithmetic, then uses
floating point only for display. Generates publication-ready vector and raster
figures plus their exact-data provenance. Run from any working directory.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'improvements/success19'
COLORS = ['#0072B2', '#D55E00', '#009E73', '#8B5AA5', '#C23D70', '#727B35']


def load_exact():
    spec = importlib.util.spec_from_file_location('certified_c3', SOURCE/'certify.py')
    exact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exact)
    witness = SOURCE/'witness.qsqrt3'
    digest = hashlib.sha256(witness.read_bytes()).hexdigest()
    saved = json.loads((SOURCE/'certificate.json').read_text())
    if digest != saved['witness_sha256']:
        raise ValueError('Witness differs from its saved certificate')
    points = exact.read(witness)
    certificate = exact.verify(points)
    if certificate['interior_histogram'] != saved['interior_histogram']:
        raise ValueError('Exact hexagon counts changed')
    # Divide by two to match the six representatives in the witness README.
    display = [tuple((a+b*math.sqrt(3))/2 for a, b in p) for p in points]
    certificate.update(witness=str(witness.relative_to(ROOT)), witness_sha256=digest,
                       display_scale=0.5, new_coordinate_optimization_performed=False,
                       note='Existing compact witness, unchanged; no new optimization. Floating point only renders the exact data.')
    return display, certificate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/figures19')
    args = parser.parse_args()
    points, certificate = load_exact()
    args.output.mkdir(parents=True, exist_ok=True)
    # Avoid trying to write matplotlib caches to the user's home directory.
    with tempfile.TemporaryDirectory(prefix='pointsat-figure19-') as cache:
        os.environ['MPLCONFIGDIR'] = cache
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.patches import Polygon, Rectangle

        plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                             'pdf.fonttype': 42, 'svg.fonttype': 'none'})
        inner = list(range(15))+[18]
        xs, ys = zip(*(points[i] for i in inner))
        center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2)
        span = max(max(xs)-min(xs), max(ys)-min(ys))*1.24
        bounds = (center[0]-span/2, center[1]-span/2, span, span)

        def setup(ax, indices, zoom=False, labels=True, faint=False):
            ax.set_aspect('equal', adjustable='box')
            ax.set_axis_off()
            ax.set_facecolor('white')
            if zoom:
                ax.set_xlim(bounds[0], bounds[0]+span)
                ax.set_ylim(bounds[1], bounds[1]+span)
            else:
                ax.set_xlim(-44000, 42500)
                ax.set_ylim(-42500, 41000)
            for i in indices:
                color = COLORS[i//3] if i < 18 else '#152B39'
                x, y = points[i]
                ax.scatter([x], [y], s=32 if zoom else 21, color=color,
                           edgecolor='white', linewidth=.45, zorder=4,
                           alpha=.38 if faint else 1)
                if labels and (zoom or i in (15, 16, 17)):
                    angle = math.atan2(y, x) if i != 18 else -math.pi/4
                    if zoom:
                        neighbor = min((j for j in indices if j != i),
                                       key=lambda j: math.dist(points[i], points[j]))
                        if math.dist(points[i], points[neighbor]) < .12*span:
                            # Keep labels of nearly coincident pairs apart;
                            # only text moves, never the plotted coordinates.
                            angle = math.atan2(y-points[neighbor][1], x-points[neighbor][0])
                    dx, dy = 7*math.cos(angle), 7*math.sin(angle)
                    ax.annotate(str(i+1), (x, y), xytext=(dx, dy),
                                textcoords='offset points', fontsize=9,
                                ha='left' if dx >= 0 else 'right',
                                va='bottom' if dy >= 0 else 'top', color=color,
                                zorder=6)

        fig, axes = plt.subplots(1, 2, figsize=(13, 7.6))
        fig.subplots_adjust(left=.035, right=.975, bottom=.22, top=.78, wspace=.11)
        fig.suptitle('19 points: no convex hexagon with 0 or 3 interior points',
                     x=.5, y=.965, fontsize=18, fontweight='bold', color='#152B39')
        fig.text(.5, .908, 'Exact 120° rotational symmetry: six triples and the center',
                 ha='center', fontsize=12, color='#56636C')
        setup(axes[0], range(19))
        axes[0].add_patch(Polygon([points[i] for i in (15, 16, 17)], closed=True,
                                 facecolor='none', edgecolor='#C8CED2', lw=1, zorder=1))
        axes[0].add_patch(Rectangle(bounds[:2], span, span, fill=False,
                                   edgecolor='#657680', lw=1, linestyle=(0, (4, 3))))
        axes[0].set_title('Full configuration', loc='left', fontsize=12, fontweight='bold')
        setup(axes[1], inner, zoom=True)
        axes[1].set_title('Enlarged center: 16 inner points', loc='left', fontsize=12, fontweight='bold')
        legend = [Line2D([], [], marker='o', linestyle='', color=COLORS[i], markersize=6,
                         label=f'{3*i+1}–{3*i+3}') for i in range(6)]
        legend.append(Line2D([], [], marker='o', linestyle='', color='#152B39',
                             markersize=6, label='19 (center)'))
        fig.legend(handles=legend, ncol=7, loc='lower center', bbox_to_anchor=(.5, .158),
                   frameon=False, handletextpad=.4, columnspacing=1.9)
        fig.text(.5, .117, 'Colors identify rotational orbits; the dashed box is enlarged at right.',
                 ha='center', fontsize=10, color='#56636C')
        fig.text(.5, .065, '28 convex hexagons: 15 contain 1 point · 12 contain 2 points · 1 contains 4 points',
                 ha='center', fontsize=12, fontweight='bold', color='#152B39')
        fig.text(.5, .025, 'All 969 triples and 27,132 six-point subsets checked exactly in Q(√3). Equal x/y scale within each panel.',
                 ha='center', fontsize=9, color='#56636C')
        for suffix in ('pdf', 'svg', 'png'):
            fig.savefig(args.output/f'19-point-solution.{suffix}', dpi=190, facecolor='white')
        plt.close(fig)

        # Separate examples explain the predicate without cluttering the main view.
        fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.1))
        fig.subplots_adjust(left=.025, right=.975, top=.77, bottom=.18, wspace=.16)
        fig.suptitle('Examples of the three allowed interior counts', y=.97,
                     fontsize=18, fontweight='bold', color='#152B39')
        fig.text(.5, .897, 'These are examples from the same 19-point configuration, not separate solutions.',
                 ha='center', fontsize=11, color='#56636C')
        examples = []
        for ax, count in zip(axes, (1, 2, 4)):
            example = next(h for h in certificate['convex_hexagons']
                           if len(h['interior']) == count and all(v <= 15 or v == 19 for v in h['vertices']))
            examples.append(example)
            setup(ax, inner, zoom=True, labels=False, faint=True)
            vertices = [points[i-1] for i in example['vertices']]
            ax.add_patch(Polygon(vertices, closed=True, facecolor='#0072B2',
                                 alpha=.09, edgecolor='none', zorder=1))
            ax.add_patch(Polygon(vertices, closed=True, fill=False,
                                 edgecolor='#0072B2', lw=1.5, zorder=2))
            ax.scatter(*zip(*vertices), s=29, color='#0072B2', edgecolor='white', linewidth=.4, zorder=5)
            inside = [points[i-1] for i in example['interior']]
            ax.scatter(*zip(*inside), s=59, color='#D55E00', edgecolor='white', linewidth=.7, zorder=6)
            ax.set_title(f'{count} interior point'+('s' if count != 1 else ''), fontsize=13, fontweight='bold')
        fig.text(.5, .11, 'Blue: chosen convex hexagon    Orange: its interior points    Faint dots: other inner points',
                 ha='center', fontsize=10, color='#56636C')
        fig.text(.5, .06, 'The three outer points are outside every displayed hexagon and are omitted from these enlarged views.',
                 ha='center', fontsize=9, color='#56636C')
        fig.text(.5, .02, 'Some angles and interior gaps are extremely small; inclusion and strict convexity are certified exactly, not inferred from the drawing.',
                 ha='center', fontsize=8, color='#56636C')
        for suffix in ('pdf', 'svg', 'png'):
            fig.savefig(args.output/f'19-point-hexagon-examples.{suffix}', dpi=190, facecolor='white')
        plt.close(fig)
    certificate['displayed_examples'] = examples
    (args.output/'verification.json').write_text(json.dumps(certificate, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'exact_verified': certificate['valid'],
                      'convex_hexagons': sum(certificate['interior_histogram']),
                      'interior_histogram': certificate['interior_histogram']}))


if __name__ == '__main__':
    main()
