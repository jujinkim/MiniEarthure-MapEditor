"""Deterministic, scale-aware derived city geometry. Original sources are immutable.

Only compatible ground chains and local area groups are combined. Every building
keeps its own footprint; nearby buildings of one site and category share one
record as MapKit building parts. Road corridors, landmark/tall buildings, source
junctions and vertical roads are protected. The output is ordinary current-v1
geometry, not a special runtime map format.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import math

import numpy as np
import shapely
from shapely.geometry import shape, mapping, Polygon, LineString, box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from shapely.errors import GEOSException

from projection import Coordinates
from osm_extract import PEDESTRIAN
import osm_roads
import osm_sites
from import_layer import BudgetExceeded, soft_limit, limit_snapshot, limit_restore, limit_delta, limit_replay

PROFILE = "scale-aware-city-v1"
SCALE = 8  # Default and original city denominator; any integer 1..8 is accepted.
SCALES = range(1, 9)
STRUCTURE_SAFETY_CM = 20  # Native bridge/tunnel safety furniture (import_units.gd).
MAX_GROUP = 128
MAX_WORK = 4_000_000  # Soft: exceeding it records a limit warning.
BUILDING_SPLIT_DEPTH = 16  # Warn above.
BUILDING_SPLIT_CEILING = 24
PAINT_SPLIT_DEPTH = 32  # Warn above.
PAINT_SPLIT_CEILING = 48
LEVELS = (0, 2, 4, 8, 16, 32, 64)  # Source metres: simplification levels (buildings are never gap-filled).
BUILDING_TOLERANCE = 1.0  # Source metres: each footprint stays recognisable.
SURFACES = {"asphalt":"asphalt", "concrete":"concrete", "dirt":"dirt", "gravel":"gravel", "grass":"grass",
            "paved":"asphalt", "paving_stones":"concrete", "sett":"concrete", "cobblestone":"concrete",
            "concrete:plates":"concrete", "concrete:lanes":"concrete", "compacted":"gravel",
            "fine_gravel":"gravel", "pebblestone":"gravel", "unpaved":"dirt", "ground":"dirt",
            "earth":"dirt", "sand":"dirt", "mud":"dirt", "wood":"concrete", "metal":"concrete"}
PAINT_CELL = 3200  # Map centimetres: one native cell partitions pedestrian paint.
# Area paint cell: PAINT_CELL × this. Larger cells give fewer but larger pieces,
# which cost MapKit's surface-area overlap check more (measured), so it stays 1.
AREA_FACTOR = 1
PAINT_VERTICES = 256
MIN_AREA_PIECE_CM2 = 10000  # Area paint pieces under one map square metre are not painted.
# Area paint keeps this map clearance from paint and water before it: snap
# rounding of the earlier piece's cuts (0.5 cm), of the margin (0.71 cm) and of
# the new piece's cuts (0.5 cm) never close it.
PAINT_MARGIN_CM = 2
# City water (map centimetres): a flat surface just above the ground (terrain
# carving gives it depth), stream ribbons at least WATER_MIN_WIDTH_CM wide,
# pieces cut per WATER_CELL_CM like paint (hole-free, ≤ PAINT_VERTICES).
WATER_SURFACE_CM = 3
WATER_DEPTH_CM = 60
WATER_MIN_WIDTH_CM = 150
WATER_CELL_CM = 12800
WIDTHS = {"motorway":12,"trunk":10,"primary":8,"secondary":8,"tertiary":6,"residential":6,
          "living_street":4,"service":3,"track":3,"path":1.6,"footway":1.6,"cycleway":2.4,"pedestrian":4,"steps":1.6}


def parts(geometry, kind="Polygon"):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [p for g in geometry.geoms for p in parts(g, kind)]
    return []


def positions(geometry):
    return int(shapely.get_num_coordinates(geometry))


def moved(geometries, function):
    """Apply an x/y array function to every coordinate in one call. The same
    per-point arithmetic as a scalar transform, without per-vertex Python calls."""
    return shapely.transform(geometries, lambda xy: np.column_stack(function(xy[:,0], xy[:,1])))


def straight(polygon):
    """A hole-free lattice polygon without exactly collinear vertices (pieces
    cut at cell lines and holes keep the same area with fewer vertices)."""
    ring = list(polygon.exterior.coords)[:-1]
    changed = True
    while changed and len(ring) > 3:
        changed = False
        kept = []
        for i, b in enumerate(ring):
            a, c = (kept[-1] if kept else ring[i-1]), ring[(i+1) % len(ring)]
            if (b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0]) == 0:
                changed = True
                continue
            kept.append(b)
        if len(kept) < 3: break
        ring = kept
    return polygon if len(ring) + 1 == len(polygon.exterior.coords) else Polygon(ring)


def corner_radius_cm(width_cm):
    """MapKit road_plan.rs corner_radius: the junction curb fillet radius."""
    return min(100.0, max(20.0, width_cm * 0.15))


def corner_fillets(roads, scale):
    """Triangles (source metres) covering MapKit's inside-corner curb fillets.

    At every node joining two or more road ends, each pair of angularly adjacent
    arms meets at the corner C of their road edges (carriageway half widths). The
    fillet of radius R (from the arm width in map cm) is tangent to both edges at
    R / tan(φ/2) from C, φ the block angle between the arms; the road area it adds
    lies inside the triangle C and both tangent points."""
    arms = defaultdict(list)
    for f, g in roads:
        p = f["properties"]
        if g.geom_type != "LineString" or len(g.coords) < 2: continue
        widths = p.get("_city_widths_m")
        if not widths or len(widths) != len(g.coords) - 1: widths = [float(p.get("width_m", 8))] * (len(g.coords) - 1)
        coords = list(g.coords)
        for point, toward, width in ((coords[0], coords[1], widths[0]), (coords[-1], coords[-2], widths[-1])):
            dx, dy = toward[0] - point[0], toward[1] - point[1]
            length = math.hypot(dx, dy)
            if length == 0: continue
            arms[(round(point[0], 2), round(point[1], 2))].append((math.atan2(dy, dx), dx / length, dy / length, float(width), point))
    wedges = []
    for key in sorted(arms):
        group = sorted(arms[key])
        if len(group) < 2: continue
        for k, (alpha, ux, uy, wa, point) in enumerate(group):
            beta, vx, vy, wb, _ = group[(k + 1) % len(group)]
            phi = (beta - alpha) % (2 * math.pi)
            if not 0.01 < phi < math.pi - 0.001: continue
            ha, hb = wa / 2, wb / 2
            # Edge of a on its counter-clockwise side, edge of b on its clockwise side.
            ax, ay = point[0] - uy * ha, point[1] + ux * ha
            bx, by = point[0] + vy * hb, point[1] - vx * hb
            det = ux * (-vy) - uy * (-vx)
            if abs(det) < 1e-9: continue
            t = ((bx - ax) * (-vy) - (by - ay) * (-vx)) / det
            cx, cy = ax + ux * t, ay + uy * t
            radius = max(corner_radius_cm(round(wa * 100 / scale)), corner_radius_cm(round(wb * 100 / scale))) * scale / 100
            reach = radius / math.tan(phi / 2)
            wedges.append(Polygon([(cx, cy), (cx + ux * reach, cy + uy * reach), (cx + vx * reach, cy + vy * reach)]))
    return [w for w in wedges if w.is_valid and w.area > 0]


def map_cm(cm, scale):
    """Source metres of whole map centimetres at 1:scale. The integer product is
    divided once, so the result is the nearest float (8 cm at 1:8 is exactly 0.08)."""
    return cm * scale / 100


def scale_denominator(value):
    if type(value) is not int or value not in SCALES:
        raise ValueError("City scale must be an integer denominator from 1 to 8")
    return value


def road_buffers(geometries, widths, clearance):
    # Built once per geometry list; barrier queries only clip and union them.
    return shapely.buffer(np.array(geometries, dtype=object), np.array(widths)/2+clearance, quad_segs=16, cap_style="square", join_style="mitre")


def segment_buffers(lines, clearance):
    """Buffers of (line, per-segment widths): a line of one width is buffered
    whole; otherwise each run of equal widths keeps its own width."""
    result = [None] * len(lines)
    uniform = [i for i, (g, w) in enumerate(lines) if len(set(w)) <= 1]
    if uniform:
        for i, b in zip(uniform, road_buffers([lines[i][0] for i in uniform], [lines[i][1][0] if lines[i][1] else 8 for i in uniform], clearance)):
            result[i] = b
    for i, (g, widths) in enumerate(lines):
        if result[i] is not None: continue
        coords, parts, start = list(g.coords), [], 0
        for k in range(1, len(widths) + 1):
            if k == len(widths) or widths[k] != widths[start]:
                parts.append((LineString(coords[start:k + 1]), widths[start]))
                start = k
        result[i] = unary_union(list(road_buffers([a for a, w in parts], [w for a, w in parts], clearance)))
    return result


def source_ids(feature):
    return feature["properties"].get("_city_sources", [feature["properties"]["osm_source_id"]])


def _key(geometry):
    return (*geometry.bounds, geometry.normalize().wkb_hex)


def strict_rings(geometry):
    rings = [geometry.exterior, *geometry.interiors]
    return all(ring.is_simple and len(set(ring.coords[:-1])) == len(ring.coords)-1 for ring in rings) and not any(a.intersects(b) for i,a in enumerate(rings) for b in rings[i+1:])


def is_building(feature, geometry):
    p = feature["properties"]
    return geometry.geom_type not in ("LineString", "MultiLineString") and not (p.get("osm_region") or p.get("_city_paint") or p.get("landuse") in ("forest","orchard"))


def clear_width(feature, furniture):
    """Width buildings keep clear of; estimated structures add `furniture`
    (20 map cm each side) for native bridge/tunnel safety furniture."""
    p = feature["properties"]
    return float(p.get("width_m", 8)) + 2 * float(p.get("_city_sidewalk_m", 0)) + (furniture if "_city_estimated_m" in p else 0.0)


def clear_widths(feature, geometry, furniture):
    """Per-segment clear widths: each segment's own width (chains and merged
    roads vary), plus sidewalks and estimated-structure furniture."""
    p = feature["properties"]
    extra = clear_width(feature, furniture) - float(p.get("width_m", 8))
    widths = p.get("_city_widths_m")
    if not widths or len(widths) != len(geometry.coords) - 1:
        widths = [float(p.get("width_m", 8))] * (len(geometry.coords) - 1)
    return [max(0.01, float(w) + extra) for w in widths]


def is_walking(feature, structural=frozenset()):
    """Ground pedestrian ways, including closed loops not joined to a structure."""
    p = feature["properties"]
    if p.get("_city_ground_paint") and "osm_node_refs" not in p and "_city_estimated_m" not in p:
        return True  # Painted service ways and tracks (city road rules).
    if p.get("_city_road_tags", {}).get("highway") not in PEDESTRIAN or p.get("road_kind", "ground") != "ground" or "elevations_m" in p:
        return False
    if "_city_estimated_m" in p:
        return False
    return "osm_node_refs" not in p or ("osm_loop_range" in p and structural.isdisjoint(p["osm_node_refs"]))


class Generalizer:
    def __init__(self, collection, options, review=None, scale=SCALE):
        from osm_review import Review
        # Map-unit lattice and clearances in source metres at 1:scale; each is a
        # whole number of map centimetres, so a multiple of the lattice.
        self.scale = scale_denominator(scale)
        self.grid = map_cm(1, scale)
        self.to_map_factor = 100 / scale
        self.road_clearance = map_cm(10, scale)
        self.building_clearance = map_cm(2, scale)
        self.partition_gap = map_cm(4, scale)
        self.furniture = map_cm(2*STRUCTURE_SAFETY_CM, scale)
        self.minimum_width = map_cm(20, scale)
        self.review = review if review is not None else Review()
        self.excluded_sources = set()
        self.collection = collection
        self.projection = Coordinates(options)
        # Working-frame multiples of the lattice must be whole map centimetres of
        # the adopted map, (frame + local origin) ÷ scale. Other scales shift the
        # frame by the local origin's remainder; 1:8 keeps its historical frame.
        shift = (0.0, 0.0)
        if self.scale != SCALE:
            shift = tuple((round(v*100) % self.scale)/100 for v in self.projection.local)
        self.local = tuple(v - d for v, d in zip(self.projection.local, shift)) if any(shift) else tuple(self.projection.local)
        self.remaining = MAX_WORK
        self.work_over = False
        self.features = []
        self.surface_mappings = Counter()
        self.widened_roads = 0
        self.estimated_widths = Counter()
        self.road_rules = Counter()
        barrier_sources = []
        water_lines = []
        # Meter precision in the source frame, before the single 1:scale adoption.
        # Scalars or coordinate arrays; arrays give the same per-point values.
        def project(x, y, z=None):
            xx, yy = self.projection.transformer.transform(np.asarray(x, dtype=float), np.asarray(y, dtype=float), errcheck=True)
            if any(shift): return xx - self.projection.origin_xy[0] + shift[0], yy - self.projection.origin_xy[1] + shift[1]
            return xx - self.projection.origin_xy[0], yy - self.projection.origin_xy[1]
        self.project = project
        from pyproj.enums import TransformDirection
        def inverse(x, y, z=None):
            if any(shift): x, y = np.asarray(x, dtype=float) - shift[0], np.asarray(y, dtype=float) - shift[1]
            return self.projection.transformer.transform(np.asarray(x, dtype=float) + self.projection.origin_xy[0], np.asarray(y, dtype=float) + self.projection.origin_xy[1], direction=TransformDirection.INVERSE, errcheck=True)
        self.inverse = inverse
        for feature in collection["features"]:
            feature = deepcopy(feature)
            geometry = shape(feature["geometry"])
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError("City optimization requires valid original geometry; no automatic repair")
            geometry = moved(geometry, project)
            if "_city_gates" in feature["properties"]:
                gates = np.array(feature["properties"]["_city_gates"], dtype=float)
                xs, ys = project(gates[:, 0], gates[:, 1])
                feature["properties"]["_city_gates"] = [(float(x), float(y), float(w)) for x, y, w in zip(xs, ys, gates[:, 2])]
            if "_city_barrier" in feature["properties"]:
                barrier_sources.append((feature, geometry))  # Barrier lines are not roads.
                continue
            if "_city_waterway" in feature["properties"]:
                water_lines.append((feature, geometry))  # Waterway lines become water, not roads.
                continue
            if "_city_outline" in feature["properties"]:
                feature["properties"]["_city_outline"] = [list(zip(*project(*np.array(ring, dtype=float).T))) for ring in feature["properties"]["_city_outline"]]
            if geometry.geom_type == "LineString":
                p = feature["properties"]
                if "width_m" not in p:
                    road_class = p.get("_city_road_tags",{}).get("highway","road")
                    lane_width = osm_roads.lane_width(p.get("_city_road_tags", {})) if road_class not in PEDESTRIAN else None
                    p["width_m"] = lane_width or WIDTHS.get(road_class,8)
                    p["_city_width_estimate"] = "lanes" if lane_width else "class"
                    self.estimated_widths[road_class] += 1
                    if lane_width: self.road_rules["lane_widths"] += 1
                if "_city_crossings" in p:
                    xs, ys = project(*np.array(p.pop("_city_crossings"), dtype=float).T)
                    p["_city_crossing_points"] = [(float(x), float(y)) for x, y in zip(xs, ys)]
                original = p.get("surface", "asphalt")
                mapped = SURFACES.get(original, "asphalt")
                if mapped != original:
                    self.surface_mappings[(original, mapped)] += 1
                    p["surface"] = mapped
                if float(p.get("width_m", 8)) < self.minimum_width:
                    p["width_m"] = self.minimum_width  # Current-v1 minimum width: 20 map cm.
                    self.widened_roads += 1
            self.features.append((feature, geometry))
        self.before = self.counts(self.features + barrier_sources + water_lines)
        # City road rules before any buffer, so every gap shares them: service
        # paint, dual carriageways merged into one road, explicit sidewalks.
        self.road_rules.update({"painted_" + k: n for k, n in osm_roads.paint_service(self.features).items()})
        merger = osm_roads.DualCarriageways(self.features, self.spend, self.scale)
        self.features = merger.run()
        self.road_rules.update({"dual_" + k: n for k, n in merger.stats.items()})
        self.road_rules.update({"profile_" + k: n for k, n in osm_roads.apply_profiles(self.features, self.scale).items()})
        self.features, sidewalk_counts = osm_roads.sidewalks(self.features, self.scale, self.spend)
        self.road_rules.update({("sidewalk_" + k if not k[0].isdigit() else "sidewalk_cm_" + k): n for k, n in sidewalk_counts.items()})
        self.crossing_points = list(dict.fromkeys(c for f, g in self.features for c in f["properties"].get("_city_crossing_points", [])))
        self.crossing_lines = [g for f, g in self.features if g.geom_type == "LineString" and f["properties"].get("_city_road_tags", {}).get("footway") == "crossing"]
        self.level_structures = sum(bool(f["properties"].get("_city_level_structure")) for f,g in self.features)
        self.road_geometries = [g for f, g in self.features if g.geom_type == "LineString"]
        # Gap-filling barriers and building trims use the same per-segment
        # clear widths (sidewalks included).
        road_lines = [(g, clear_widths(f, g, self.furniture)) for f, g in self.features if g.geom_type == "LineString"]
        self.road_widths = [max(w) for g, w in road_lines]
        self.road_tree = STRtree(self.road_geometries)
        self.road_buffers = np.array(segment_buffers(road_lines, self.road_clearance), dtype=object)
        self.ground_geometries = [g for f,g in self.features if g.geom_type == "LineString" and f["properties"].get("road_kind","ground") == "ground"]
        self.ground_widths = [clear_widths(f, g, self.furniture) for f,g in self.features if g.geom_type == "LineString" and f["properties"].get("road_kind","ground") == "ground"]
        self.ground_buffers = segment_buffers(list(zip(self.ground_geometries, self.ground_widths)), self.road_clearance)
        # Buildings lifted from a positive layer to the ground are cut around
        # source-height structures with their safety furniture; no building
        # grows back into that corridor.
        structures = [(g, float(f["properties"].get("width_m", 8)) + self.furniture) for f,g in self.features
                      if g.geom_type == "LineString" and f["properties"].get("road_kind","ground") != "ground"]
        self.structure_buffers = list(road_buffers([g for g,w in structures], [w for g,w in structures], self.road_clearance))
        self.structure_tree = STRtree(self.structure_buffers)
        self.protected_areas = [g for f,g in self.features if g.geom_type != "LineString" and (f["properties"].get("protected") or f["properties"].get("landuse") in ("water","wetland","forest","orchard","park","nature_reserve"))]
        self.area_tree = STRtree(self.protected_areas)
        self.area_array = np.array(self.protected_areas, dtype=object)
        # Projection can invalidate a source area; its overlay may then fail
        # and must fail inside the group, as an eagerly built barrier does.
        self.invalid_areas = ~shapely.is_valid(self.area_array) if len(self.area_array) else np.zeros(0, dtype=bool)
        self.barrier_buffers = self.road_buffers
        self.barrier_tree = self.road_tree
        self.max_width = max(self.road_widths, default=0)
        # Sites group building records; barriers are built once (gap independent).
        self.is_walking = is_walking
        self.source_ids = source_ids
        self.sites = osm_sites.Sites(self.features, source_ids)
        self.barriers = osm_sites.Barriers(self, barrier_sources)
        self.water_items, self.water_counts, self.water_dropped = self.water(water_lines)
        self.input_ids = sorted({s for f,g in self.features for s in source_ids(f)} | {s for f,g in self.barriers.items for s in source_ids(f)}
                                | {s for f,g in self.water_items for s in source_ids(f)})
        self.uses = Counter(ref for f,g in self.features if g.geom_type == "LineString"
                            for ref in set(f["properties"].get("osm_node_refs", f["properties"].get("_city_refs", []))))
        # Chaining joins driving roads where exactly two driving roads meet;
        # painted ways (footways, service paint) no longer block it.
        self.drive_uses = Counter(ref for f,g in self.features if g.geom_type == "LineString" and ("osm_node_refs" in f["properties"] or not is_walking(f))
                                  for ref in set(f["properties"].get("osm_node_refs", f["properties"].get("_city_refs", []))))
        self.trim_windows = {}
        self.context = {}
        self.reviewed = len(self.review.excluded)

    def spend(self, count=1):
        # Hot path: the limit is recorded once when first crossed; settle_work()
        # records the final amount at the end of the candidate.
        self.remaining -= count
        if self.remaining < 0 and not self.work_over:
            self.work_over = True
            self.settle_work()

    def settle_work(self):
        if self.remaining < 0:
            soft_limit("city_work", MAX_WORK - self.remaining, MAX_WORK, "City optimization spatial work budget exceeded; optimization takes longer")

    def stage_limits(self, snapshot):
        """Limits met while building a cached stage. city_work is excluded: the
        replayed spend() records it."""
        return limit_delta(snapshot, ("city_work",))

    @staticmethod
    def counts(items):
        counts = dict(features=len(items), positions=0, roads=0, buildings=0, areas=0, barriers=0)
        for feature, geometry in items:
            counts["positions"] += positions(geometry)
            p = feature["properties"]
            counts["barriers" if "_city_barrier" in p else "areas" if "_city_waterway" in p or "_city_water" in p else "roads" if geometry.geom_type == "LineString" else "areas" if p.get("osm_region") or p.get("_city_paint") or p.get("landuse") in ("forest", "orchard") else "buildings"] += 1
        return counts

    def barrier(self, geometry, extra=0):
        """Query and charge the barrier now; return a cached builder of its union,
        which callers need only when filling or simplification can add area."""
        window = geometry.envelope.buffer(extra + self.max_width / 2 + self.road_clearance).envelope
        ids = self.barrier_tree.query(window)
        self.spend(len(ids))
        # A buffer's envelope lies within its source bounds grown by the distance,
        # so an empty query of that box is the same as the exact (costly) query.
        x0, y0, x1, y1 = geometry.bounds
        reach = extra + self.building_clearance + 1e-6
        areas = self.area_tree.query(box(x0-reach, y0-reach, x1+reach, y1+reach))
        if len(areas):
            areas = self.area_tree.query(geometry.buffer(extra+self.building_clearance).envelope)
        self.spend(len(areas))
        # Gap filling must not regrow into a junction surface the trim cleared,
        # nor into a source-height structure's safety corridor.
        junctions = self.junction_tree.query(window)
        structures = self.structure_tree.query(window)
        self.spend(len(junctions) + len(structures))
        union = []
        def build():
            if not union:
                union.append(unary_union(list(shapely.intersection(self.barrier_buffers[ids], window)) + list(shapely.intersection(self.area_array[areas], window))
                                         + [self.junction_disks[i] for i in junctions] + [self.structure_buffers[i].intersection(window) for i in structures]))
            return union[0]
        if self.invalid_areas[areas].any():
            build()
        return build

    def barrier_hit(self, geometry, grown, extra=0):
        """Whether `grown` (area a simplification adds) meets road space, protected
        land, a junction surface or a structure corridor near `geometry`. Charges
        the same queries as `barrier`; an invalid nearby area fails as its overlay."""
        x0, y0, x1, y1 = geometry.bounds
        reach = extra + self.building_clearance + 1e-6
        areas = self.area_tree.query(box(x0-reach, y0-reach, x1+reach, y1+reach))
        if len(areas):
            areas = self.area_tree.query(geometry.buffer(extra+self.building_clearance).envelope)
        self.spend(len(areas))
        if self.invalid_areas[areas].any():
            self.barrier(geometry, extra)()  # Raises inside the group, as the eager overlay does.
        if grown.is_empty: return False  # Nothing to test: only the area query is charged.
        window = geometry.envelope.buffer(extra + self.max_width / 2 + self.road_clearance).envelope
        ids = self.barrier_tree.query(window)
        junctions = self.junction_tree.query(window)
        structures = self.structure_tree.query(window)
        self.spend(len(ids) + len(junctions) + len(structures))
        return bool(shapely.intersects(self.barrier_buffers[ids], grown).any() or shapely.intersects(self.area_array[areas], grown).any()
                    or any(self.junction_disks[i].intersects(grown) for i in junctions)
                    or any(self.structure_buffers[i].intersects(grown) for i in structures))

    def simplified_line(self, feature, geometry, tolerance):
        """The simplified line and the source vertex index of each kept vertex."""
        p = feature["properties"]
        refs = p.get("_city_refs")
        if tolerance == 0 or len(geometry.coords) <= 2 or not refs or len(refs) != len(geometry.coords) or "osm_node_refs" in p:
            return geometry, list(range(len(geometry.coords)))
        # All source incidence, including junctions inside a way, stays fixed.
        cuts = [0] + [i for i in range(1, len(refs)-1) if self.uses[refs[i]] > 1] + [len(refs)-1]
        points, kept = [], []
        original = list(geometry.coords)
        for a,b in zip(cuts,cuts[1:]):
            segment = LineString(list(geometry.coords)[a:b+1])
            candidate = segment.simplify(tolerance, preserve_topology=True)
            if not candidate.is_simple:
                candidate = segment
            # Do not create a crossing with a road the source did not cross.
            ids = self.road_tree.query(candidate.envelope)
            self.spend(len(ids))
            if any(candidate.intersects(self.road_geometries[i]) and not segment.intersects(self.road_geometries[i]) for i in ids):
                candidate = segment
            # Douglas-Peucker keeps source vertices in order.
            index = a
            for point in list(candidate.coords)[bool(points):]:
                while original[index] != point: index += 1
                kept.append(index)
                points.append(point)
        return LineString(points), kept

    def roads(self, gap):
        ordinary, fixed = [], []
        for f, g in self.features:
            if g.geom_type != "LineString":
                continue
            if "osm_node_refs" in f["properties"] or "_city_estimated_m" in f["properties"]:
                # Source graph and estimated structure profiles keep every vertex.
                fixed.append((deepcopy(f), g))
            else:
                geometry, kept = self.simplified_line(f, g, min(4.0, gap / 4))
                ordinary.append((deepcopy(f), geometry, kept, len(g.coords)))
        # Per ordinary piece: simplified segment widths, vertex source refs,
        # lane count (voted by length along a chain) and sidewalk.
        extras = []
        for feature, geometry, kept, count in ordinary:
            p = feature["properties"]
            source = p.get("_city_widths_m") or [float(p.get("width_m", 8))] * (count - 1)
            refs = p.get("_city_refs")
            extras.append(([max(source[a:b]) for a, b in zip(kept, kept[1:])],
                           [refs[k] for k in kept] if refs and len(refs) == count else [None] * len(kept),
                           p["_city_lanes"] if "_city_lanes" in p else osm_roads.lanes(p.get("_city_road_tags", {})),
                           float(p.get("_city_sidewalk_m", 0))))
        ordinary = [(f, g) for f, g, kept, count in ordinary]
        walks = [is_walking(f) for f, g in ordinary]
        endpoints = defaultdict(list)
        for index, (feature, geometry) in enumerate(ordinary):
            refs = feature["properties"].get("_city_refs")
            if refs:
                endpoints[(walks[index], refs[0])].append((index, 0))
                endpoints[(walks[index], refs[-1])].append((index, 1))
        # Chains continue across width, lane, name and ref changes (per-segment
        # widths); class, structure, access, surface, oneway, sidewalk and paint
        # still break (one sidewalk per road record).
        ignored = ("name", "ref", "lanes", "sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right", "footway", "dual_carriageway")
        def signature(feature):
            p = feature["properties"]
            return json.dumps({k:v for k,v in p.items() if not k.startswith("_city") and k not in ("osm_source_id", "width_m")}
                              | {"tags":{k:v for k,v in p.get("_city_road_tags", {}).items() if k not in ignored}, "paint":p.get("_city_ground_paint"),
                                 "sidewalk":p.get("_city_sidewalk_m", 0)}, sort_keys=True)
        signatures = [signature(f) for f,g in ordinary]
        seen, output = set(), []
        for index, (feature, geometry) in enumerate(ordinary):
            if index in seen:
                continue
            seen.add(index)
            p = feature["properties"]
            refs = p.get("_city_refs")
            points = list(geometry.coords)
            widths, prefs = list(extras[index][0]), list(extras[index][1])
            lanes = Counter()
            crossings = list(p.get("_city_crossing_points", []))
            def vote(j, line):
                lanes[extras[j][2]] += line.length
            vote(index, geometry)
            sources = set(source_ids(feature))
            uses = self.uses if walks[index] else self.drive_uses
            if refs:
                ends = [refs[0], refs[-1]]
                for side in (0, 1):
                    while uses[ends[side]] == 2 and len(endpoints[(walks[index], ends[side])]) == 2:
                        options = [(j,end) for j,end in endpoints[(walks[index], ends[side])] if j not in seen and signatures[j] == signatures[index]]
                        if len(options) != 1:
                            break
                        j, end = options[0]
                        other, shape_j = ordinary[j]
                        other_refs = other["properties"]["_city_refs"]
                        far = other_refs[0 if end == 1 else -1]
                        if far == ends[1-side]:
                            break  # Never create a self-loop that the native road contract cannot express.
                        new_points, new_widths, new_prefs = list(shape_j.coords), list(extras[j][0]), list(extras[j][1])
                        if end == side:
                            new_points.reverse(); new_widths.reverse(); new_prefs.reverse()
                        if (new_points[-1] if side == 0 else new_points[0]) != points[0 if side == 0 else -1]:
                            break
                        if len(points) + len(new_points) > 1024:
                            break
                        if side == 0:
                            points, widths, prefs = new_points[:-1] + points, new_widths + widths, new_prefs[:-1] + prefs
                        else:
                            points, widths, prefs = points + new_points[1:], widths + new_widths, prefs + new_prefs[1:]
                        ends[side] = far
                        sources.update(source_ids(other))
                        crossings.extend(other["properties"].get("_city_crossing_points", []))
                        vote(j, shape_j)
                        seen.add(j)
                        self.spend()
                p["_city_ends"] = [str(ref) for ref in ends]
            p["_city_sources"] = sorted(sources)
            if crossings: p["_city_crossing_points"] = list(dict.fromkeys(crossings))
            if not walks[index]:
                p["_city_lanes"] = max(((n, length) for n, length in lanes.items() if n is not None), key=lambda item: (item[1], item[0]), default=(None, 0))[0]
            quantized, kept_widths, kept_refs, last = [], [], [], 0
            for n, point in enumerate(points):
                snapped = self.snap(point)
                if quantized and snapped == quantized[-1]:
                    if n == len(points) - 1: kept_refs[-1] = prefs[n]  # The end keeps its source node.
                    continue
                if quantized: kept_widths.append(max(widths[last:n]))
                quantized.append(snapped); kept_refs.append(prefs[n]); last = n
            if len(quantized) >= 2: points, widths, prefs = quantized, kept_widths, kept_refs
            p["_city_widths_m"], p["_city_point_refs"] = widths, prefs
            p["width_m"] = max(widths)
            joined_geometry = LineString(points)
            if not joined_geometry.is_simple or points[0] == points[-1]:
                # Distinct OSM endpoint IDs can coincide geometrically. Keep
                # every edge in maximal simple paths, never weld those IDs or
                # discard a self-crossing source way.
                chains, chain = [], [0]
                for n in range(1, len(points)):
                    self.spend(len(chain))
                    trial = [points[k] for k in chain + [n]]
                    if len(chain) > 1 and (trial[0] == trial[-1] or not LineString(trial).is_simple):
                        chains.append(chain)
                        chain = [chain[-1], n]
                    else:
                        chain = chain + [n]
                chains.append(chain)
                for chain in chains:
                    piece = deepcopy(feature)
                    piece["properties"].pop("_city_ends",None)
                    a, b = chain[0], chain[-1]
                    piece["properties"].update(_city_widths_m=widths[a:b], _city_point_refs=prefs[a:b+1], width_m=max(widths[a:b]))
                    output.append((piece,LineString([points[k] for k in chain])))
            else:
                output.append((feature, joined_geometry))
        # The exact importer splits a closed ground way at every source vertex.
        # Rejoin consecutive pieces without hiding an incident source junction
        # or creating a from==to road. Original traversal ranges survive.
        fixed.sort(key=lambda item:(item[0]["properties"].get("osm_way_id",0),item[0]["properties"].get("osm_loop_range",[0])[0]))
        joined = []
        for feature, geometry in fixed:
            p = feature["properties"]
            if joined and "osm_loop_range" in p and p.get("road_kind") == "ground" and "elevations_m" not in p:
                previous, previous_geometry = joined[-1]
                q = previous["properties"]
                if q.get("osm_way_id") == p.get("osm_way_id") and "osm_loop_range" in q and "elevations_m" not in q and len(q["osm_node_refs"])+len(p["osm_node_refs"])-1<=1024 and q["osm_loop_range"][1] == p["osm_loop_range"][0] and q["osm_node_refs"][-1] == p["osm_node_refs"][0] and self.uses[p["osm_node_refs"][0]] == 2 and q["osm_node_refs"][0] != p["osm_node_refs"][-1]:
                    q["osm_node_refs"] += p["osm_node_refs"][1:]
                    q["osm_loop_range"][1] = p["osm_loop_range"][1]
                    previous["geometry"]["coordinates"] += feature["geometry"]["coordinates"][1:]
                    joined[-1] = (previous,LineString(list(previous_geometry.coords)+list(geometry.coords)[1:]))
                    continue
            joined.append((feature,geometry))
        for index,(feature,geometry) in enumerate(joined):
            p=feature["properties"]
            if gap == 0 or "osm_loop_range" not in p or p.get("road_kind") != "ground" or "elevations_m" in p or len(geometry.coords)<=2:
                continue
            candidate=geometry.simplify(min(4.0,gap/4),preserve_topology=True)
            if not candidate.is_simple or len(candidate.coords)==len(geometry.coords): continue
            ids=self.road_tree.query(candidate.envelope)
            self.spend(len(ids))
            if any(candidate.intersects(self.road_geometries[i]) and not geometry.intersects(self.road_geometries[i]) for i in ids): continue
            # Douglas-Peucker retains original vertices. Record their exact
            # source positions, including fractional crop ends, so removed
            # degree-two bends never erase original traversal or junctions.
            original=list(geometry.coords)
            lookup={}
            for i,point in enumerate(original): lookup.setdefault(point,i)
            indices=[lookup[point] for point in candidate.coords]
            if indices!=sorted(set(indices)): continue
            start,end=p["osm_loop_range"]
            p["_city_loop_positions"]=[start if i==0 else end if i==len(original)-1 else math.floor(start)+i for i in indices]
            p["osm_node_refs"]=[p["osm_node_refs"][i] for i in indices]
            feature["geometry"]["coordinates"]=[feature["geometry"]["coordinates"][i] for i in indices]
            joined[index]=(feature,candidate)
        for index,(feature,geometry) in enumerate(joined):
            p = feature["properties"]
            if "_city_estimated_m" not in p: continue
            # Estimated structures share ground nodes with quantized roads. Snap
            # them to the same lattice, dropping a vertex (and its height) that
            # collapses onto its predecessor; ends never move apart.
            points, heights, refs = [], [], []
            for i, point in enumerate(geometry.coords):
                snapped = self.snap(point)
                if points and snapped == points[-1]:
                    if i == len(geometry.coords) - 1: points.pop(); heights.pop(); refs.pop()
                    else: continue
                points.append(snapped); heights.append(p["_city_estimated_m"][i]); refs.append(p["_city_refs"][i])
            if len(points) < 2: continue
            p["_city_estimated_m"], p["_city_refs"] = heights, refs
            joined[index] = (feature, LineString(points))
        roads, self.road_rules["open_deck_ends"] = osm_roads.open_deck_ends(joined + output)
        return roads

    def snap(self, point):
        """Nearest whole 1:scale map centimetre in this projection's local metres."""
        snapped = []
        for axis,value in enumerate(point[:2]):
            cm = round((value+self.local[axis])*100)
            game_cm = math.copysign(math.floor(abs(cm)/self.scale+0.5),cm)
            snapped.append(game_cm*self.grid-self.local[axis])
        return tuple(snapped)

    def polygon_group(self, group, gap, buildings):
        try:
            return self._polygon_group(group, gap, buildings)
        except GEOSException:
            # A failed derived operation cannot repair, erase or relabel source
            # geometry. Keep that complete group unmerged and disclose the cost.
            self.retained_groups += 1
            return self.unmerged(group)

    def unmerged(self, group):
        # Unmerged members still use the map-centimetre lattice; an erased one
        # is restored by the source coverage step.
        snapped = [(f,shapely.set_precision(g, self.grid)) for f,g in group]
        return [(deepcopy(f),g) for f,g in snapped if not g.is_empty]

    def _polygon_group(self, group, gap, buildings):
        # Bound each GEOS operation independently; dense tiles split in source
        # order, never allocate an all-city pairwise distance/union matrix.
        if len(group) > MAX_GROUP:
            return [item for start in range(0, len(group), MAX_GROUP)
                    for item in self.polygon_group(group[start:start+MAX_GROUP], gap, buildings)]
        self.spend(len(group))
        shapes = [g for f,g in group]
        # A building group is one source (no fusion); its valid geometry needs no union.
        original = shapes[0] if len(shapes) == 1 else unary_union(shapes)
        holes = [Polygon(ring) for g in shapes for part in parts(g) for ring in part.interiors]
        protected_holes = unary_union(holes).difference(original) if holes else Polygon()
        candidate = original
        tolerance = min(BUILDING_TOLERANCE if buildings else 8.0, gap / 4)
        simpler = candidate.simplify(tolerance, preserve_topology=True) if tolerance else candidate
        if buildings:
            # Buildings are never gap-filled or fused: each source keeps its own
            # footprint; simplification may not grow into road space or courtyards.
            grown = simpler.difference(candidate) if simpler is not candidate else Polygon()
            if self.barrier_hit(original, grown, tolerance) or (not protected_holes.is_empty and not simpler.intersection(protected_holes).is_empty):
                simpler = candidate
        if not simpler.is_valid or simpler.is_empty:
            raise GEOSException("Derived polygon is invalid; retain the complete original group")
        # The final 1:scale map has whole centimetres. Snap derived boundaries to
        # that same lattice before inverse projection, so sub-centimetre buffer
        # slivers cannot become duplicate vertices during native adoption.
        snapped = shapely.set_precision(simpler, self.grid)
        if snapped.is_empty:
            self.retained_groups += 1
            return self.unmerged(group)
        simpler = snapped
        strict = all(strict_rings(g) for g in parts(simpler))
        if not strict and not protected_holes.is_empty:
            # Open, rather than fill, a courtyard which touches an outer edge
            # after map-centimetre rounding. At most two game centimetres of
            # additional clearance; original open space remains open.
            simpler = shapely.difference(simpler, protected_holes.buffer(self.building_clearance, join_style="mitre"), grid_size=self.grid)
            strict = all(strict_rings(g) for g in parts(simpler))
        geometries = sorted(parts(simpler), key=_key)
        # Large/complex merged courtyards stay as smaller valid source groups.
        too_complex = not strict or any(buildings and (len(g.interiors) > 16 or positions(g) > 512) for g in geometries)
        if len(group) > 1 and too_complex:
            middle = len(group)//2
            return self.polygon_group(group[:middle], gap, buildings) + self.polygon_group(group[middle:], gap, buildings)
        output = []
        members = np.array(shapes, dtype=object)
        for geometry in geometries:
            contributors = [group[i] for i in np.flatnonzero(shapely.intersects(members, geometry.buffer(self.grid)))]
            if not contributors:
                # GEOS closing can leave an isolated floating-point filler
                # sliver. It is newly derived, never an original component.
                # Do not invent a building for it; source coverage is checked
                # independently on the complete output below.
                continue
            feature = deepcopy(contributors[0][0])
            p = feature["properties"]
            p["_city_sources"] = sorted({identity for f,g in contributors for identity in source_ids(f)})
            if buildings and len(contributors) > 1:
                total = sum(g.area for f,g in contributors)
                p["height_m"] = round(sum(float(f["properties"].get("height_m", 12))*g.area for f,g in contributors)/total, 2)
                p["_city_estimated_height"] = True
            output.append((feature, geometry))
        return output

    def polygons(self, gap):
        if "groups" not in self.context:
            start, retained, limits = self.remaining, self.retained_groups, limit_snapshot()
            self.context.update(zip(("prepared", "fixed", "groups"), self.prepare()), trimmed=set(self.trimmed_buildings),
                                prepare_work=start-self.remaining, prepare_retained=self.retained_groups-retained,
                                prepare_limits=self.stage_limits(limits))
        else:
            # Same road space: replay the work charges, limit warnings and
            # disclosures. Review exclusions are already recorded (idempotent)
            # in the shared sets.
            self.spend(self.context["prepare_work"])
            limit_replay(self.context["prepare_limits"])
            self.retained_groups += self.context["prepare_retained"]
            self.trimmed_buildings.update(self.context["trimmed"])
        self.prepared, groups = self.context["prepared"], self.context["groups"]
        output = list(self.context["fixed"])
        for building, group in groups:
            output.extend(self.polygon_group(group, gap, building))
        return output

    def prepare(self):
        """Road-trimmed sources, protected buildings and aggregation groups. They
        depend on the derived road space only, not on the gap being filled."""
        groups, fixed = defaultdict(list), []
        prepared = []
        for index, (f,g) in enumerate(self.features):
            if g.geom_type == "LineString":
                continue
            p = f["properties"]
            building = not (p.get("osm_region") or p.get("landuse") in ("forest", "orchard"))
            if building:
                if index not in self.trim_windows:
                    self.trim_windows[index] = g.buffer(self.max_width/2+self.road_clearance).envelope
                ids = self.ground_tree.query(self.trim_windows[index])
                self.spend(len(ids))
                barriers = [self.ground_barriers[i].intersection(g.envelope) for i in ids]
                if p.get("_city_layer_building"):
                    lifted = self.structure_tree.query(g)
                    self.spend(len(lifted))
                    barriers += [self.structure_buffers[i].intersection(g.envelope) for i in lifted]
                road_space = unary_union(barriers)
                trimmed = g.difference(road_space)
                if trimmed.is_empty:
                    for identity in source_ids(f):
                        self.review.reject(identity, f"Building footprint is entirely inside derived ground-road space; it cannot retain a solid at 1:{self.scale} without blocking the road. Road widths may be estimates. Explicit source exclusion is required."
                                           if not p.get("_city_layer_building") else "Building above other features (positive layer) placed on the ground lies entirely inside derived road or source-height structure space. Explicit source exclusion is required.")
                        self.excluded_sources.add(identity)
                    continue
                if not trimmed.is_empty and trimmed.area < g.area-0.0001:
                    self.trimmed_buildings.update(source_ids(f))
                    g = trimmed
            prepared.append((f,g,building))
        singles = []
        for f,g,building in prepared:
            # Exclude the whole source object, including other multipart pieces,
            # only through the existing explicit ID/reason review contract.
            if self.excluded_sources.intersection(source_ids(f)):
                continue
            p = f["properties"]
            if building:
                # Every building keeps its own footprint (no gap filling or
                # fusion). Its record key groups it with the buildings of its
                # site (else 256 m source tile) and category as building parts.
                site = self.sites.key(f, g)
                if "_city_building" not in p: p["_city_building"] = p.get("usage", "yes")
                if "height_m" not in p and "_city_levels" in p:
                    p["height_m"] = osm_sites.LEVEL_M * p["_city_levels"]
                    p["_city_levels_height"] = True
                landmark = p.get("_city_landmark") or float(p.get("height_m", 12)) >= 40 or p["_city_building"] in ("public", "hospital", "school", "church", "cathedral")
                protected = landmark or (p.get("_city_name") and site[0] == "tile")
                # Untagged apartment-complex blocks get a seeded storey count
                # after the landmark test, which keeps the source height.
                tall = osm_sites.complex_height(self.sites, site, p, g, min(source_ids(f)))
                if tall is not None:
                    p["height_m"] = tall
                    p["_city_levels_height"] = True
                    p["_city_complex_height"] = True
                # The facade (material, use, roof) is part of the record key, so
                # grouped parts share one appearance (MapKit parts share them).
                p["material"], p["usage"], p["roof"], p["_city_usage_inferred"] = osm_sites.facade(p, self.sites.kind(site))
                properties = {k:v for k,v in p.items() if not k.startswith("_city") and k not in ("osm_source_id", "height_m", "base_m")}
                record = json.dumps(["own", source_ids(f)] if protected else [list(site), properties], sort_keys=True)
                f = dict(f, properties=dict(p, _city_record=record))
                if protected:
                    # Preserve identity/height, unsimplified. Quantization still
                    # uses the same map-centimetre lattice as other geometry.
                    fixed.extend(self.polygon_group([(f,g)],0,True))
                else:
                    singles.append((f,g))
                continue
            properties = {k:v for k,v in p.items() if not k.startswith("_city") and k not in ("osm_source_id", "height_m")}
            # A fixed source-metre grid bounds aggregation extent independently
            # of the city, output origin, crop size or source object order.
            centre = g.centroid
            key = (building, math.floor(centre.x/256), math.floor(centre.y/256), 0, json.dumps(properties, sort_keys=True))
            groups[key].append((f,g))
        singles.sort(key=lambda item:(source_ids(item[0]), _key(item[1])))
        return ([(f,g) for f,g,building in prepared], fixed,
                [(True, [item]) for item in singles] + [(key[0], sorted(groups[key], key=lambda item:(source_ids(item[0]), _key(item[1])))) for key in sorted(groups)])

    def native_polygon_parts(self, geometry, depth=0):
        result = []
        for part in parts(geometry):
            self.spend(positions(part))
            if positions(part) <= 512 and len(part.interiors) <= 16 and strict_rings(part):
                result.append(part)
                continue
            if depth >= BUILDING_SPLIT_CEILING: raise BudgetExceeded("City building partition ceiling exceeded")
            if depth >= BUILDING_SPLIT_DEPTH: soft_limit("city_building_partition", depth + 1, BUILDING_SPLIT_DEPTH, "City building partition depth budget exceeded")
            x0,y0,x1,y1 = part.bounds
            axis = 0 if x1-x0 >= y1-y0 else 1
            middle = round(((x0+x1) if axis == 0 else (y0+y1))/2/self.grid)*self.grid
            half = self.building_clearance  # Half the partition gap on each side.
            rectangles = [box(x0-1,y0-1,middle-half,y1+1),box(middle+half,y0-1,x1+1,y1+1)] if axis == 0 else [box(x0-1,y0-1,x1+1,middle-half),box(x0-1,middle+half,x1+1,y1+1)]
            for rectangle in rectangles:
                result.extend(self.native_polygon_parts(shapely.intersection(part,rectangle,grid_size=self.grid),depth+1))
        return result

    def water(self, lines):
        """City water: OSM water areas plus waterway ribbons (source width,
        at least WATER_MIN_WIDTH_CM on the map) minus ground vehicle roads with
        their sidewalks and clearance, and walking ways. United on the map
        lattice and cut like paint into hole-free pieces per WATER_CELL_CM; each
        piece keeps the sources it covers. A waterway wholly under roads is
        disclosed as dropped. Returns (items, counts, dropped sources)."""
        counts = Counter()
        sources = []
        for f, g in self.features:
            p = f["properties"]
            if g.geom_type != "LineString" and p.get("osm_region") and p.get("landuse") in osm_sites.WATER:
                sources.append((source_ids(f), g))
                counts["areas"] += 1
        minimum = WATER_MIN_WIDTH_CM * self.scale / 100
        for f, g in lines:
            width = max(float(f["properties"]["_city_waterway"]["width_m"]), minimum)
            sources.append((source_ids(f), g.buffer(width / 2, quad_segs=2)))
            counts["waterways"] += 1
        if not sources:
            return [], counts, []
        cuts = []
        for f, g in self.features:
            p = f["properties"]
            if g.geom_type != "LineString" or not osm_roads.ground(f, g) or "_city_estimated_m" in p: continue
            if is_walking(f):
                cuts.append(g.buffer(float(p.get("width_m", 1.6)) / 2, quad_segs=2))
            elif osm_roads.driving(f, g):
                cuts.append(g.buffer(clear_width(f, self.furniture) / 2 + self.road_clearance, quad_segs=2))
        self.spend(sum(positions(g) for _, g in sources) + sum(positions(g) for g in cuts))
        lx, ly = self.local
        factor, grid = self.to_map_factor, self.grid
        to_map = lambda x, y: ((x+lx)*factor, (y+ly)*factor)
        from_map = lambda x, y: (x*grid-lx, y*grid-ly)
        areal = lambda g: g if g.geom_type in ("Polygon", "MultiPolygon") else shapely.union_all(parts(g), grid_size=1)
        shapes = [areal(shapely.make_valid(shapely.set_precision(moved(g, to_map), 1))) for _, g in sources]
        water = areal(shapely.union_all(shapes, grid_size=1))
        if cuts:
            blocked = shapely.union_all(list(shapely.set_precision(moved(np.array(cuts, dtype=object), to_map), 1)), grid_size=1)
            water = areal(shapely.difference(water, blocked, grid_size=1))
        tree = STRtree(shapes)
        output, kept = [], set()
        if not water.is_empty:
            x0, y0, x1, y1 = water.bounds
            for i in range(math.floor(x0/WATER_CELL_CM), math.floor(x1/WATER_CELL_CM)+1):
                for j in range(math.floor(y0/WATER_CELL_CM), math.floor(y1/WATER_CELL_CM)+1):
                    cell = box(i*WATER_CELL_CM, j*WATER_CELL_CM, (i+1)*WATER_CELL_CM, (j+1)*WATER_CELL_CM)
                    local = areal(shapely.intersection(water, cell, grid_size=1))
                    if local.is_empty: continue
                    for piece in self.paint_parts(local):
                        if piece.area < MIN_AREA_PIECE_CM2:
                            counts["slivers"] += 1
                            continue
                        owners = set()
                        for k in tree.query(piece):
                            self.spend()
                            if shapely.intersection(shapes[k], piece).area > 0: owners.update(sources[k][0])
                        if not owners: continue
                        kept.update(owners)
                        output.append((dict(type="Feature", properties=dict(_city_water=dict(surface_m=round(WATER_SURFACE_CM*self.scale/100, 2),
                            bottom_m=round(-WATER_DEPTH_CM*self.scale/100, 2)), _city_sources=sorted(owners), osm_source_id=min(owners)), geometry=None), piece))
        counts["pieces"] = len(output)
        counts["positions"] = sum(positions(g) for f, g in output)
        dropped = sorted({s for ids, g in sources for s in ids} - kept)
        line_ids = {s for f, g in lines for s in source_ids(f)}
        dropped = [s for s in dropped if s in line_ids]  # Water areas stay mapped as regions.
        return [(f, g) for (f, _), g in zip(output, moved([g for f, g in output], from_map))], counts, dropped

    def paint_parts(self, geometry, depth=0):
        # Native surface areas are simple and hole-free. Cut through each hole
        # (or the middle of an oversized part) along a whole map-centimetre line.
        result = []
        for part in parts(geometry):
            self.spend(positions(part))
            holes = [h for h in part.interiors if max(h.bounds[2]-h.bounds[0], h.bounds[3]-h.bounds[1]) >= 2]
            part = Polygon(part.exterior, holes)  # Sub-centimetre holes are painted over.
            if not holes and positions(part) <= PAINT_VERTICES + 1:
                result.append(straight(part))
                continue
            if depth >= PAINT_SPLIT_CEILING: raise BudgetExceeded("City paint partition ceiling exceeded")
            if depth >= PAINT_SPLIT_DEPTH: soft_limit("city_paint_partition", depth + 1, PAINT_SPLIT_DEPTH, "City paint partition depth budget exceeded")
            x0,y0,x1,y1 = holes[0].bounds if holes else part.bounds
            axis = 0 if x1-x0 >= y1-y0 else 1
            cut = math.floor(((x0+x1) if axis == 0 else (y0+y1))/2)
            x0,y0,x1,y1 = part.bounds
            halves = [box(x0-1,y0-1,cut,y1+1),box(cut,y0-1,x1+1,y1+1)] if axis == 0 else [box(x0-1,y0-1,x1+1,cut),box(x0-1,cut,x1+1,y1+1)]
            for half in halves:
                result.extend(self.paint_parts(shapely.intersection(part,half,grid_size=1),depth+1))
        return result

    def paint(self, walking, tolerance=0.0):
        """Paths, footways and cycleways become ground paint, not road records;
        green land becomes grass and parking asphalt paint (city ground).

        Pedestrian ribbons are united on the 1:scale map-centimetre lattice and
        cut per native cell, so the pieces never overlap; each keeps every source
        way it covers and takes the surface covering most of its area. Area
        paint follows in surface priority order (asphalt, concrete, gravel, dirt,
        grass), each minus water and everything painted before it, so pieces of
        different surfaces never overlap either. Buildings are not subtracted
        (they stand on top) and roads keep precedence natively.
        """
        areas, water = osm_sites.ground_areas(self.features, tolerance, SURFACES, source_ids)
        self.paint_counts = Counter()
        if not walking and not areas:
            return []
        lx, ly = self.local
        factor, grid = self.to_map_factor, self.grid
        to_map = lambda x, y: ((x+lx)*factor, (y+ly)*factor)
        from_map = lambda x, y: (x*grid-lx, y*grid-ly)
        owners = []
        for feature, geometry in walking:
            self.spend(positions(geometry))
            owners.append((source_ids(feature), feature["properties"].get("_city_paint_surface") or feature["properties"].get("surface", "concrete")))
        ribbons = shapely.buffer(np.array([g for f,g in walking], dtype=object), np.array([float(f["properties"].get("width_m", 1.6)) for f,g in walking])/2, quad_segs=2) if walking else np.zeros(0, dtype=object)
        ribbons = list(shapely.set_precision(moved(ribbons, to_map), 1)) if walking else []
        tree = STRtree(ribbons)
        polygonal = lambda geometries: [unary_union(parts(g)) if g.geom_type not in ("Polygon", "MultiPolygon") else g
                                        for g in shapely.make_valid(shapely.set_precision(moved(np.array(geometries, dtype=object), to_map), 1))]
        shapes = polygonal([g for _, _, g in areas]) if areas else []
        waters = polygonal(water) if water else []
        self.spend(sum(positions(g) for g in shapes) + sum(positions(g) for g in waters))
        # Ribbons are cut per PAINT_CELL, areas per PAINT_CELL × AREA_FACTOR.
        area_cell = PAINT_CELL * AREA_FACTOR
        cells, area_cells = defaultdict(list), defaultdict(lambda: ([], []))
        for kind, items in ((0, ribbons), (1, shapes), (2, waters)):
            size = PAINT_CELL if kind == 0 else area_cell
            for index, item in enumerate(items):
                if item.is_empty: continue
                x0,y0,x1,y1 = item.bounds
                for i in range(math.floor(x0/size), math.floor(x1/size)+1):
                    for j in range(math.floor(y0/size), math.floor(y1/size)+1):
                        if kind == 0: cells[(i,j)].append(index)
                        else: area_cells[(i,j)][kind-1].append(index)
        output, taken = [], {}
        for i, j in sorted(cells):
            ribbon_ids = cells[(i,j)]
            cell = box(i*PAINT_CELL, j*PAINT_CELL, (i+1)*PAINT_CELL, (j+1)*PAINT_CELL)
            self.spend(len(ribbon_ids))
            local = shapely.intersection(shapely.union_all([ribbons[k] for k in ribbon_ids], grid_size=1), cell, grid_size=1)
            for piece in self.paint_parts(local):
                sources, surfaces = set(), Counter()
                for k in tree.query(piece):
                    self.spend()
                    area = shapely.intersection(ribbons[k], piece).area
                    if area > 0:
                        sources.update(owners[k][0])
                        surfaces[owners[k][1]] += area
                if not sources:
                    continue  # A lattice sliver of a ribbon already covered elsewhere.
                surface = sorted(surfaces.items(), key=lambda item:(-item[1], item[0]))[0][0]
                output.append((dict(type="Feature", properties=dict(_city_paint=surface, _city_sources=sorted(sources), osm_source_id=min(sources)), geometry=None), piece))
                self.paint_counts["pedestrian"] += 1
            taken[(i,j)] = local
        # Lattice overlays may add lower-dimension slivers; keep polygons only.
        areal = lambda g: g if g.geom_type in ("Polygon", "MultiPolygon") else shapely.union_all(parts(g), grid_size=1)
        for i, j in sorted(area_cells):
            area_ids, water_ids = area_cells[(i,j)]
            if not area_ids: continue
            cell = box(i*area_cell, j*area_cell, (i+1)*area_cell, (j+1)*area_cell)
            self.spend(len(area_ids) + len(water_ids))
            clipped = {k: areal(shapely.intersection(shapes[k], cell, grid_size=1)) for k in area_ids}
            blocked = [areal(shapely.intersection(waters[k], cell, grid_size=1)) for k in water_ids]
            blocked += [areal(taken[(a, b)]) for a in range(i*AREA_FACTOR, (i+1)*AREA_FACTOR) for b in range(j*AREA_FACTOR, (j+1)*AREA_FACTOR) if (a, b) in taken]
            blocked = areal(shapely.union_all(blocked, grid_size=1)) if blocked else None
            for surface in osm_sites.AREA_SURFACES:
                members = [k for k in area_ids if areas[k][1] == surface and not clipped[k].is_empty]
                if not members: continue
                local = areal(shapely.union_all([clipped[k] for k in members], grid_size=1))
                if blocked is not None and not blocked.is_empty:
                    local = areal(shapely.difference(local, blocked.buffer(PAINT_MARGIN_CM, quad_segs=1, join_style="mitre"), grid_size=1))
                if local.is_empty: continue
                for piece in self.paint_parts(local):
                    if piece.area < MIN_AREA_PIECE_CM2:
                        self.paint_counts["slivers"] += 1
                        continue  # A sliver left by cell cuts, ribbons or water; sources stay mapped as areas.
                    sources = set()
                    for k in members:
                        self.spend()
                        if shapely.intersection(clipped[k], piece).area > 0: sources.update(areas[k][0])
                    if not sources: continue
                    output.append((dict(type="Feature", properties=dict(_city_paint=surface, _city_sources=sorted(sources), osm_source_id=min(sources)), geometry=None), piece))
                    self.paint_counts[surface] += 1
                blocked = local if blocked is None else areal(shapely.union(blocked, local, grid_size=1))
        self.paint_ways = len(walking)
        self.paint_counts["pieces"] = len(output)
        self.paint_counts["positions"] = sum(positions(g) for f, g in output)
        return [(f,g) for (f,_),g in zip(output, moved([g for f,g in output], from_map))]

    def resolve_buildings(self, items):
        buildings = [(f,g) for f,g in items if is_building(f,g)]
        rest = [(f,g) for f,g in items if not is_building(f,g)]
        buildings.sort(key=lambda item:(-float(item[0]["properties"].get("height_m",12)),not bool(item[0]["properties"].get("_city_name")),-item[1].area,source_ids(item[0]),_key(item[1])))
        tree = STRtree([g for f,g in buildings])
        accepted = {}
        self.overlap_sources = set()
        for index,(feature,geometry) in enumerate(buildings):
            clearance = self.building_clearance
            candidates = [int(i) for i in tree.query(geometry.buffer(clearance).envelope) if int(i) in accepted]
            self.spend(len(candidates))
            neighbors = [i for i in candidates if accepted[i][1].buffer(clearance,join_style="mitre").intersects(geometry)]
            if neighbors:
                occupied = unary_union([accepted[i][1].buffer(clearance,join_style="mitre") for i in neighbors])
                trimmed = shapely.difference(geometry,occupied,grid_size=self.grid)
                self.overlap_sources.update(source_ids(feature))
                if trimmed.is_empty:
                    # A fully enclosed/duplicate building is represented by its
                    # enclosing volume. Keep every source ID and recorded name;
                    # the chosen taller envelope's height is disclosed as an
                    # approximation for the absorbed object, never a survey.
                    owner = max(neighbors,key=lambda i:(accepted[i][1].intersection(geometry).area,-i))
                    p = accepted[owner][0]["properties"]
                    p["_city_sources"] = sorted(set(source_ids(accepted[owner][0]))|set(source_ids(feature)))
                    names = set(p.get("_city_names",[])) | set(feature["properties"].get("_city_names",[]))
                    names.update(n for n in (p.get("_city_name"),feature["properties"].get("_city_name")) if n)
                    p["_city_names"] = sorted(names)
                    p["_city_estimated_height"] = True
                    continue
                geometry = trimmed
            accepted[index] = (feature,geometry)  # Owned by this candidate; parts copy below.
        for feature,geometry in accepted.values():
            rest.extend((deepcopy(feature),part) for part in self.separated_parts(geometry))
        return rest

    def separated_parts(self, geometry):
        # Native buildings may not even touch. Parts of one source geometry that
        # meet at a point keep the same building clearance as other neighbours.
        kept = []
        for part in self.native_polygon_parts(geometry):
            self.spend(len(kept))
            near = [k for k in kept if k.intersects(part)]
            if not near:
                kept.append(part)
                continue
            trimmed = shapely.difference(part, unary_union([k.buffer(self.building_clearance, join_style="mitre") for k in near]), grid_size=self.grid)
            kept.extend(p for p in self.native_polygon_parts(trimmed) if not any(p.intersects(k) for k in kept))
        return kept

    def road_space(self, gap):
        """Derived roads and the space buildings keep clear of; ground pedestrian
        ways are split off for paint."""
        roads = self.roads(gap)
        structural = frozenset(ref for f,g in roads if f["properties"].get("road_kind","ground") != "ground" or "elevations_m" in f["properties"]
                               for ref in f["properties"].get("osm_node_refs", []))
        # Markings, junction-end crosswalks and the MapKit paint segment bound,
        # over the records that stay roads (painted ways become ground paint).
        is_road = lambda f, g: not is_walking(f, structural)
        roads, counts = osm_roads.finish(roads, self.scale, self.crossing_points, self.crossing_lines, is_road, self.spend)
        self.finish_counts = Counter(counts)
        self.paint_bound = osm_roads.paint_bound(roads, self.scale, is_road)
        derived = [(g, clear_widths(f, g, self.furniture)) for f,g in roads]
        self.barrier_buffers = np.concatenate([self.road_buffers, np.array(segment_buffers(derived, self.road_clearance), dtype=object)])
        self.barrier_tree = STRtree(self.road_geometries + [g for f,g in roads])
        ground = [line for (f,g), line in zip(roads, derived) if f["properties"].get("road_kind","ground") == "ground"]
        lines = list(zip(self.ground_geometries,self.ground_widths))+ground
        self.ground_barriers = list(self.ground_buffers) + segment_buffers(ground, self.road_clearance)
        # A junction surface is the hull of its approach mouths, which reaches up to
        # √2 × the widest half width from the node; keep buildings outside it too.
        # Each approach counts with the width of its end segment.
        ends = defaultdict(list)
        for g,w in lines:
            for (x,y), width in ((g.coords[0], w[0]), (g.coords[-1], w[-1])):
                ends[(round(x,2),round(y,2))].append(width)
        # The 16-gon circumscribes the disk (its edges never cut inside the radius).
        self.junction_disks = [shapely.Point(point).buffer((max(widths)/2*math.sqrt(2)+self.road_clearance)/math.cos(math.pi/16), quad_segs=4)
                               for point,widths in sorted(ends.items()) if len(widths) > 1]
        # MapKit rounds each inside corner between adjacent arms with a curb
        # fillet that bulges into the block beyond both road edges.
        self.junction_disks += [w.buffer(self.road_clearance, join_style="mitre") for w in corner_fillets([(f, g) for f, g in roads if is_road(f, g)], self.scale)]
        self.junction_tree = STRtree(self.junction_disks)
        self.ground_barriers += self.junction_disks
        self.ground_tree = STRtree(self.ground_barriers)
        # Pedestrian ways still keep merged buildings and derived road space
        # clear above, but are represented as painted ground below.
        return [(f,g) for f,g in roads if not is_walking(f, structural)], [(f,g) for f,g in roads if is_walking(f, structural)]

    def candidate(self, gap):
        try:
            return self._candidate(gap)
        finally:
            self.settle_work()

    def _candidate(self, gap):
        self.remaining = MAX_WORK
        self.work_over = False
        self.retained_groups = 0
        self.trimmed_buildings = set()
        # Road space depends on the gap only through the line tolerance, equal for
        # 16-64 m gaps. Reuse it and everything derived from it (trimmed sources,
        # protected buildings, groups, paint), replaying their work charges.
        shared = ("barrier_buffers", "barrier_tree", "ground_barriers", "junction_disks", "junction_tree", "ground_tree", "finish_counts", "paint_bound")
        tolerance = min(4.0, gap/4)
        if self.context.get("tolerance") == tolerance:
            self.spend(self.context["road_work"])
            limit_replay(self.context["road_limits"])
            for name in shared:
                setattr(self, name, self.context[name])
        else:
            # Exclusions come only from the road space of the candidate kept.
            self.excluded_sources = set()
            self.review.restore(self.reviewed)
            start, limits = self.remaining, limit_snapshot()
            driving, walking = self.road_space(gap)
            self.context = dict(tolerance=tolerance, driving=driving, walking=walking, road_work=start-self.remaining,
                                road_limits=self.stage_limits(limits), **{name: getattr(self, name) for name in shared})
        driving, walking = self.context["driving"], self.context["walking"]
        items = driving + self.polygons(gap)
        # A multipart source remains fully represented by separate native
        # polygons. Touching components must not be misrepresented as holes.
        items = [(deepcopy(f),native) for f,g in items for part in ([g] if g.geom_type == "LineString" else parts(g))
                 for native in ([part] if part.geom_type == "LineString" or is_building(f,part) else self.native_polygon_parts(part))]
        # A source erased by merging or quantization keeps its road-trimmed shape
        # on the map-centimetre lattice, then meets the same overlap partition.
        covered = {identity for f,g in items + walking for identity in source_ids(f)}
        for f,g in self.prepared:
            if set(source_ids(f)) <= covered or self.excluded_sources.intersection(source_ids(f)):
                continue
            snapped = shapely.set_precision(g, self.grid)
            if snapped.is_empty:
                continue
            self.retained_groups += 1
            covered.update(source_ids(f))
            items.extend((deepcopy(f),part) for part in (parts(snapped) if is_building(f,snapped) else self.native_polygon_parts(snapped)))
        items = self.resolve_buildings(items)
        # A gable roof survives only on a final axis-aligned rectangular solid;
        # the roof is part of the record key, so a flattened solid regroups.
        for f, g in items:
            p = f["properties"]
            if is_building(f, g) and p.get("roof") == "gable" and not osm_sites.rectangular(g):
                p["roof"] = "flat"
                record = json.loads(p["_city_record"]) if p.get("_city_record") else None
                if record and record[0] != "own":
                    record[1]["roof"] = "flat"
                    p["_city_record"] = json.dumps(record, sort_keys=True)
        # Nearby buildings of one site and category share a record (MapKit
        # building parts); each solid stays its own visible prism.
        items, self.record_counts = osm_sites.building_records(items, is_building, source_ids, _key)
        items += [(deepcopy(f), g) for f, g in self.barriers.items]
        items += [(deepcopy(f), g) for f, g in self.water_items]
        # Area paint simplifies like other areas, so it is shared only by gaps
        # with the same area tolerance as well as the same road space.
        area_tolerance = min(8.0, gap/4)
        if "paint" in self.context and self.context.get("paint_tolerance") == area_tolerance:
            self.spend(self.context["paint_work"])
            limit_replay(self.context["paint_limits"])
        else:
            start, self.paint_ways, limits = self.remaining, 0, limit_snapshot()
            self.context.update(paint=self.paint(walking, area_tolerance), paint_tolerance=area_tolerance)
            self.context.update(paint_work=start-self.remaining, paint_ways=self.paint_ways, paint_limits=self.stage_limits(limits), paint_counts=dict(self.paint_counts))
        self.paint_ways = self.context["paint_ways"]
        # Output features are completed in place below; cached paint gets copies.
        items += [(dict(f, properties=dict(f["properties"], _city_sources=list(f["properties"]["_city_sources"]))), g) for f,g in self.context["paint"]]
        self.trimmed_buildings.difference_update(self.excluded_sources)
        def order(item):
            feature, geometry = item
            p = feature["properties"]
            traversal = (0,p.get("osm_loop_range",[p.get("_city_crop_feature",0)])[0]) if "osm_node_refs" in p else (1,_key(geometry))
            return geometry.geom_type,source_ids(feature),traversal
        items.sort(key=order)
        # Every supported source object remains represented, including split
        # parts. Unsupported exclusions are a separate, explicitly reviewed list.
        retained = {identity for f,g in items for identity in source_ids(f)}
        expected = set(self.input_ids) - self.excluded_sources
        missing = expected - retained
        # A road-trimmed building whose remainder vanished on the lattice must
        # not come back untrimmed inside the road: exclude it explicitly.
        for identity in sorted(missing & self.trimmed_buildings):
            self.review.reject(identity, f"Building footprint outside derived ground-road space is smaller than the 1:{self.scale} map lattice; it cannot retain a solid without blocking the road. Road widths may be estimates. Explicit source exclusion is required.")
            self.excluded_sources.add(identity)
        self.trimmed_buildings.difference_update(self.excluded_sources)
        expected = set(self.input_ids) - self.excluded_sources
        missing = expected - retained
        if missing:
            # Quantization or a derived courtyard clearance must not erase a
            # small source island. Keep those original features unmerged; they
            # still face the ordinary native geometry/output budget checks.
            for feature, geometry in self.features:
                if missing.intersection(source_ids(feature)):
                    items.append((deepcopy(feature),geometry))
                    self.retained_groups += 1
            items.sort(key=order)
            retained = {identity for f,g in items for identity in source_ids(f)}
        if retained != expected:
            raise ValueError("City optimization source coverage mismatch")
        result = {k:deepcopy(v) for k,v in self.collection.items() if k != "features"}
        result["features"] = []
        groups = []
        # Protected graph geometry must preserve its exact source order and
        # values; recomputing it would invalidate loop/crop height provenance.
        derived = iter(moved([g for f,g in items if "osm_node_refs" not in f["properties"]], self.inverse))
        for feature, geometry in items:
            p = feature["properties"]
            p["_city_sources"] = source_ids(feature)
            groups.append(dict(source_ids=p["_city_sources"], name=p.get("_city_name", ""), names=p.get("_city_names",[]), estimated_height=bool(p.get("_city_estimated_height"))))
            if "osm_node_refs" not in p:
                feature["geometry"] = json.loads(json.dumps(mapping(next(derived))))
            result["features"].append(feature)
        meta = dict(profile=PROFILE, scale_denominator=self.scale, gap_m=gap, grid_m=self.grid,
                    vegetation_spacing_m=32, vegetation_density_per_mille=750,
                    surface_mappings=[dict(source=s,target=t,features=n) for (s,t),n in sorted(self.surface_mappings.items())],
                    widened_roads=self.widened_roads, minimum_road_width_m=self.minimum_width,
                    estimated_road_widths=dict(sorted(self.estimated_widths.items())),
                    road_clearance_m=self.road_clearance, trimmed_building_sources=sorted(self.trimmed_buildings),
                    building_clearance_m=self.building_clearance, polygon_partition_gap_m=self.partition_gap, overlap_adjusted_sources=sorted(self.overlap_sources),
                    line_tolerance_m=min(4.0, gap/4), polygon_tolerance_m=min(8.0, gap/4), building_tolerance_m=min(BUILDING_TOLERANCE, gap/4),
                    before=self.before, after=self.counts(items), source_ids=sorted(expected),
                    unmerged_numeric_groups=self.retained_groups, painted_pedestrian_ways=self.paint_ways,
                    level_structures=self.level_structures,
                    road_rules=dict(sorted((self.road_rules + self.finish_counts).items())), paint_segment_bound=self.paint_bound,
                    layered_buildings=sum(bool(f["properties"].get("_city_layer_building")) and not self.excluded_sources.intersection(source_ids(f)) for f,g in self.features),
                    estimated_structure_roads=sum("_city_estimated_m" in f["properties"] for f,g in items),
                    groups=groups, protected_buildings=sum(bool(f["properties"].get("_city_name") or f["properties"].get("_city_landmark") or float(f["properties"].get("height_m",12))>=40) for f,g in items if is_building(f,g)),
                    building_records=dict(sorted(self.record_counts.items())),
                    barriers=dict(sorted((self.barriers.counts + Counter({"kind_" + k: n for k, n in self.barriers.kinds.items()})).items()), dropped_sources=sorted(set(self.barriers.dropped) - set(self.input_ids))),
                    ground_paint=dict(sorted(self.context.get("paint_counts", {}).items())),
                    water=dict(sorted(self.water_counts.items()), dropped_sources=self.water_dropped))
        return result, meta


