"""Bounded planar ring checks; no repair, triangulation or source mutation.

Conservative profile: simple disjoint boundaries only (touching rings reject).
The same checks run on source coordinates and projected integer centimetres.
"""
MAX_TOPOLOGY_CHECKS = 2_000_000


class Budget:
    def __init__(self):
        self.remaining = MAX_TOPOLOGY_CHECKS

    def spend(self, count=1):
        self.remaining -= count
        if self.remaining < 0:
            raise ValueError("polygon topology budget exceeded; use a smaller extract")


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def on_segment(a, b, p):
    return cross(a, b, p) == 0 and all(min(a[i], b[i]) <= p[i] <= max(a[i], b[i]) for i in (0, 1))


def intersects(a, b, c, d):
    if any(max(a[i], b[i]) < min(c[i], d[i]) or max(c[i], d[i]) < min(a[i], b[i]) for i in (0, 1)):
        return False
    x, y, z, w = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return (x*y < 0 and z*w < 0) or any((on_segment(a, b, c), on_segment(a, b, d), on_segment(c, d, a), on_segment(c, d, b)))


def inside(point, ring, budget):
    result = False
    for a, b in zip(ring, ring[1:]):
        budget.spend()
        if (a[1] > point[1]) != (b[1] > point[1]):
            if point[0] < (b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1]) + a[0]:
                result = not result
    return result


def group_rings(outers, inners, budget):
    """Validate boundaries and assign each inner to its unique immediate outer.

    Nested outer islands are allowed only inside a hole of their containing outer.
    Input order is retained; OSM assembly canonicalizes node IDs beforehand.
    """
    if not outers:
        raise ValueError("multipolygon requires an outer ring")
    rings = outers + inners
    edges = []
    for ring in rings:
        if len(ring) < 4 or ring[0] != ring[-1] or len({tuple(p) for p in ring[:-1]}) != len(ring)-1:
            raise ValueError("polygon must be a closed simple ring without repeated positions")
        segments = list(zip(ring, ring[1:]))
        for i, (a, b) in enumerate(segments):
            for j in range(i+1, len(segments)):
                budget.spend()
                c, d = segments[j]
                if j == i+1 or (i == 0 and j == len(segments)-1):
                    # Adjacent collinear segments may continue, but must not backtrack.
                    other = d if j == i+1 else c
                    shared = b if j == i+1 else a
                    first = a if j == i+1 else b
                    if cross(first, shared, other) == 0 and sum((first[k]-shared[k])*(other[k]-shared[k]) for k in (0,1)) > 0:
                        raise ValueError("polygon boundary backtracks")
                elif intersects(a, b, c, d):
                    raise ValueError("polygon boundary self-intersects or touches")
        if sum(cross(ring[0], a, b) for a, b in segments) == 0:
            raise ValueError("polygon has zero area")
        edges.append(segments)
    for i, first in enumerate(edges):
        for second in edges[i+1:]:
            for a, b in first:
                for c, d in second:
                    budget.spend()
                    if intersects(a, b, c, d):
                        raise ValueError("multipolygon boundaries intersect or touch")
    # No intersections remain, so one vertex determines strict containment.
    budget.spend(len(rings) * len(rings))  # Bound allocation before the containment matrix.
    contains = [[False] * len(rings) for _ in rings]
    for i, ring in enumerate(rings):
        for j, other in enumerate(rings):
            if i != j:
                contains[i][j] = inside(other[0], ring, budget)
    parents = []
    for j in range(len(rings)):
        containers = [i for i in range(len(rings)) if contains[i][j]]
        closest = [i for i in containers if not any(i != k and contains[i][k] for k in containers)]
        if len(closest) > 1:
            raise ValueError("ambiguous multipolygon containment")
        parents.append(closest[0] if closest else None)
    result = [[ring] for ring in outers]
    for i, parent in enumerate(parents):
        if i < len(outers):
            if parent is not None and parent < len(outers):
                raise ValueError("multipolygon outer areas overlap")
        else:
            if parent is None or parent >= len(outers):
                raise ValueError("multipolygon inner must be inside an outer, without nested holes")
            result[parent].append(rings[i])
    return result
