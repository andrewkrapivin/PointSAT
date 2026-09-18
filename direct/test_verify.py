#!/usr/bin/env python3
"""Public-CLI boundary and exact-arithmetic checks for the exhaustive verifier."""
import argparse
import json
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", default="direct/verify")
    args = parser.parse_args()
    count = 0

    def verify(text, code=0, options=()):
        nonlocal count
        result = subprocess.run([args.verify, "--input", "-", "--gon", "0", "--hole", "0", *options],
                                input=text, capture_output=True, text=True, check=False)
        assert result.returncode == code, (text, result.returncode, result.stdout, result.stderr)
        count += 1
        return json.loads(result.stdout) if result.stdout else None

    assert verify("1\n5 7\n")["min_determinant"] is None
    assert verify("2\n1 1\n1 1\n", 1)["duplicate_pairs"] == 1
    assert verify("3\n0 0\n1 1\n2 2\n", 1)["collinear_triples"] == 1
    v = verify("3\n-1000000000000000000 -1000000000000000000\n1000000000000000000 -1000000000000000000\n0 1000000000000000000\n")
    assert v["min_determinant"] == 4*10**36
    assert v["bbox_area"] == 4*10**36
    cap = "6\n" + "".join(f"{i} {-i*i}\n" for i in range(6))
    assert verify(cap, 1, ("--cap", "5"))["convex_caps"] == 6
    cup = "6\n" + "".join(f"{i} {i*i}\n" for i in range(6))
    assert verify(cup, 0, ("--cap", "5"))["convex_caps"] == 0
    for text in ("", "0\n", "65\n", "2\n1 2\n", "1\n1 2\n3 4\n", "1\n1.2 3\n",
                 "1\n1000000000000000001 0\n", "1\n-9223372036854775808 0\n"):
        verify(text, 2)
    verify("1\n0 0\n", 2, ("--gon", "2"))
    print(json.dumps({"status": "passed", "cli_cases": count}))


if __name__ == "__main__":
    main()
