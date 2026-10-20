"""Bounded planar ring checks; no repair, triangulation or source mutation.

Conservative profile: simple disjoint boundaries only (touching rings reject).
The same checks run on source coordinates and projected integer centimetres.
"""
from import_layer import BudgetExceeded, soft_limit

MAX_TOPOLOGY_CHECKS = 2_000_000  # Warn above; every check still runs.
TOPOLOGY_CEILING = 200_000_000  # CPU-time guard: an unfinished check is never skipped.


class Budget:
    def __init__(self):
        self.limit, self.ceiling, self.used = MAX_TOPOLOGY_CHECKS, TOPOLOGY_CEILING, 0
        self.threshold = min(self.limit, self.ceiling)

    def spend(self, count=1):
        # Hot path (once per segment pair): a single comparison until the next
        # threshold. The soft limit is recorded once when first crossed; settle()
        # records the final count when a ring check finishes.
        self.used += count
        if self.used > self.threshold:
            self.crossed()

    def crossed(self):
        if self.used > self.ceiling:
            raise BudgetExceeded("polygon topology check ceiling exceeded; use a smaller extract")
        self.threshold = self.ceiling
        self.settle()

    def settle(self):
        if self.used > self.limit:
            soft_limit("topology_checks", self.used, self.limit, "Polygon topology checks exceed their budget; import takes longer")


class SpatialBudget(Budget):
    """Same ring rules, with bounded spatial candidates instead of all edge pairs."""
    spatial = True


def spatial_rings(outers, inners, budget):
    try:
        return _spatial_rings(outers, inners, budget)
    finally:
        budget.settle()


def _spatial_rings(outers, inners, budget):
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree
    if not outers: raise ValueError("multipolygon requires an outer ring")
    rings = outers + inners
    polygons = []
    for ring in rings:
        budget.spend(len(ring))
        if len(ring) < 4 or ring[0] != ring[-1] or len({tuple(p) for p in ring[:-1]}) != len(ring)-1:
            raise ValueError("polygon must be a closed simple ring without repeated positions")
        polygon = Polygon(ring)
        if not polygon.is_valid or polygon.is_empty or not polygon.exterior.is_simple or polygon.area == 0:
            raise ValueError("polygon boundary self-intersects, touches or has zero area")
        polygons.append(polygon)
    tree = STRtree(polygons)
    parents = [None] * len(rings)
    for i, polygon in enumerate(polygons):
        candidates = tree.query(polygon)
        budget.spend(len(candidates))
        parent_area = float("inf")
        for j in candidates:
            if i == j: continue
            other = polygons[j]
            if polygon.exterior.intersects(other.exterior):
                raise ValueError("multipolygon boundaries intersect or touch")
            if other.area < parent_area and other.contains(polygon):
                parents[i], parent_area = int(j), other.area
    result = [[ring] for ring in outers]
    for i,parent in enumerate(parents):
        if i < len(outers):
            if parent is not None and parent < len(outers): raise ValueError("multipolygon outer areas overlap")
        else:
            if parent is None or parent >= len(outers): raise ValueError("multipolygon inner must be inside an outer, without nested holes")
            result[parent].append(rings[i])
    return result


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
    if getattr(budget, "spatial", False):
        return spatial_rings(outers, inners, budget)
    try:
        return _group_rings(outers, inners, budget)
    finally:
        budget.settle()


def _group_rings(outers, inners, budget):
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
