"""City road rules on projected source-metre features (Editor-only, current v1).

Lane-based widths, dual-carriageway merging, explicit sidewalks, road markings
and the paint segment bound. Every rule keeps every source ID: absorbed ways
move into the `_city_sources` of the road that represents them.
"""
from collections import Counter, defaultdict
import math
import re

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from osm_extract import PEDESTRIAN, LEAD_M

LANE_M = 3.25  # Source metres per tagged lane, plus LANE_MARGIN_M for the edges.
LANE_MARGIN_M = 0.5
MERGE_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary")
MEDIAN_M = (0.5, 25.0)  # Inner-edge gap of a dual carriageway, source metres.
SAMPLE_M = 5.0
OVERLAP = 0.7
PAIR_M = 50.0
RUNG_FACTOR = 3.0  # A median or diagonal turn link up to 3 × the separation is a rung.
ALIGN_M = 10.0  # Aligned nodes: along-road offset within max(10 m, separation).
VIRTUAL = -1  # An aligned node pair bounding a merge (no source piece between them).
RUNGLESS = ("motorway", "trunk")
LOOP_M = 150.0  # A road looping back onto one merged node is absorbed up to this length.  # Pairs between ramps may merge without a real rung.
ANTIPARALLEL = -0.9
MAX_LANES = 8
NO_SIDEWALK = ("motorway", "trunk", "service", "track")
SIDEWALK_CLASSES = ("primary", "secondary", "tertiary", "residential")
URBAN = ("residential", "commercial", "retail", "industrial", "education", "religious")
FOOTWAY_REACH_M = 8.0
CROSSWALK_M = 15.0
MARKED = {"motorway": 4, "trunk": 4, "primary": 4, "secondary": 2, "tertiary": 2,
          "motorway_link": None, "trunk_link": None, "primary_link": None, "secondary_link": None, "tertiary_link": None,
          "unclassified": None, "residential": None}
# MapKit (road_paint.rs, road_style.rs): a marked road's paint path segments in
# a cell plus those of its two-arm neighbours may not exceed 128. Counted here
# for whole records, so the bound holds for any cell size.
PAINT_SEGMENTS = 128
RECORD_SEGMENTS = 42  # A record with marked two-arm neighbours: three fit in 128.
TURN_SLACK = 0.005  # Radians: map-centimetre rounding of the adopted vertices.
SERVICE_PAINT = ("parking_aisle", "driveway", "drive-through")
STUB_M = 15.0
ROAD_FLOOR_CM = 150  # Editor adoption floor (import_units.gd), raises paint radii.


def tags(feature):
    return feature["properties"].get("_city_road_tags", {})


def lanes(road_tags):
    value = road_tags.get("lanes", "")
    if re.fullmatch(r"[1-9][0-9]?", value) and int(value) <= 16:
        return int(value)
    return None


def lane_width(road_tags):
    """Source metres of a road with a lane count and no width tag, else None."""
    count = lanes(road_tags)
    return round(count * LANE_M + LANE_MARGIN_M, 2) if count else None


def oneway(road_tags):
    """+1 one-way along the geometry, -1 against it, 0 two-way."""
    value = road_tags.get("oneway", "")
    if value in ("yes", "true", "1"): return 1
    if value in ("-1", "reverse"): return -1
    if value in ("no", "false", "0"): return 0
    if road_tags.get("highway") == "motorway" or road_tags.get("junction") in ("roundabout", "circular"): return 1
    return 0


def ground(feature, geometry):
    p = feature["properties"]
    return geometry.geom_type == "LineString" and p.get("road_kind", "ground") == "ground" and "elevations_m" not in p


def driving(feature, geometry):
    """A ground vehicle road that stays a road record."""
    p = feature["properties"]
    return ground(feature, geometry) and tags(feature).get("highway") not in PEDESTRIAN and not p.get("_city_ground_paint")


def fixed(feature):
    p = feature["properties"]
    return "osm_node_refs" in p or "_city_estimated_m" in p


def end_refs(feature):
    """Ordinary source end refs (int or None); explicit graphs return None."""
    p = feature["properties"]
    if "osm_node_refs" in p: return None
    refs = p.get("_city_refs")
    if refs: return [refs[0], refs[-1]]
    ends = p.get("_city_ends")
    if ends: return [_ref(e) if e is not None else None for e in ends]
    return None


def _ref(value):
    """Source node refs as ints; crop cut refs stay text."""
    return int(value) if isinstance(value, str) and value.isdigit() else value


def _tangents(line, distances, sign=1.0):
    length = line.length
    a = shapely.line_interpolate_point(line, np.clip(distances - 1.0, 0, length))
    b = shapely.line_interpolate_point(line, np.clip(distances + 1.0, 0, length))
    d = shapely.get_coordinates(b) - shapely.get_coordinates(a)
    n = np.linalg.norm(d, axis=1)
    n[n == 0] = 1
    return d / n[:, None] * sign


