#!/usr/bin/env python3
"""Exact full-sign canonical forms under point relabeling and reflection.

This does not prove realizability. A complete nonzero alternating triple-sign
table is supported when at least one pivot has a transitive radial tournament.
Every general-position affine point configuration has such a pivot: every
convex-hull vertex does. The method also supports abstract sign tables meeting
that condition, without assuming or claiming oriented-matroid axioms.

For a pivot p, orient i -> j when chi(p,i,j) is positive. A transitive tournament
has distinct outdegrees 0,...,n-2, which uniquely determine its order. Relabeling
maps eligible pivots and their orders bijectively; reflection reverses every
order. Taking the minimum full triple-sign string over these candidates is
therefore canonical. Equality supplies an explicit sign-preserving/reversing
relabeling, not merely a coarse invariant. Compare canonical_signs for literal
equality; canonical_sha256 is a convenient index, not a collision-free proof.

No eligible pivot means UNSUPPORTED, never a new purported unique type.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re


_ROW = re.compile(r"([ABC])_\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


def parse_orientations(orientations_text: str) -> tuple[int, dict[tuple[int, int, int], int]]:
    """Read complete A/B triples on labels 1..n; normalize unsorted triples.

    Blank lines and full-line '#' comments are allowed. Duplicate triples,
    collinear C triples, malformed rows, and partial tables raise ValueError.
    """
    signs: dict[tuple[int, int, int], int] = {}
    for line_number, row in enumerate(orientations_text.splitlines(), 1):
        row = row.strip()
        if not row or row.startswith("#"):
            continue
        match = _ROW.fullmatch(row)
        if not match:
            raise ValueError(f"Malformed orientation on line {line_number}")
        kind = match[1]
        triple = tuple(int(match[i]) for i in (2, 3, 4))
        if min(triple) < 1 or len(set(triple)) != 3:
            raise ValueError(f"Expected three distinct positive labels on line {line_number}")
        if kind == "C":
            raise ValueError("Canonicalization requires nonzero general-position signs")
        inversions = sum(triple[i] > triple[j] for i, j in ((0, 1), (0, 2), (1, 2)))
        key = tuple(sorted(triple))
        if key in signs:
            raise ValueError(f"Duplicate triple {key}")
        signs[key] = (1 if kind == "A" else -1) * (-1 if inversions % 2 else 1)
    if not signs:
        raise ValueError("Expected a complete nonempty orientation table")
    n = max(max(triple) for triple in signs)
    if len(signs) != n * (n - 1) * (n - 2) // 6:
        raise ValueError("Orientation table must cover every triple on labels 1..n exactly once")
    return n, signs


def canonicalize(orientations_text: str) -> dict:
    """Return a JSON-compatible canonical form or an explicit unsupported result.

    permutation lists the original 1-based labels in canonical order; reflection
    is +1 or -1. For all a<b<c, canonical_signs is '1' precisely when
    reflection * chi(permutation[a], permutation[b], permutation[c]) > 0.
    eligible_pivots contains original 1-based labels. Its membership is equivariant
    under relabeling; the particular minimizing permutation need not be unique.
    """
    n, signs = parse_orientations(orientations_text)
    cube = [[[0] * n for _ in range(n)] for _ in range(n)]
    for (a, b, c), sign in signs.items():
        a, b, c = a - 1, b - 1, c - 1
        cube[a][b][c] = cube[b][c][a] = cube[c][a][b] = sign
        cube[a][c][b] = cube[c][b][a] = cube[b][a][c] = -sign
    positions = tuple(itertools.combinations(range(n), 3))
    eligible = []
    best = None
    best_order = None
    best_reflection = None
    for pivot in range(n):
        others = [i for i in range(n) if i != pivot]
        degree = {i: sum(cube[pivot][i][j] > 0 for j in others) for i in others}
        if sorted(degree.values()) != list(range(n - 1)):
            continue
        order = sorted(others, key=degree.__getitem__, reverse=True)
        # This follows from the degree criterion; check rather than assuming it.
        if any(cube[pivot][order[i]][order[j]] != 1
               for i in range(n - 1) for j in range(i + 1, n - 1)):
            continue
        eligible.append(pivot + 1)
        for candidate, reflection in (([pivot] + order, 1), ([pivot] + order[::-1], -1)):
            word = bytes(int(reflection * cube[candidate[i]][candidate[j]][candidate[k]] > 0)
                         for i, j, k in positions)
            if best is None or word < best:
                best, best_order, best_reflection = word, candidate, reflection
    result = {"supported": best is not None, "n": n, "triple_count": len(signs),
              "canonical_sha256": None, "canonical_signs": None,
              "permutation": None, "reflection": None, "eligible_pivots": eligible,
              "equivalence": "arbitrary_point_relabeling_and_global_reflection",
              "method": "transitive_pivot_full_signs_v1"}
    if best is None:
        result["reason"] = "No transitive radial pivot; this canonicalizer does not support this sign table"
    else:
        payload = f"PointSAT transitive-pivot full signs v1 n={n}\n".encode("ascii") + best
        result.update(canonical_sha256=hashlib.sha256(payload).hexdigest(),
                      canonical_signs="".join(str(bit) for bit in best),
                      permutation=[i + 1 for i in best_order], reflection=best_reflection)
    return result


def labeled_hamming_distance(first: str, second: str, *, allow_reflection: bool = False) -> int:
    """Count differing triple signs; NOT invariant under arbitrary relabeling.

    This measures expanded triple signs, not compressed SAT-variable distance.
    With allow_reflection=True, minimize over a global sign reversal only.
    """
    n, a = parse_orientations(first)
    m, b = parse_orientations(second)
    if n != m:
        raise ValueError("Hamming distance requires the same point labels")
    distance = sum(sign != b[triple] for triple, sign in a.items())
    return min(distance, len(a) - distance) if allow_reflection else distance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Complete A/B orientation file")
    parser.add_argument("--compare", type=Path, help="Optional second orientation file")
    args = parser.parse_args()
    try:
        text = args.input.read_text()
        result = canonicalize(text)
        if args.compare:
            other_text = args.compare.read_text()
            other = canonicalize(other_text)
            result = {"first": result, "second": other,
                      "equivalent": (result["n"] == other["n"] and
                                     result["canonical_signs"] == other["canonical_signs"])
                      if result["supported"] and other["supported"] else None,
                      "labeled_hamming_distance": labeled_hamming_distance(text, other_text)}
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
