"""Exact projected flippability with reusable SAT state and safe clause screening."""
import time
from pysat.formula import CNF
from pysat.solvers import Cadical195


def load_model_str(model):
    model_map, order = {}, []
    for line in model.splitlines():
        fields = line.split()
        if not fields or fields[0] in ('c', 'p', 's'):
            continue
        if fields[0] == 'v':
            fields = fields[1:]
        for field in fields:
            lit = int(field)
            if not lit:
                continue
            var = abs(lit)
            if var in model_map:
                if model_map[var] != lit:
                    raise ValueError(f"contradictory literals for variable {var}")
                continue
            model_map[var] = lit
            order.append(var)
    return model_map, order


def load_model(path):
    with open(path, encoding='utf-8') as file:
        return load_model_str(file.read())


class FlippabilityChecker:
    """Keep CNF/solver once per worker; learned clauses remain globally valid.

    A projected-only clause with one true literal forbids flipping that literal.
    A complete SAT witness with no singly supported clause remains a witness
    after a flip. Only the remaining cases need individual SAT queries.
    """
    def __init__(self, cnf_str, witness_screening=False):
        self.cnf = CNF(from_string=cnf_str)
        self.clauses = []
        for clause in self.cnf.clauses:
            literals = set(clause)
            if any(-lit in literals for lit in literals):
                continue
            self.clauses.append(tuple(literals))
        self.solver = Cadical195(bootstrap_with=self.cnf.clauses)
        self.last_stats = {}
        self._projection = None
        self._pure_clauses = []
        # Scanning all auxiliary clauses cost more than the few SAT calls it
        # saved on the PointSAT benchmarks. Keep this optional for other CNFs.
        self.witness_screening = witness_screening

    def close(self):
        if self.solver is not None:
            self.solver.delete()
            self.solver = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def check(self, model_str):
        start = time.perf_counter()
        model_map, order = load_model_str(model_str)
        projection = frozenset(order)
        max_variable = max(self.cnf.nv, max(order, default=0))
        assumptions = [model_map[var] for var in order]
        if not self.solver.solve(assumptions=assumptions):
            raise ValueError("flippability requires a satisfiable projected model")
        truth = bytearray(max_variable + 1)
        for lit in self.solver.get_model():
            if abs(lit) <= max_variable:
                truth[abs(lit)] = lit > 0
        for lit in assumptions:
            truth[abs(lit)] = lit > 0

        if self._projection != projection:
            self._pure_clauses = [clause for clause in self.clauses
                                  if all(abs(lit) in projection for lit in clause)]
            self._projection = projection

        blocked = set()
        for clause in self._pure_clauses:
            support = 0
            for lit in clause:
                if truth[abs(lit)] == (lit > 0):
                    if support:
                        support = 0
                        break
                    support = lit
            if support:
                blocked.add(abs(support))

        unresolved = projection - blocked
        critical = set(unresolved)
        if unresolved and self.witness_screening:
            critical.clear()
            for clause in self.clauses:
                support = 0
                for lit in clause:
                    if truth[abs(lit)] == (lit > 0):
                        if support:
                            support = 0
                            break
                        support = lit
                if support and abs(support) in unresolved:
                    critical.add(abs(support))

        flippable = set(unresolved - critical)
        witness_flips = len(flippable)
        queries = 0
        for index, lit in enumerate(assumptions):
            if abs(lit) not in critical:
                continue
            assumptions[index] = -lit
            queries += 1
            if self.solver.solve(assumptions=assumptions):
                flippable.add(abs(lit))
            assumptions[index] = lit
        self.last_stats = {'variables': len(order), 'screened_nonflippable': len(blocked),
                           'witness_flippable': witness_flips, 'flip_sat_calls': queries,
                           'initial_sat_calls': 1, 'seconds': time.perf_counter() - start}
        return flippable, [model_map[var] for var in order if var not in flippable]


def check_flippable(cnf_str, model_str):
    """Compatibility API; repeated callers should reuse FlippabilityChecker."""
    with FlippabilityChecker(cnf_str) as checker:
        return checker.check(model_str)
