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
                pair = (int(parts[1]), int(parts[2]))
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

def objective_spread(points):
    """Compactness objective: area of bounding box."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    return width * height

def local_search_annealing(constraints,points,
                           initial_temp=10000.0,
                           cooling_rate=0.999,
                           step_size=100,
                           min_temp=1,
                           max_iter=400000,
                           objective_func=objective_spread):
    """
    Simulated annealing: minimize spread while preserving orientation.
    """
    current = copy.deepcopy(points)
    best = copy.deepcopy(points)
    best_score = current_score = objective_func(points)
    T = initial_temp
    iter_count = 0

    while T > min_temp and iter_count < max_iter:
        iter_count += 1
        i = random.randrange(len(current))
        x, y = current[i]

        # Adaptive step size: smaller as temperature cools
        scaled_step = max(1, int(step_size * (T / initial_temp)))
        dx = random.randint(-scaled_step, scaled_step)
        dy = random.randint(-scaled_step, scaled_step)
        new_point = (x + dx, y + dy)
        new_points = current[:i] + [new_point] + current[i+1:]

        if not validate(constraints,new_points):
            continue  # skip if orientation constraint fails

        new_score = objective_func(new_points)
        delta = new_score - current_score

        # Accept if better or probabilistically if worse
        if delta < 0 or random.random() < math.exp(-delta / T):
            current = new_points
            current_score = new_score
            if new_score < best_score:
                best = copy.deepcopy(new_points)
                best_score = new_score

        T *= cooling_rate

    return best

points = parse_file("645754-new1.txt")
constraints = parse_constraints("645754.or")

dilated_points = local_search_annealing(constraints,points)

write_file(dilated_points, "optimized.txt")