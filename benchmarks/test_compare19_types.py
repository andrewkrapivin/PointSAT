"""Canonicalization tests; no SAT/native search and no external dependencies."""
import itertools
from pathlib import Path
import random
import unittest

from benchmarks.compare19_types import canonicalize, labeled_hamming_distance, parse_orientations
from direct.compare_points import canonical as coordinate_canonical


ROOT = Path(__file__).resolve().parents[1]


def orient_text(points):
    rows = []
    for a, b, c in itertools.combinations(range(len(points)), 3):
        x, y, z = points[a], points[b], points[c]
        sign = (y[0] - x[0]) * (z[1] - x[1]) - (y[1] - x[1]) * (z[0] - x[0])
        assert sign
        rows.append(f"{'A' if sign > 0 else 'B'}_({a+1}, {b+1}, {c+1})\n")
    return "".join(rows)


def transformed_text(signs, permutation, reflection=1):
    """Independent dictionary/parity relabeler; permutation maps new -> old."""
    rows = []
    for triple in itertools.combinations(range(1, len(permutation) + 1), 3):
        old = [permutation[i - 1] for i in triple]
        parity = sum(old[i] > old[j] for i in range(3) for j in range(i + 1, 3))
        sign = signs[tuple(sorted(old))] * (-1 if parity % 2 else 1) * reflection
        rows.append(f"{'A' if sign > 0 else 'B'}_{triple}\n")
    return "".join(rows)


class CanonicalTypesTests(unittest.TestCase):
    def assert_witness(self, original, result):
        n, signs = parse_orientations(original)
        self.assertEqual(sorted(result["permutation"]), list(range(1, n + 1)))
        transformed = transformed_text(signs, result["permutation"], result["reflection"])
        _, canonical_signs = parse_orientations(transformed)
        self.assertEqual(result["canonical_signs"],
                         "".join("1" if sign > 0 else "0" for sign in canonical_signs.values()))

    def test_paper23_matches_independent_coordinate_canonicalizer(self):
        words = list(map(int, (ROOT / "direct/seeds/paper23.pts").read_text().split()))
        self.assertEqual(len(words), 1 + 2 * words[0])
        points = list(zip(words[1::2], words[2::2]))
        text = orient_text(points)
        result = canonicalize(text)
        self.assertTrue(result["supported"])
        self.assertEqual(bytes(map(int, result["canonical_signs"])), coordinate_canonical(points))
        self.assert_witness(text, result)

    def test_100_relabelings_and_reflections_per_fixture(self):
        words = list(map(int, (ROOT / "direct/seeds/paper23.pts").read_text().split()))
        fixtures = [orient_text(list(zip(words[1::2], words[2::2]))),
                    (ROOT / "improvements/success19/witness.or").read_text()]
        rng = random.Random(20260906)
        for text in fixtures:
            n, signs = parse_orientations(text)
            expected = canonicalize(text)
            self.assertTrue(expected["supported"])
            original_pivots = set(expected["eligible_pivots"])
            for trial in range(100):
                permutation = rng.sample(range(1, n + 1), n)
                for reflection in (1, -1):
                    with self.subTest(n=n, trial=trial, reflection=reflection):
                        transformed = transformed_text(signs, permutation, reflection)
                        result = canonicalize(transformed)
                        self.assertEqual(result["canonical_signs"], expected["canonical_signs"])
                        self.assertEqual(result["canonical_sha256"], expected["canonical_sha256"])
                        self.assertEqual({permutation[i - 1] for i in result["eligible_pivots"]},
                                         original_pivots)
                        self.assert_witness(transformed, result)

    def test_no_eligible_pivot_is_explicitly_unsupported(self):
        # Positive rank-3 circuit: all four pivot tournaments are directed 3-cycles.
        text = "B_(1,2,3)\nA_(1,2,4)\nB_(1,3,4)\nA_(2,3,4)\n"
        result = canonicalize(text)
        self.assertFalse(result["supported"])
        self.assertEqual(result["eligible_pivots"], [])
        for key in ("canonical_sha256", "canonical_signs", "permutation", "reflection"):
            self.assertIsNone(result[key])
        n, signs = parse_orientations(text)
        for permutation in itertools.permutations(range(1, n + 1)):
            for reflection in (1, -1):
                self.assertFalse(canonicalize(transformed_text(signs, permutation, reflection))["supported"])

    def test_distinct_four_point_types(self):
        convex = canonicalize(orient_text([(0, 0), (4, 0), (4, 4), (0, 4)]))
        interior = canonicalize(orient_text([(0, 0), (6, 0), (0, 6), (1, 1)]))
        self.assertNotEqual(convex["canonical_signs"], interior["canonical_signs"])
        self.assertEqual(len(convex["eligible_pivots"]), 4)
        self.assertEqual(len(interior["eligible_pivots"]), 3)

    def test_parser_and_hamming(self):
        a = "# comment\n A_(1,2,3) \n"
        b = "B_(2,1,3)\n"
        self.assertEqual(canonicalize(a)["canonical_signs"], canonicalize(b)["canonical_signs"])
        self.assertEqual(labeled_hamming_distance(a, b), 0)
        reflected = "B_(1,2,3)\n"
        self.assertEqual(labeled_hamming_distance(a, reflected), 1)
        self.assertEqual(labeled_hamming_distance(a, reflected, allow_reflection=True), 0)
        for malformed in ("", "C_(1,2,3)", "A_(0,1,2)", "A_(1,1,2)",
                          "A_(1,2,4)", "A_(1,2,3)\nB_(1,2,3)",
                          "A_(1,2,3) trailing", "A_(1,2,3)\nB_(3,2,1)"):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                canonicalize(malformed)


if __name__ == "__main__":
    unittest.main()
