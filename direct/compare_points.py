#!/usr/bin/env python3
"""Compare labeled signs and canonical order types up to relabeling/reflection."""
import argparse
import functools
import hashlib
import itertools
import json
import pathlib


def read(path):
    words = pathlib.Path(path).read_text().split()
    n = int(words[0])
    assert len(words) == 1+2*n
    return [(int(words[2*i+1]), int(words[2*i+2])) for i in range(n)]


def det(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def hull(points):
    order = sorted(range(len(points)), key=lambda i: points[i])
    lo, hi = [], []
    for target, stream in ((lo, order), (hi, reversed(order))):
        for i in stream:
            while len(target) >= 2 and det(points[target[-2]], points[target[-1]], points[i]) <= 0:
                target.pop()
            target.append(i)
    return lo[:-1]+hi[:-1]


def canonical(points):
    # Every order-type isomorphism maps hull vertices to hull vertices and
    # preserves their radial order, possibly reversing all orientations.
    # At a hull vertex all other rays occupy a strict half-plane, so the
    # cross-product comparator gives a unique linear order without atan2.
    candidates = []
    for pivot in hull(points):
        others = [i for i in range(len(points)) if i != pivot]

        def compare(i, j):
            cross = det(points[pivot], points[i], points[j])
            assert cross, "canonicalization requires general position"
            return -1 if cross > 0 else 1

        others.sort(key=functools.cmp_to_key(compare))
        for order, reflection in (([pivot]+others, 1), ([pivot]+list(reversed(others)), -1)):
            signs = bytes(int(reflection*det(points[order[i]], points[order[j]], points[order[k]]) > 0)
                          for i, j, k in itertools.combinations(range(len(points)), 3))
            candidates.append(signs)
    return min(candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    a, b = read(args.first), read(args.second)
    assert len(a) == len(b)
    ca, cb = canonical(a), canonical(b)
    triples = list(itertools.combinations(range(len(a)), 3))
    changed = sum((det(a[i], a[j], a[k]) > 0) != (det(b[i], b[j], b[k]) > 0) for i, j, k in triples)
    report = {"first": args.first, "second": args.second, "n": len(a), "triples": len(triples),
              "changed_labeled_orientation_signs": changed,
              "isomorphic_order_types_allowing_reflection": ca == cb,
              "first_canonical_sha256": hashlib.sha256(ca).hexdigest(),
              "second_canonical_sha256": hashlib.sha256(cb).hexdigest()}
    if args.output:
        pathlib.Path(args.output).write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
