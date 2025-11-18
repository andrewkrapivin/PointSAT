from pysat.formula import CNF
from pysat.solvers import Cadical195
import sys

def load_model(path):
    """Read literals from DIMACS-style model file."""
    model_map = {}
    order = []  # preserve variable order
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('c') or line.startswith('p'):
                continue
            for lit in line.split():
                if lit == 'v':
                    continue
                lit = int(lit)
                if lit == 0:
                    continue
                var = abs(lit)
                model_map[var] = lit
                order.append(var)
    return model_map, order

def load_model_str(model):
    model_map = {}
    order = []
    for line in model.splitlines():
        line = line.strip()
        # print(line)
        if not line or line.startswith('c') or line.startswith('p'):
            continue
        for lit in line.split():
            if lit == 'v':
                continue
            # print(lit)
            lit = int(lit)
            if lit == 0:
                continue
            var = abs(lit)
            model_map[var] = lit
            order.append(var)
    return model_map, order

# def check_flippable(cnf_path, model_path):
def check_flippable(cnf_str, model_str):
    # cnf = CNF(from_file=cnf_path)
    cnf = CNF(from_string=cnf_str)

    # model_map, order = load_model(model_path)
    # print(model_str)
    model_map, order= load_model_str(model_str)
    n = len(model_map)

    assumptions = [model_map[v] for v in order]
    
    flippable = set()
    
    with Cadical195(bootstrap_with=cnf.clauses) as solver:
        for i in range(len(assumptions)):
            original_lit = assumptions[i]
            var = abs(original_lit)
            
            assumptions[i] = -original_lit
            
            if solver.solve(assumptions=assumptions):
                flippable.add(var)
            
            assumptions[i] = original_lit

    nonflippable = []
    for v in order:
        if v not in flippable:
            nonflippable.append(model_map[v])
    return flippable, nonflippable


    # print(f"\nTotal flippable: {len(flippable)} / {n}")

    # nonflippable_path = "nonflippable_lits.txt"
    # with open("nonflippable_lits.txt", "w") as f:
    #     for v in order:
    #         if v not in flippable:
    #             f.write(f"{model_map[v]} 0\n")

    # print(f"Wrote non-flippable literals to: {nonflippable_path}")

# if __name__ == "__main__":
#     if len(sys.argv) != 3:
#         print("Usage: python flippable2.py formula.cnf assignment.v")
#         sys.exit(1)
#     check_flippable(sys.argv[1], sys.argv[2])