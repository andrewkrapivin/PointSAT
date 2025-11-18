import re
import math
import itertools
from fractions import Fraction

def C2(k):
    return k*(k-1)//2 if k>=2 else 0

def C3(k):
    return k*(k-1)*(k-2)//6 if k>=3 else 0

def invert_rank(m, n):
    # find c: smallest c in [3..n] with C3(c) >= m
    lo, hi = 3, n
    while lo < hi:
        mid = (lo + hi) // 2
        if C3(mid) >= m:
            hi = mid
        else:
            lo = mid + 1
    c = lo
    # sanity: require C3(c) >= m and C3(c-1) < m
    r = m - C3(c-1)  # 1 <= r <= C2(c-1)
    # find b: smallest b in [2..c-1] with C2(b) >= r
    lo, hi = 2, c-1
    while lo < hi:
        mid = (lo + hi) // 2
        if C2(mid) >= r:
            hi = mid
        else:
            lo = mid + 1
    b = lo
    a = r - C2(b-1)
    return (a, b, c)

def split_line(sol):
    return [int(x) for x in re.findall(r'-?\d+', sol)]

def get_orientations(sol, n=23):
    orientations = ""
    for i in sol:
        if i > 0:
            orientations += "A_" + str(invert_rank(i,n)) + "\n"
        elif i < 0:
            orientations += "B_" + str(invert_rank(-i,n)) + "\n"
    return orientations




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
        
def parse_points(filename):
    frac_points = []
    float_points = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            tk = line.split(' ')
            frac_points.append((Fraction(float(tk[1])), Fraction(float(tk[2]))))
            float_points.append((float(tk[1]), float(tk[2])))
    return frac_points, float_points
    
def det(a, b, c):
    # return (pc.y - pa.y) * (pb.x - pa.x) - (pc.x - pa.x) * (pb.y - pa.y);
    return (c[1] - a[1]) * (b[0] - a[0]) - (c[0] - a[0]) * (b[1] - a[1])

def validate_constraint(sign, a, b, c):
    if sign == 1:
        return det(a, b, c) > 0
    else:
        return det(a, b, c) < 0

def orient(a, b, c):
    if a > b:
        t = a
        a = b
        b = t
    if b > c:
        t = b
        b = c
        c = t
    return int(a + (b-2)*(b-1)/2 + (c-3)*(c-2)*(c-1)/6)

def validate(constraint_filename, point_filename):
    constraints = parse_constraints(constraint_filename)
    frac_points, float_points = parse_points(point_filename)
    valid = True
    bad_vars = []
    for sign, vls in constraints:
        a, b, c = frac_points[vls[0]-1], frac_points[vls[1]-1], frac_points[vls[2]-1]
        float_a, float_b, float_c = float_points[vls[0]-1], float_points[vls[1]-1], float_points[vls[2]-1]
        if not validate_constraint(sign, a, b, c):
            # print(vls[0], vls[1], vls[2])
            bad_vars.append(orient(vls[0], vls[1], vls[2]))
            valid = False
    return valid, bad_vars

def get_sat_model(point_filename, n = 23):
    sat_model = []
    frac_points, _ = parse_points(point_filename)
    for (i, j, k) in itertools.combinations(range(n), 3):
        a, b, c = frac_points[i], frac_points[j], frac_points[k]
        d = det(a, b, c)
        assert d != 0
        if d > 0:
            sat_model.append(orient(i+1,j+1,k+1))
        else:
            sat_model.append(-orient(i+1,j+1,k+1))
    sat_model.sort(key=abs)
    return sat_model