"""Explicit signed projection between arbitrary CNF variables and point triples."""
import itertools
import json
from pathlib import Path


class OrientationMap:
    def __init__(self, filename, n):
        data = json.loads(Path(filename).read_text())
        if data['n'] != n:
            raise ValueError('Orientation-map n differs from pipeline n')
        self.entries = []
        seen, expected = set(), set(itertools.combinations(range(1, n+1), 3))
        for entry in data['entries']:
            triple, literal = tuple(entry['triple']), entry['literal']
            if triple not in expected:
                raise ValueError(f'Expected a sorted, distinct triple in1..n: {triple}')
            if triple in seen or not isinstance(literal, int) or not literal:
                raise ValueError('Duplicate triple or invalid signed CNF variable in map')
            seen.add(triple)
            a, b, c = triple
            rank = a + (b-1)*(b-2)//2 + (c-1)*(c-2)*(c-3)//6
            self.entries.append((triple, literal, rank))
        if seen != expected:
            raise ValueError('Orientation map must cover every point triple exactly once')
        self.variables = sorted({abs(lit) for _, lit, _ in self.entries})
        self.rank_to_variable = {rank: abs(literal) for _, literal, rank in self.entries}
        if data.get('primary_variables', len(self.variables)) != len(self.variables):
            raise ValueError('primary_variables count differs from the map projection')

    def orientations(self, model):
        assignment = {abs(lit): lit for lit in model}
        return ''.join(f"{'A' if assignment[abs(lit)]*lit > 0 else 'B'}_{triple}\n"
                       for triple, lit, _ in self.entries if abs(lit) in assignment)

    def project(self, colex_model):
        """Return a primary CNF model, or explicit orbit-consistency conflicts."""
        actual = {abs(lit): 1 if lit > 0 else -1 for lit in colex_model}
        assignment, origins, conflicts = {}, {}, []
        for triple, literal, rank in self.entries:
            variable = abs(literal)
            value = actual[rank] * (1 if literal > 0 else -1)
            if variable in assignment and assignment[variable] != value:
                conflicts.append({'variable': variable, 'first_triple': origins[variable], 'conflicting_triple': triple})
            else:
                assignment[variable] = value
                origins.setdefault(variable, triple)
        if conflicts:
            return None, conflicts
        return [variable*assignment[variable] for variable in self.variables], []