def candidates(collection, options, review=None, scale=SCALE):
    """Largest gap first: it simplifies most. Callers take the first
    candidate that meets the targets; smaller gaps are built only after a miss or
    failure. A gap whose partition ceilings or road space cannot be met yields
    (None, failure) instead. Soft budgets met while building a gap are recorded
    as limit warnings of that gap only."""
    worker = Generalizer(collection, options, review, scale)
    # Limit warnings belong to the candidate they were met in.
    base = limit_snapshot()
    # Dense sources skip the 0–2 m gaps (source metres at every scale: a 4 m gap
    # is 0.5 m on a 1:8 map); all protected geometry and final admission still apply.
    built = set()
    for gap in reversed(LEVELS[2 if worker.before["features"] > 20000 else 0:]):
        # Without building gap filling a gap acts only through its line,
        # building and area tolerances; a gap repeating them gives the same
        # candidate and is not built again (64 and 32 m).
        tolerances = (min(4.0, gap/4), min(8.0, gap/4), min(BUILDING_TOLERANCE, gap/4))
        if tolerances in built: continue
        built.add(tolerances)
        limit_restore(base)
        try:
            result = worker.candidate(gap)
        except ValueError as exc:
            # Own partition ceilings, or a building the straighter road covers; a
            # smaller gap keeps more bends. The review's aggregate ceiling stays fatal.
            if not (isinstance(exc, BudgetExceeded) and str(exc).startswith("City ")) and "Explicit source exclusion is required" not in str(exc):
                raise
            result = None, dict(gap_m=gap, failure=str(exc))
        yield result
