import re
import sys
import itertools
import pprint

def triple_to_orient(a,b,c):
    assert a < b
    assert b < c
    return a + (b-2)*(b-1)//2 + (c-3)*(c-2)*(c-1)//6

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

def compute_hull_layers_fast(n, orient):
    """
    Computes the sizes of convex hull layers for n points using
    the Gift Wrapping (Jarvis March) algorithm. 
    Complexity: O(N^2) in the worst case (sum of layers),
    which is significantly faster than the O(N^4) naive approach.
    """
    
    # --- Helper: Orientation Wrapper ---
    # Handles index permutations to satisfy the strict orient(i < j < k) requirement.
    def is_ccw(a, b, c):
        # Sort indices to match function signature
        sorted_indices = sorted([a, b, c])
        i, j, k = sorted_indices[0], sorted_indices[1], sorted_indices[2]
        
        val = orient(i, j, k)
        
        # Determine permutation parity
        # (a,b,c) -> (i,j,k)
        # Even swaps: orientation is same. Odd swaps: orientation is inverted.
        perm = [a, b, c]
        swaps = 0
        if perm[0] > perm[1]: 
            perm[0], perm[1] = perm[1], perm[0]; swaps += 1
        if perm[1] > perm[2]: 
            perm[1], perm[2] = perm[2], perm[1]; swaps += 1
        if perm[0] > perm[1]: 
            perm[0], perm[1] = perm[1], perm[0]; swaps += 1
            
        return val if (swaps % 2 == 0) else not val

    # --- Helper: Find one Hull Layer ---
    def get_convex_hull(points_set):
        points = list(points_set)
        if len(points) < 3:
            return points

        # 1. Find a starting point guaranteed to be on the Hull.
        # We pick an arbitrary reference P0, and find the point 'start_node'
        # that is "most right" (clockwise) relative to P0.
        p0 = points[0]
        start_node = points[1]
        
        for i in range(2, len(points)):
            candidate = points[i]
            # If candidate is to the Right (not CCW) of p0->start_node, it's better.
            if not is_ccw(p0, start_node, candidate):
                start_node = candidate
                
        # 2. Jarvis March (Gift Wrapping)
        hull = []
        current = start_node
        
        while True:
            hull.append(current)
            
            # Pick an initial guess for the next point
            # We need a point that is distinct from 'current'
            next_p = points[0]
            if next_p == current:
                next_p = points[1]
            
            # Find the point that is "most right" relative to 'current'
            # i.e., all other points must be to the Left (CCW) of current->next_p
            for p in points:
                if p == current or p == next_p:
                    continue
                    
                # If p is to the Right of current->next_p, then p is a better hull candidate
                if not is_ccw(current, next_p, p):
                    next_p = p
            
            current = next_p
            
            # If we wrapped around to the start, we are done with this layer
            if current == start_node:
                break
                
        return hull

    # --- Main Peeling Loop ---
    current_points = set(range(1, n + 1))
    layer_sizes = []

    while current_points:
        # Get vertices on the current convex hull
        hull_layer = get_convex_hull(current_points)
        
        # Record size
        layer_sizes.append(len(hull_layer))
        
        # Remove hull points (Peel the onion)
        for p in hull_layer:
            current_points.remove(p)
            
    return layer_sizes

sols = []

with open(sys.argv[1], 'r') as file:
    for i, line in enumerate(file):
        sols.append([int(x) for x in re.findall(r'-?\d+', line)])

layers_set = set()
layers_count = dict()

n = 23

index = 0
for sol in sols:
    hull_layer = tuple(compute_hull_layers_fast(n, lambda a,b,c : sol[triple_to_orient(a,b,c)-1] > 0))
    layers_set.add(hull_layer)
    if hull_layer in layers_count:
        layers_count[hull_layer] += 1
    else:
        layers_count[hull_layer] = 1

print(f"Number of distinct layer sizes: {len(layers_set)}")
pprint.pprint(layers_count)

print(len(sols))