def _samples(line):
    count = max(1, int(line.length // SAMPLE_M))
    distances = (np.arange(count) + 0.5) * line.length / count
    return distances, shapely.line_interpolate_point(line, distances)


def _compatible(p, q):
    a, b = tags(p), tags(q)
    if a.get("highway") != b.get("highway"): return False
    return all(a.get(k) == b.get(k) for k in ("name", "ref") if k in a and k in b)


class DualCarriageways:
    """Merge anti-parallel one-way pairs ("ladders") into one two-way road.

    The merged centreline is the midline: carriageway A's vertices move halfway
    towards B, A's nodes move with them (incident roads follow) and B's rung
    nodes are renamed to A's. B, median rungs and U-turn links are absorbed into
    the merged road's sources. A merge runs only between rungs (a shared converge
    node or one short median piece) and stops a lead length before any structure
    anchor or explicit-height node.
    """

    def __init__(self, items, spend=lambda count=1: None):
        self.items = list(items)
        self.spend = spend
        self.stats = Counter()
        self.reasons = Counter()  # Diagnostics only: why cells were not merged.

    def run(self):
        items = self.items
        self.alive = [True] * len(items)
        self.candidates = [i for i, (f, g) in enumerate(items) if self.candidate(f, g)]
        if len(self.candidates) < 2:
            return items
        self.prepare()
        self.pair()
        self.chain()
        pairs = Counter()
        for i in self.candidates:
            for j, length in self.partner_length[i].items():
                a, b = self.chain_of[i], self.chain_of[j]
                if a != b: pairs[(min(a, b), max(a, b))] += length
        self.used = set()
        for (a, b), length in sorted(pairs.items(), key=lambda item: (-item[1], item[0])):
            if length >= PAIR_M:
                self.ladder(a, b)
        return [item for i, item in enumerate(items) if self.alive[i]]

    @staticmethod
    def candidate(f, g):
        p = f["properties"]
        t = tags(f)
        refs = p.get("_city_refs")
        return (driving(f, g) and not fixed(f) and not p.get("_city_level_structure") and t.get("highway") in MERGE_CLASSES
                and oneway(t) != 0 and t.get("junction") not in ("roundabout", "circular") and refs and len(refs) == len(g.coords)
                and refs[0] != refs[-1] and None not in refs)

    def index(self):
        """Ordinary ground driving ends and the driving-road index, rebuilt
        after each merge (splits and moved followers)."""
        items = self.items
        self.incident = defaultdict(list)  # ref -> [(index, end)].
        for i, (f, g) in enumerate(items):
            if not self.alive[i] or not driving(f, g) or fixed(f): continue
            for end, ref in enumerate(end_refs(f) or []):
                if ref is not None: self.incident[ref].append((i, end))
        self.drive = [i for i, (f, g) in enumerate(items) if self.alive[i] and driving(f, g)]
        self.drive_tree = STRtree([items[i][1] for i in self.drive])
        self.extra = []  # Pieces split or moved by merges since: a small second index.
        self.extra_tree = STRtree([])

    def reindex(self, changed):
        """After a merge: index its split pieces and moved followers too."""
        for i in changed:
            f, g = self.items[i]
            if i >= len(self.alive) or not self.alive[i]: continue
            for end, ref in enumerate(end_refs(f) or []):
                if ref is not None and (i, end) not in self.incident[ref]: self.incident[ref].append((i, end))
        self.extra = sorted(set(self.extra) | set(changed))
        self.extra_tree = STRtree([self.items[i][1] for i in self.extra])

    def driving_near(self, geometry):
        """Driving roads whose (possibly moved) geometry may meet `geometry`."""
        hits = {self.drive[h] for h in self.drive_tree.query(geometry)} | {self.extra[h] for h in self.extra_tree.query(geometry)}
        return sorted(i for i in hits if self.alive[i])

    def prepare(self):
        items = self.items
        anchors = {}
        structures = []
        for i, (f, g) in enumerate(items):
            if g.geom_type != "LineString": continue
            p = f["properties"]
            # Anchors: explicit graphs, estimated and explicit structures. Ground
            # walking loops are painted and level structures lie flat on the map.
            walking_loop = ground(f, g) and "_city_estimated_m" not in p and tags(f).get("highway") in PEDESTRIAN
            if (fixed(f) or not ground(f, g)) and not walking_loop:
                structures.append(g)
                refs = p.get("osm_node_refs") or p.get("_city_refs") or []
                for ref, point in zip(refs, g.coords):
                    if ref is not None: anchors[_ref(ref)] = point
                for ref, point in zip(end_refs(f) or [], (g.coords[0], g.coords[-1])):
                    if ref is not None: anchors[_ref(ref)] = point
        self.index()
        self.anchors = set(anchors)
        # Structures, explicit heights and graph roads: no merge within a lead length.
        self.structures = structures
        self.structure_tree = STRtree(structures)
        self.anchor_points = [Point(p) for _, p in sorted(anchors.items(), key=lambda item: str(item[0]))]
        self.anchor_tree = STRtree(self.anchor_points)
        polygons = [(f, g) for f, g in items if g.geom_type != "LineString"]
        self.blockers = [g for f, g in polygons if not f["properties"].get("osm_region") or f["properties"].get("landuse") in ("water", "wetland")]
        self.blocker_tree = STRtree(self.blockers)
        # The median test uses tagged widths; an estimated carriageway counts
        # as one lane, so an inflated estimate cannot hide a pair.
        self.width = {i: float(items[i][0]["properties"].get("width_m", 8)) for i in self.candidates}
        self.edge = {i: LANE_M + LANE_MARGIN_M if items[i][0]["properties"].get("_city_width_estimate") else self.width[i] for i in self.candidates}
        self.sign = {i: oneway(tags(items[i][0])) for i in self.candidates}

    def travel(self, i):
        """Start and end refs in travel direction."""
        refs = self.items[i][0]["properties"]["_city_refs"]
        return (refs[0], refs[-1]) if self.sign[i] > 0 else (refs[-1], refs[0])

    def pair(self):
        items = self.items
        geometries = [items[i][1] for i in self.candidates]
        tree = STRtree(geometries)
        widest = max(self.edge.values())
        self.matched = {}
        self.partner_length = {i: Counter() for i in self.candidates}
        for i in self.candidates:
            f, g = items[i]
            distances, points = _samples(g)
            own = _tangents(g, distances, self.sign[i])
            best = np.full(len(points), np.inf)
            match = np.full(len(points), -1)
            reach = MEDIAN_M[1] + self.edge[i] / 2 + widest / 2
            near = tree.query(g, predicate="dwithin", distance=reach)
            self.spend(len(near) + len(points))
            for k in sorted(near):
                j = self.candidates[k]
                if j == i or not _compatible(f, items[j][0]): continue
                h = items[j][1]
                dist = shapely.distance(h, points)
                gap = dist - self.edge[i] / 2 - self.edge[j] / 2
                ok = (gap >= MEDIAN_M[0]) & (gap <= MEDIAN_M[1])
                if not ok.any(): continue
                theirs = _tangents(h, shapely.line_locate_point(h, points), self.sign[j])
                ok &= (own * theirs).sum(axis=1) < ANTIPARALLEL
                better = ok & (dist < best)
                best[better] = dist[better]
                match[better] = j
            step = g.length / len(points)
            self.matched[i] = match
            for j in match[match >= 0]:
                self.partner_length[i][int(j)] += step

    def chain(self):
        """Travel-direction chains of compatible candidates (unique, < 45° turns)."""
        items = self.items
        starts = defaultdict(list)
        for i in self.candidates:
            starts[self.travel(i)[0]].append(i)
        def direction(i, at_end):
            g = items[i][1]
            coords = list(g.coords) if self.sign[i] > 0 else list(g.coords)[::-1]
            a, b = (coords[-2], coords[-1]) if at_end else (coords[0], coords[1])
            v = np.subtract(b, a)
            return v / (np.linalg.norm(v) or 1)
        successor, predecessor = {}, defaultdict(list)
        for i in self.candidates:
            options = [j for j in starts[self.travel(i)[1]] if j != i and _compatible(items[i][0], items[j][0])
                       and float(np.dot(direction(i, True), direction(j, False))) > math.cos(math.radians(45))]
            if len(options) == 1:
                successor[i] = options[0]
                predecessor[options[0]].append(i)
        successor = {i: j for i, j in successor.items() if len(predecessor[j]) == 1}
        has_previous = set(successor.values())
        self.chain_of, self.chains = {}, []
        for i in sorted(self.candidates, key=lambda i: (i in has_previous, i)):
            if i in self.chain_of: continue
            path = [i]
            self.chain_of[i] = len(self.chains)
            while path[-1] in successor and successor[path[-1]] not in self.chain_of:
                path.append(successor[path[-1]])
                self.chain_of[path[-1]] = len(self.chains)
            self.chains.append(path)

    def nodes(self, path):
        refs = [self.travel(path[0])[0]] + [self.travel(i)[1] for i in path]
        return refs

    def point(self, i, ref):
        f, g = self.items[i]
        refs = f["properties"]["_city_refs"]
        return g.coords[0] if refs[0] == ref else g.coords[-1]

    def safe(self, ref, point):
        if ref in self.anchors: return False
        if not self.anchor_points: return True
        near = self.anchor_tree.query(Point(point).buffer(LEAD_M))
        return not any(self.anchor_points[k].distance(Point(point)) < LEAD_M for k in near)

    def line(self, path):
        coords = []
        for i in path:
            c = list(self.items[i][1].coords)
            if self.sign[i] < 0: c.reverse()
            coords.extend(c if not coords else c[1:])
        return LineString(coords)


    def runs(self, chain):
        """Unused, still consecutive pieces of a chain (earlier merges move or
        rename the nodes of the roads they touch)."""
        runs, run = [], []
        for i in chain:
            if i in self.used or not self.alive[i] or run and self.travel(run[-1])[1] != self.travel(i)[0]:
                if run: runs.append(run)
                run = [] if i in self.used or not self.alive[i] else [i]
            else:
                run.append(i)
        if run: runs.append(run)
        return runs

    def ladder(self, ca, cb):
        for A in self.runs(self.chains[ca]):
            for B in self.runs(self.chains[cb]):
                if any(i in self.used for i in A + B): continue
                if any(self.chain_of.get(int(j)) == cb for i in A for j in self.matched[i] if j >= 0 and int(j) in B):
                    self.pair_runs(A, B, ca, cb)

    def pair_runs(self, A, B, ca, cb):
        items = self.items
        a_nodes, b_nodes = self.nodes(A), self.nodes(B)
        if len(set(a_nodes)) != len(a_nodes) or len(set(b_nodes)) != len(b_nodes): return
        b_index = {ref: k for k, ref in enumerate(b_nodes)}
        position = {ref: self.point(A[max(0, k - 1)], ref) for k, ref in enumerate(a_nodes)}
        position.update({ref: self.point(B[max(0, k - 1)], ref) for k, ref in enumerate(b_nodes)})
        b_line = self.line(B)
        members = set(A) | set(B)
        rungs = []  # (A node index, B node index, connector item, None (converge) or VIRTUAL)
        b_stations = [b_line.project(Point(position[ref])) for ref in b_nodes]
        for k, ref in enumerate(a_nodes):
            if ref in b_index:
                rungs.append((k, b_index[ref], None))
                continue
            separation = b_line.distance(Point(position[ref]))
            best = None
            for i, end in self.incident.get(ref, []):
                if i in members or not self.alive[i] or i in self.used: continue
                other = end_refs(items[i][0])[1 - end]
                if other in b_index and other not in a_nodes:
                    length = items[i][1].length
                    if length <= RUNG_FACTOR * separation and (best is None or (length, i) < best[:2]):
                        best = (length, i, b_index[other])
            if best:
                rungs.append((k, best[2], best[1]))
                continue
            # Aligned nodes across the median bound a merge too (one real rung
            # per run still required below class trunk).
            station = b_line.project(Point(position[ref]))
            j = min(range(len(b_nodes)), key=lambda n: (abs(b_stations[n] - station), n))
            if abs(b_stations[j] - station) <= max(ALIGN_M, separation) and b_nodes[j] not in a_nodes:
                rungs.append((k, j, VIRTUAL))
        # Anti-parallel: B positions decrease along A. Keep the most rungs,
        # preferring real ones (longest decreasing chain, weighted).
        score, previous = [], []
        for n, (k, j, c) in enumerate(rungs):
            weight = 1 if c == VIRTUAL else 2
            best = (weight, -1)
            for m in range(n):
                if rungs[m][1] > j and score[m] + weight > best[0]: best = (score[m] + weight, m)
            score.append(best[0]); previous.append(best[1])
        ordered = []
        n = max(range(len(rungs)), key=lambda n: (score[n], -n)) if rungs else -1
        while n >= 0:
            ordered.append(rungs[n]); n = previous[n]
        ordered.reverse()
        run = []
        for r0, r1 in zip(ordered, ordered[1:]):
            links = self.cell(A, B, a_nodes, b_nodes, position, r0, r1, ca, cb)
            if links is not None:
                run.append((r0, r1, links))
                continue
            if run: self.merge(A, B, a_nodes, b_nodes, position, run)
            run = []
        if run: self.merge(A, B, a_nodes, b_nodes, position, run)

    def cell(self, A, B, a_nodes, b_nodes, position, r0, r1, ca, cb):
        """Median links absorbed by a valid cell between rungs r0 and r1, else None."""
        items = self.items
        (k0, j0, c0), (k1, j1, c1) = r0, r1
        a_cell, b_cell = A[k0:k1], B[j1:j0]
        connectors = [c for c in (c0, c1) if c is not None and c != VIRTUAL]
        if not a_cell or not b_cell or any(i in self.used or not self.alive[i] for i in a_cell + b_cell + connectors):
            self.reasons["used"] += 1
            return None
        refs = a_nodes[k0:k1 + 1] + b_nodes[j1:j0 + 1]
        if not all(self.safe(ref, position[ref]) for ref in refs):
            self.reasons["structure"] += 1
            return None
        for side, other in ((a_cell, cb), (b_cell, ca)):
            total = sum(items[i][1].length for i in side)
            covered = sum(items[i][1].length / len(self.matched[i]) * sum(1 for j in self.matched[i] if j >= 0 and self.chain_of[int(j)] == other)
                          for i in side)
            if covered < OVERLAP * total:
                self.reasons["overlap"] += 1
                return None
        ring = list(self.line(a_cell).coords) + list(self.line(b_cell).coords)
        strip = Polygon(ring)
        if not strip.is_valid: strip = shapely.make_valid(strip)
        lead = strip.buffer(LEAD_M)
        if any(self.anchor_points[k].intersects(lead) for k in self.anchor_tree.query(lead)) or \
                any(self.structures[k].intersects(lead) for k in self.structure_tree.query(lead)):
            self.reasons["structure"] += 1
            return None
        core = strip.buffer(-0.5)
        if not core.is_empty:
            hits = self.blocker_tree.query(core, predicate="intersects")
            self.spend(len(hits))
            if any(self.blockers[h].intersection(core).area > 1.0 for h in hits):
                self.reasons["building"] += 1
                return None
        nodes = set(refs)
        inner, outer = strip.buffer(-1.0), strip.buffer(1.0)
        hits = self.driving_near(strip)
        self.spend(len(hits))
        inside, blocking = [], []
        for i in hits:
            if i in a_cell or i in b_cell or i in connectors or not self.alive[i]: continue
            f, g = items[i]
            if i not in self.used and not fixed(f) and end_refs(f) and g.difference(outer).length <= 0.2 * g.length:
                inside.append(i)
            elif not inner.is_empty and g.intersection(inner).length > 2.0:
                blocking.append(i)
        # Median links, U-turns and junction pieces between the carriageways are
        # absorbed when they connect only to the ladder's own nodes.
        members = set(inside)
        changed = True
        while changed:
            changed = False
            for i in sorted(members):
                for ref in end_refs(items[i][0]):
                    if ref in nodes: continue
                    if ref is None or ref in self.anchors or any(j not in members and self.alive[j] for j, _ in self.incident.get(ref, [])):
                        members.discard(i)
                        changed = True
                        break
        blocking += [i for i in inside if i not in members and items[i][1].intersection(inner).length > 2.0]
        if blocking:
            self.reasons["road"] += 1
            return None  # Another road between the carriageways.
        return sorted(members)

    def merge(self, A, B, a_nodes, b_nodes, position, run):
        items = self.items
        (k_start, j_start, _), (k_end, j_end, _) = run[0][0], run[-1][1]
        a_run, b_run = A[k_start:k_end], B[j_end:j_start]
        if sum(items[i][1].length for i in a_run) < PAIR_M:
            self.reasons['merge_short'] += 1
            return
        rungs = [run[0][0]] + [r1 for _, r1, _ in run]
        if all(c == VIRTUAL for _, _, c in rungs) and tags(items[a_run[0]][0]).get("highway") not in RUNGLESS:
            self.reasons["merge_rungless"] += 1
            return
        links = sorted({i for _, _, cell in run for i in cell})
        connectors = sorted({c for _, _, c in rungs if c is not None and c != VIRTUAL})
        absorbed = set(b_run) | set(links) | set(connectors)
        partner = {a_nodes[k]: position[b_nodes[j]] for k, j, c in rungs if c != VIRTUAL}
        rename = {b_nodes[j]: a_nodes[k] for k, j, _ in rungs if b_nodes[j] != a_nodes[k]}
        b_line = self.line(b_run)
        wb = max(self.width[i] for i in b_run)
        moved, new = {}, {}
        for i in a_run:
            f, g = items[i]
            refs = f["properties"]["_city_refs"]
            coords, widths = [], []
            for ref, point in zip(refs, g.coords):
                q = partner.get(ref)
                if q is None:
                    near = b_line.interpolate(b_line.project(Point(point)))
                    q = (near.x, near.y)
                coords.append(((point[0] + q[0]) / 2, (point[1] + q[1]) / 2))
                widths.append(math.dist(point, q) + self.width[i] / 2 + wb / 2)
            if any(a == b for a, b in zip(coords, coords[1:])):
                self.reasons['merge_collapsed'] += 1
                return
            new[i] = [coords, list(refs), [round(max(a, b), 2) for a, b in zip(widths, widths[1:])]]
            moved[refs[0]], moved[refs[-1]] = coords[0], coords[-1]
        midline = LineString([c for n, i in enumerate(a_run) for c in (new[i][0] if n == 0 else new[i][0][1:])])
        if not midline.is_simple:
            self.reasons['merge_midline'] += 1
            return
        # A B node with side roads but no rung gets a midline node (one-sided T).
        splits = defaultdict(set)
        rungs_b = {b_nodes[j] for _, j, _ in rungs}
        for ref in b_nodes[j_end + 1:j_start]:
            if ref in rungs_b or not any(i not in absorbed and self.alive[i] for i, _ in self.incident.get(ref, [])): continue
            point = Point(position[ref])
            i = min(a_run, key=lambda i: (LineString(new[i][0]).distance(point), i))
            coords, refs, widths = new[i]
            line = LineString(coords)
            at = line.project(point)
            stations = [line.project(Point(c)) for c in coords]
            nearest = min(range(len(coords)), key=lambda n: (abs(stations[n] - at), n))
            if abs(stations[nearest] - at) <= 1.0:
                rename[ref] = refs[nearest]
                if 0 < nearest < len(coords) - 1: splits[i].add(refs[nearest])
                moved[refs[nearest]] = coords[nearest]
                continue
            k = next(n for n, s in enumerate(stations) if s > at)
            spot = line.interpolate(at)
            coords.insert(k, (spot.x, spot.y)); refs.insert(k, ref); widths.insert(k - 1, widths[k - 1])
            splits[i].add(ref)
            moved[ref] = (spot.x, spot.y)
        # Every other road at a moved or renamed node follows it.
        changes = defaultdict(dict)
        for ref in sorted(set(moved) | set(rename)):
            target = rename.get(ref, ref)
            for i, end in self.incident.get(ref, []):
                if i in absorbed or i in a_run or not self.alive[i]: continue
                changes[i][end] = (ref, target)
        updates = []
        for i in sorted(changes):
            ends = end_refs(items[i][0])
            targets = [changes[i][e][1] if e in changes[i] else ends[e] for e in (0, 1)]
            if targets[0] == targets[1]:
                # Both ends on one merged node (a jughandle U-turn): the merged
                # road represents it, as it does median links. A longer loop
                # would vanish from the map, so the merge is not made.
                if items[i][1].length > LOOP_M:
                    self.reasons["merge_loop"] += 1
                    return
                absorbed.add(i)
                links.append(i)
                continue
            coords = list(items[i][1].coords)
            for end, (ref, target) in changes[i].items():
                coords[0 if end == 0 else -1] = moved[target]
            if any(a == b for a, b in zip(coords, coords[1:])) or not LineString(coords).is_simple:
                self.reasons['merge_follower'] += 1
                return
            updates.append((i, changes[i], LineString(coords)))
        merged_m = sum(items[i][1].length for i in a_run + b_run)  # Source one-way length merged.
        lanes_a = [lanes(tags(items[i][0])) for i in a_run]
        lanes_b = [lanes(tags(items[i][0])) for i in b_run]
        total = None
        if None not in lanes_a + lanes_b:
            total = min(MAX_LANES, Counter(lanes_a).most_common(1)[0][0] + Counter(lanes_b).most_common(1)[0][0])
        for i, ends, line in updates:
            f, _ = items[i]
            p = f["properties"]
            for end, (ref, target) in ends.items():
                if p.get("_city_refs"): p["_city_refs"][0 if end == 0 else -1] = target
                if p.get("_city_ends"): p["_city_ends"][0 if end == 0 else -1] = str(target)
                if ref != target: self.incident[target].append((i, end))
            items[i] = (f, line)
            self.used.add(i)  # Its end moved; no later ladder relies on it.
        pieces = {}
        for i in a_run:
            f, _ = items[i]
            coords, refs, widths = new[i]
            p = f["properties"]
            p["_city_road_tags"] = {k: v for k, v in tags(f).items() if k not in ("oneway", "dual_carriageway")}
            p["_city_dual"] = True
            p["_city_lanes"] = total
            cuts = [0] + [n for n in range(1, len(refs) - 1) if refs[n] in splits[i]] + [len(refs) - 1]
            pieces[i] = []
            for a, b in zip(cuts, cuts[1:]):
                q = dict(p, _city_refs=refs[a:b + 1], _city_ends=[str(refs[a]), str(refs[b])], _city_widths_m=widths[a:b], width_m=max(widths[a:b]))
                q["_city_sources"] = list(p.get("_city_sources", [p["osm_source_id"]]))
                pieces[i].append((dict(f, properties=q), LineString(coords[a:b + 1])))
        owners = [(i, n, line) for i in a_run for n, (_, line) in enumerate(pieces[i])]
        for j in sorted(absorbed):
            f, g = items[j]
            middle = g.interpolate(0.5, normalized=True)
            i, n, _ = min(owners, key=lambda item: (item[2].distance(middle), item[0], item[1]))
            target = pieces[i][n][0]["properties"]
            target["_city_sources"] = sorted(set(target["_city_sources"]) | set(f["properties"].get("_city_sources", [f["properties"]["osm_source_id"]])))
            crossings = f["properties"].get("_city_crossing_points")
            if crossings: target["_city_crossing_points"] = list(target.get("_city_crossing_points", [])) + list(crossings)
            self.alive[j] = False
        first_new = len(items)
        for i in a_run:
            items[i] = pieces[i][0]
            for piece in pieces[i][1:]:
                items.append(piece)
                self.alive.append(True)
        self.used.update(a_run)
        self.used.update(absorbed)
        self.stats["merged_pairs"] += 1
        self.stats["merged_ways"] += len(a_run) + len(b_run)
        self.stats["absorbed_links"] += len(links) + len(connectors)
        self.stats["merged_m"] += round(merged_m)
        self.reindex([i for i, _, _ in updates] + list(a_run) + list(range(first_new, len(items))))


def paint_service(items):
    """Parking aisles, driveways, drive-throughs, dead-end service stubs under
    15 m and tracks become ground paint (asphalt; tracks dirt, unless tagged).
    They stay drivable terrain and keep their sources."""
    counts = Counter()
    graph = Counter()
    for f, g in items:
        if driving(f, g):
            for ref in end_refs(f) or (f["properties"].get("osm_node_refs", [])[:1] + f["properties"].get("osm_node_refs", [])[-1:]):
                if ref is not None: graph[ref] += 1
    service = [i for i, (f, g) in enumerate(items) if driving(f, g) and not fixed(f) and tags(f).get("highway") == "service" and end_refs(f)]
    by_end = defaultdict(list)
    for i in service:
        for end, ref in enumerate(end_refs(items[i][0])):
            if ref is not None: by_end[ref].append(i)
    painted = set()
    for i in service:
        f, g = items[i]
        if tags(f).get("service") in SERVICE_PAINT:
            painted.add(i)
            continue
    for i in service:
        ends = end_refs(items[i][0])
        for end, ref in enumerate(ends):
            if ref is None or graph[ref] != 1: continue
            # A dead-end service stub, through two-arm joins of service ways.
            path, length, at, current = [i], items[i][1].length, ends[1 - end], i
            while at is not None and graph[at] == 2 and length < STUB_M:
                following = [j for j in by_end[at] if j != current and j not in path]
                if len(following) != 1: break
                current = following[0]
                path.append(current)
                length += items[current][1].length
                refs = end_refs(items[current][0])
                at = refs[1] if refs[0] == at else refs[0]
            if length < STUB_M and at is not None and graph[at] != 2:
                painted.update(path)
    painted.update(i for i, (f, g) in enumerate(items) if driving(f, g) and not fixed(f) and tags(f).get("highway") == "track")
    painted -= _connecting(items, painted)
    for i, (f, g) in enumerate(items):
        if i in painted:
            p = f["properties"]
            kind = tags(f).get("highway")
            p["_city_ground_paint"] = kind
            p["_city_paint_surface"] = p.get("surface", "dirt" if kind == "track" else "asphalt")
            counts[kind] += 1
    return counts


def _connecting(items, painted):
    """Painted candidates that alone connect remaining driving roads or
    structures (an aisle or driveway as the only approach): they stay roads."""
    def ends(f):
        refs = end_refs(f)
        if refs is None:
            graph = f["properties"].get("osm_node_refs") or [None, None]
            refs = [graph[0], graph[-1]]
        return [("ref", _ref(r)) if r is not None else ("cut", id(f), k) for k, r in enumerate(refs[:2])]
    edges = {i: ends(f) for i, (f, g) in enumerate(items) if driving(f, g) or (g.geom_type == "LineString" and not ground(f, g))
             or "_city_estimated_m" in f["properties"]}
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, (a, b) in edges.items():
        if i not in painted: parent[find(a)] = find(b)
    kept = {n for i, e in edges.items() if i not in painted for n in e}
    def node(n): return ("super", find(n)) if n in kept else n
    # Prune painted dead ends; what is left links remaining roads.
    graph = {i: [node(n) for n in edges[i]] for i in painted if i in edges}
    degree = Counter(n for e in graph.values() for n in e)
    changed = True
    while changed:
        changed = False
        for i in sorted(graph):
            if any(n[0] != "super" and degree[n] == 1 for n in graph[i]):
                for n in graph.pop(i): degree[n] -= 1
                changed = True
    links = {}
    for i, (a, b) in graph.items():
        links.setdefault(a, set()).add(i); links.setdefault(b, set()).add(i)
    restore, seen = set(), set()
    for start in sorted(graph):
        if start in seen: continue
        group, pending = set(), [start]
        while pending:
            i = pending.pop()
            if i in group: continue
            group.add(i)
            for n in graph[i]: pending.extend(links[n] - group)
        seen |= group
        supers = {n for i in group for n in graph[i] if n[0] == "super"}
        if len(supers) > 1: restore |= group
    return restore


def sidewalk_state(road_tags):
    values = [road_tags.get(k) for k in ("sidewalk", "sidewalk:both")]
    sides = [road_tags.get(k) for k in ("sidewalk:left", "sidewalk:right")]
    if any(v in ("no", "none") for v in values) or (sides[0] == sides[1] == "no"): return "no"
    if "separate" in values + sides: return "separate"
    if any(v in ("both", "left", "right", "yes") for v in values) or "yes" in sides: return "yes"
    return None


def quantized_sidewalk(metres, scale):
    """Whole map centimetres: 0 or 20..1000 (MapKit), from source metres."""
    cm = round(metres * 100 / scale)
    if cm < 20: cm = 20 if cm >= 10 else 0
    return min(cm, 1000)


def sidewalks(items, scale, spend=lambda count=1: None):
    """Explicit sidewalk width on every ground road (`_city_sidewalk_m` source
    metres on the map-centimetre lattice). A matched `footway=sidewalk` ribbon
    wholly covered by its road's sidewalk is absorbed into that road's sources.
    Returns (items, counts)."""
    counts = Counter()
    urban = [g for f, g in items if g.geom_type != "LineString" and f["properties"].get("osm_region") and f["properties"].get("landuse") in URBAN]
    urban_tree = STRtree(urban)
    footways = [i for i, (f, g) in enumerate(items) if ground(f, g) and tags(f).get("highway") in PEDESTRIAN
                and tags(f).get("footway") == "sidewalk" and not fixed(f)]
    footway_tree = STRtree([items[i][1] for i in footways])
    matches = defaultdict(list)  # footway item -> [(road item, overlap metres)]
    for i, (f, g) in enumerate(items):
        if not ground(f, g) or fixed(f) and "_city_estimated_m" in f["properties"]: continue
        p = f["properties"]
        if not driving(f, g):
            if g.geom_type == "LineString" and not p.get("_city_ground_paint") and tags(f).get("highway") in PEDESTRIAN:
                p["_city_sidewalk_m"] = 0.0
            continue
        kind = tags(f).get("highway", "road")
        state = sidewalk_state(tags(f))
        width = float(p.get("width_m", 8))
        metres = 0.0
        if kind in NO_SIDEWALK or kind.endswith("_link") or state == "no":
            p["_city_sidewalk_m"] = 0.0
            counts["0"] += 1
            continue
        if state in ("yes", "separate") or kind in SIDEWALK_CLASSES and len(urban_tree.query(g.interpolate(0.5, normalized=True), predicate="dwithin", distance=width / 2 + 5)):
            metres = 3.0 if kind in ("primary", "secondary") else 2.0
        reach = width / 2 + FOOTWAY_REACH_M
        near = footway_tree.query(g, predicate="dwithin", distance=reach)
        spend(len(near))
        if len(near):
            distances, points = _samples(g)
            own = _tangents(g, distances)
            normal = np.column_stack([-own[:, 1], own[:, 0]])
            sides = [defaultdict(list), defaultdict(list)]
            for k in sorted(near):
                j = footways[k]
                h = items[j][1]
                fw = float(items[j][0]["properties"].get("width_m", 1.6))
                dist = shapely.distance(h, points)
                nearest = shapely.line_interpolate_point(h, shapely.line_locate_point(h, points))
                offset = shapely.get_coordinates(nearest) - shapely.get_coordinates(points)
                theirs = _tangents(h, shapely.line_locate_point(h, points))
                ok = (dist - width / 2 <= FOOTWAY_REACH_M) & (np.abs((own * theirs).sum(axis=1)) >= 0.9)
                side = (offset * normal).sum(axis=1) >= 0
                for n in np.flatnonzero(ok):
                    outer = dist[n] + fw / 2 - width / 2
                    bucket = sides[int(side[n])][n]
                    bucket.append((outer, j))
            widened = []
            for bucket in sides:
                if len(bucket) >= 0.5 * len(points):
                    values = sorted(min(v)[0] for v in bucket.values())
                    widened.append(values[len(values) // 2])
                    for v in bucket.values():
                        for outer, j in v: matches[j].append(i)
            if widened:
                metres = max(metres, min(FOOTWAY_REACH_M + 2, math.ceil(max(widened) * 4) / 4))
                counts["footway"] += 1
        cm = quantized_sidewalk(metres, scale)
        p["_city_sidewalk_m"] = cm * scale / 100
        counts[str(cm)] += 1
    # A sidewalk footway inside its roads' sidewalks is represented by them.
    drop = set()
    for j in sorted(matches):
        roads = sorted(set(matches[j]))
        band = shapely.union_all([items[i][1].buffer(float(items[i][0]["properties"].get("width_m", 8)) / 2 + items[i][0]["properties"]["_city_sidewalk_m"] + 0.25, cap_style="flat")
                                  for i in roads if items[i][0]["properties"]["_city_sidewalk_m"] > 0] or [Polygon()])
        f, g = items[j]
        spend(len(roads))
        if band.is_empty or g.difference(band).length > 0.5: continue
        owner = max(roads, key=lambda i: (items[i][1].buffer(float(items[i][0]["properties"].get("width_m", 8)) / 2 + items[i][0]["properties"]["_city_sidewalk_m"] + 0.25).intersection(g).length, -i))
        q = items[owner][0]["properties"]
        q["_city_sources"] = sorted(set(q.get("_city_sources", [q["osm_source_id"]])) | set(f["properties"].get("_city_sources", [f["properties"]["osm_source_id"]])))
        crossings = f["properties"].get("_city_crossing_points")
        if crossings: q["_city_crossing_points"] = list(dict.fromkeys(list(q.get("_city_crossing_points", [])) + list(crossings)))
        drop.add(j)
    counts["absorbed_footways"] = len(drop)
    return [item for i, item in enumerate(items) if i not in drop], counts


def markings(kind, lane_count, two_way, surface):
    """MapKit markings for a road record, or None."""
    if kind not in MARKED or surface not in ("asphalt", "concrete"): return None
    count = lane_count or MARKED[kind]
    if not count: return None
    count = max(1, min(MAX_LANES, count))
    return dict(lanes=count, center_line=bool(two_way and count % 2 == 0), edge_lines=False, crosswalk_start=False, crosswalk_end=False)


def _arc(a, p, b, width):
    """Points of MapKit's fillet at p (road_plan.rs fillet): an upper bound
    (no rounding dedupe, a little extra turn for adopted-vertex rounding)."""
    la, lb = math.dist(a, p), math.dist(p, b)
    if la < 2 or lb < 2: return 1
    u = ((p[0] - a[0]) / la, (p[1] - a[1]) / la)
    v = ((b[0] - p[0]) / lb, (b[1] - p[1]) / lb)
    turn = abs(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])) + TURN_SLACK
    radius = width / 2 + min(max(width * 0.15, 20.0), 100.0)
    tangent = math.tan(turn / 2)
    r = min(radius * tangent, 0.45 * la, 0.45 * lb) / tangent
    step = min(math.pi / 18, 2 * math.acos(min(1.0, max(-1.0, 1 - 1 / max(r, 1)))))
    return math.ceil(math.ceil(turn / step) / 2) * 2 + 1


def paint_segments(points, widths, scale, before=None, after=None):
    """MapKit paint path segments of one marked road record (road_paint.rs):
    one point per free end, a fillet arc per interior vertex and, at a
    two-arm end joined to the neighbour vertex `before`/`after` (point,
    width), half of that join's arc. Source metres in, map centimetres used."""
    factor = 100 / scale
    xy = [(x * factor, y * factor) for x, y in points]
    w = [max(v * factor, ROAD_FLOOR_CM) for v in widths]
    total = 0
    for n in range(1, len(xy) - 1):
        total += _arc(xy[n - 1], xy[n], xy[n + 1], max(w[n - 1], w[n]))
    for end, join in ((0, before), (1, after)):
        if join is None:
            total += 1
            continue
        q = (join[0][0] * factor, join[0][1] * factor)
        wq = max(join[1] * factor, ROAD_FLOOR_CM)
        arc = _arc(q, xy[0], xy[1], max(wq, w[0])) if end == 0 else _arc(xy[-2], xy[-1], q, max(w[-1], wq))
        half = (arc - 1) // 2
        total += arc - half if end == 0 else half + 1
    return total - 1


def node_keys(f):
    """Layer node keys of a road record's ends, as geojson.convert writes them
    (None: an independent end)."""
    p = f["properties"]
    if "osm_node_refs" in p: return [("x", p["osm_node_refs"][0]), ("x", p["osm_node_refs"][-1])]
    if tags(f).get("highway") in PEDESTRIAN and "_city_estimated_m" not in p: return [None, None]
    ends = p.get("_city_ends")
    if ends: return [("g", str(e)) if e is not None else None for e in ends]
    return [None, None]


class Graph:
    """Road records' end nodes (the layer's node set) and two-arm joins."""

    def __init__(self, roads, is_road):
        self.roads = roads
        self.at = defaultdict(list)
        for index, (f, g) in enumerate(roads):
            if not is_road(f, g): continue
            for end, key in enumerate(node_keys(f)):
                if key is not None: self.at[key].append((index, end))

    def degree(self, key):
        return len(self.at[key]) if key is not None else 1

    def join(self, index, end):
        """(neighbour index, (its vertex next to the join, its end width)) at a two-arm end."""
        key = node_keys(self.roads[index][0])[end]
        if key is None or len(self.at[key]) != 2: return None
        (j, e), = [(j, e) for j, e in self.at[key] if (j, e) != (index, end)]
        f, g = self.roads[j]
        coords = list(g.coords)
        widths = f["properties"].get("_city_widths_m") or [float(f["properties"].get("width_m", 8))] * (len(coords) - 1)
        return j, ((coords[1], widths[0]) if e == 0 else (coords[-2], widths[-1]))


def record_segments(roads, graph, index, scale):
    f, g = roads[index]
    coords = list(g.coords)
    widths = f["properties"].get("_city_widths_m") or [float(f["properties"].get("width_m", 8))] * (len(coords) - 1)
    joins = [graph.join(index, 0), graph.join(index, 1)]
    return paint_segments(coords, widths, scale, *(j[1] if j else None for j in joins))


def finish(roads, scale, crossing_points, crossing_lines, is_road, spend=lambda count=1: None):
    """Markings, junction-end crosswalks and the paint segment bound on the
    derived roads (`is_road`: records that stay roads). Ordinary records whose
    paint could exceed the MapKit bound are split at source nodes; a record that
    cannot be split keeps no markings. Returns (roads, counts)."""
    counts = Counter()
    graph = Graph(roads, is_road)
    half = defaultdict(float)
    for key, ends in graph.at.items():
        half[key] = max(float(roads[i][0]["properties"].get("width_m", 8)) / 2 for i, e in ends)
    point_tree = STRtree([Point(c) for c in crossing_points])
    line_tree = STRtree(crossing_lines)
    marks = {}
    for index, (f, g) in enumerate(roads):
        p = f["properties"]
        if not is_road(f, g) or not driving(f, g) or tags(f).get("highway") in PEDESTRIAN: continue
        t = tags(f)
        mark = markings(t.get("highway", "road"), p.get("_city_lanes", lanes(t)), oneway(t) == 0, p.get("surface", "asphalt"))
        if mark is None: continue
        width = float(p.get("width_m", 8))
        for end, key in enumerate(node_keys(f)):
            if key is None or graph.degree(key) < 3: continue
            at = Point(g.coords[0 if end == 0 else -1])
            reach = max(CROSSWALK_M, math.sqrt(2) * half[key] + 10)
            found = any(Point(crossing_points[k]).distance(g) <= width / 2 + 1 and Point(crossing_points[k]).distance(at) <= reach
                        for k in point_tree.query(at.buffer(reach)))
            if not found:
                for k in line_tree.query(at.buffer(reach)):
                    piece = crossing_lines[k].intersection(g.buffer(width / 2 + 1))
                    if not piece.is_empty and piece.distance(at) <= reach:
                        found = True
                        break
            spend()
            if found:
                mark["crosswalk_start" if end == 0 else "crosswalk_end"] = True
        marks[index] = mark
    output = []
    for index, (f, g) in enumerate(roads):
        if index not in marks:
            output.append((f, g))
            continue
        p = f["properties"]
        mark = marks[index]
        joins = [graph.join(index, 0), graph.join(index, 1)]
        neighbours = any(j is not None and j[0] in marks for j in joins)
        budget = RECORD_SEGMENTS if neighbours else PAINT_SEGMENTS
        coords = list(g.coords)
        widths = p.get("_city_widths_m") or [float(p.get("width_m", 8))] * (len(coords) - 1)
        spend(len(coords))
        if paint_segments(coords, widths, scale, *(j[1] if j else None for j in joins)) <= budget:
            output.append((dict(f, properties=dict(p, _city_markings=mark)), g))
            counts["marked"] += 1
            counts["crosswalks"] += mark["crosswalk_start"] + mark["crosswalk_end"]
            continue
        refs = p.get("_city_point_refs")
        if fixed(f) or not refs or len(refs) != len(coords) or not p.get("_city_ends"):
            output.append((f, g))
            counts["unmarked_long"] += 1
            continue
        # Greedy cuts at source nodes; every piece then has marked two-arm
        # neighbours and keeps within RECORD_SEGMENTS.
        last_index = len(coords) - 1
        def fits(a, b):
            before = (coords[a - 1], widths[a - 1]) if a > 0 else joins[0][1] if joins[0] else None
            after = (coords[b + 1], widths[b]) if b < last_index else joins[1][1] if joins[1] else None
            return paint_segments(coords[a:b + 1], widths[a:b], scale, before, after) <= RECORD_SEGMENTS
        cuts, last = [0], None
        for n in range(1, len(coords)):
            if not fits(cuts[-1], n):
                if last is None or not fits(last, n): break
                cuts.append(last)
                last = None
            if n < last_index and refs[n] is not None: last = n
        else:
            cuts.append(last_index)
        if cuts[-1] != last_index:
            output.append((f, g))
            counts["unmarked_long"] += 1
            continue
        for a, b in zip(cuts, cuts[1:]):
            piece_mark = dict(mark, crosswalk_start=mark["crosswalk_start"] and a == 0, crosswalk_end=mark["crosswalk_end"] and b == last_index)
            ends = [p["_city_ends"][0] if a == 0 else str(refs[a]), p["_city_ends"][1] if b == last_index else str(refs[b])]
            q = dict(p, _city_markings=piece_mark, _city_ends=ends, _city_widths_m=widths[a:b], _city_point_refs=refs[a:b + 1],
                     width_m=max(widths[a:b]), _city_sources=list(p["_city_sources"]))
            output.append((dict(f, properties=q), LineString(coords[a:b + 1])))
            counts["marked"] += 1
            counts["crosswalks"] += piece_mark["crosswalk_start"] + piece_mark["crosswalk_end"]
        counts["paint_splits"] += len(cuts) - 2
    return enforce_paint_bound(output, scale, counts, is_road), counts


def paint_totals(roads, scale, is_road):
    """Per marked record: its paint segments plus those of its marked two-arm
    neighbours (what MapKit draws joined at most 128 of per road and cell)."""
    graph = Graph(roads, is_road)
    estimates = {index: record_segments(roads, graph, index, scale) for index, (f, g) in enumerate(roads)
                 if f["properties"].get("_city_markings") and is_road(f, g)}
    totals = {}
    for index, estimate in estimates.items():
        totals[index] = estimate + sum(estimates.get(j[0], 0) for j in (graph.join(index, 0), graph.join(index, 1)) if j is not None)
    return totals, estimates


def paint_bound(roads, scale, is_road):
    """Check: the largest per-record paint total (at most PAINT_SEGMENTS)."""
    return max(paint_totals(roads, scale, is_road)[0].values(), default=0)


def enforce_paint_bound(roads, scale, counts, is_road):
    """Drop markings from the largest contributor until every total fits."""
    while True:
        totals, estimates = paint_totals(roads, scale, is_road)
        over = [index for index, total in totals.items() if total > PAINT_SEGMENTS]
        if not over: return roads
        index = max(over, key=lambda i: (estimates[i], i))
        f, g = roads[index]
        roads[index] = (dict(f, properties={k: v for k, v in f["properties"].items() if k != "_city_markings"}), g)
        counts["unmarked_bound"] += 1
