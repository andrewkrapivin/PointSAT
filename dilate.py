import math
import random
import copy
import numpy as np
from itertools import combinations

def parse_file(file_path):
    pairs = []
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 3:
                # Ignore the first number, store the next two as a tuple
                pair = (int(float(parts[1])*1e7), int(float(parts[2])*1e7))
                pairs.append(pair)
    return pairs

def write_file(pairs,file_path):
    with open(file_path, 'w') as f:
        for i in range(len(pairs)):
            pair = pairs[i]
            f.write(str(i+1) + " " + ' '.join(map(str, pair)))
            f.write("\n")

def det(a, b, c):
    # return (pc.y - pa.y) * (pb.x - pa.x) - (pc.x - pa.x) * (pb.y - pa.y);
    return (c[1] - a[1]) * (b[0] - a[0]) - (c[0] - a[0]) * (b[1] - a[1])

def validate_constraint(sign, a, b, c):
    if sign == 1:
        return det(a, b, c) > 0
    else:
        return det(a, b, c) < 0
        
def validate(constraints, points):
    for sign, vls in constraints:
        a, b, c = points[vls[0]-1], points[vls[1]-1], points[vls[2]-1]
        if not validate_constraint(sign, a, b, c):
            return False
    return True

def parse_constraints(filename):
    constraints = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            tk = line.split('_')
            sign = 1 if tk[0] == 'A' else -1
            vls = eval(tk[1])
            constraints.append((sign, vls))
    return constraints

def dilate(constraints,points):
    """
    Try multiple scaling factors and rounding to find the smallest integer coordinates
    that preserve orientation.
    """
    arr = np.array(points, dtype=float)
    arr -= arr.mean(axis=0)  # center around origin

    scales = np.geomspace(1e6, 1e2, num=200000)

    best_points = None
    best_scale = None

    for s in scales:
        rounded = np.round(arr / np.max(np.abs(arr)) * s).astype(int)
        candidate = [tuple(p) for p in rounded]
        if validate(constraints,candidate):
            best_points = candidate
            best_scale = s

    if best_points is None:
        raise ValueError("No integer configuration preserved orientation.")

    print(f"Best integer scale found: {best_scale:.3f}")
    return best_points

points = parse_file("645754_1136348.real")
constraints = parse_constraints("645754.or")

dilated_points = dilate(constraints,points)

write_file(dilated_points, "dilated.txt")