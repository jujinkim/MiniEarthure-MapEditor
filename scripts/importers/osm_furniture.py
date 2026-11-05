"""Generated city street furniture, road signs and park details (Editor-only, current v1).

OSM gives where bus stops, stations, subway entrances and signals are, not what
they look like; parks give an area. These rules place MapKit builtins at those
positions with fixed-seed variation, in the layer's source centimetres (÷D at
adoption), clear of road corridors, junction mouths, buildings, water and each
other. Road signs follow (`Furniture.road_signs`): OSM stop/give-way nodes,
then signs derived from the road graph, its markings, the OSM road class and
posted speed, and school sites. Street planting follows: street trees in
pits beside the curb of sidewalk roads (`street_trees`, OSM trees first),
median beds between one-way pairs (`median_beds`) and planters along building
fronts (`planters`). City streetlights close the list (`streetlights`): poles
behind the sidewalk of arterials and collectors with the head over the lanes,
in the gaps between street-tree crowns. A candidate that finds no free spot is
skipped and counted.
"""
from collections import Counter
import hashlib
import math

from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

# Map-centimetre sizes (×D gives source cm): footprint half sizes along local
# x (across the asset's front) and y.
SIZES = {"builtin:signal_h": (4, 4), "builtin:signal_v": (4, 4), "builtin:bus_shelter": (80, 25),
         "builtin:subway_entrance": (40, 60), "builtin:station_sign": (12, 12), "builtin:bench": (40, 40),
         "builtin:shrub": (35, 35), "builtin:tree": (200, 200)}
CLEARANCE_CM = 30  # Beyond the road edge and sidewalk.
GAP_CM = 10  # Between placements.
ROAD_FLOOR_CM = 150  # The adoption road width floor (import_units.gd ROAD_WIDTH_FLOOR_CM).
PARK_KINDS = ("park", "garden", "playground", "recreation_ground", "village_green")
# Park trees are MapKit vegetation zones of city trees (osm_generalize.CITY_ZONES).
PARK_GRID_CM = {"builtin:bench": 1500, "builtin:shrub": 600}
PARK_CHANCE = {"builtin:bench": 0.25, "builtin:shrub": 0.35}
MAX_PLACEMENTS = 24_000
BUCKET_CM = 3000
SIGNAL_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary")

# Road signs (map cm, ×D for source cm). Pole signs reserve their plate width
# across local x; the guide sign reserves only its pole (the display-only arm
# and board overhang the road from 1.70 m up).
SPEEDS = (30, 40, 50, 60, 80, 100)
SIGN_POLE = ("builtin:sign_stop", "builtin:sign_yield", "builtin:sign_crossing", "builtin:sign_children",
             *(f"builtin:sign_speed_{v}" for v in SPEEDS))
GUIDE = "builtin:guide_sign"
SIZES |= {asset: (16, 6) for asset in SIGN_POLE} | {GUIDE: (8, 8)}
# Speed of a road class without a posted maxspeed; other classes get no sign.
CLASS_SPEED = {"motorway": 100, "trunk": 80, "primary": 50, "secondary": 50, "tertiary": 50,
               "motorway_link": 40, "trunk_link": 40, "primary_link": 40, "secondary_link": 40, "tertiary_link": 40}
SPEED_EXIT_CM, SPEED_REPEAT_CM, SPEED_MIN_ROAD_CM, SPEED_DEDUPE_CM = 1000, 25000, 2500, 12000
GUIDE_SETBACK_CM, GUIDE_MIN_ROAD_CM, GUIDE_MAX_SIDEWALK_CM, GUIDE_REACH_CM, GUIDE_DEDUPE_CM = 2000, 3000, 100, 260, 12000
CROSSING_SETBACK_CM = 200  # Behind the junction mouth, before the painted crosswalk.
MINOR_SETBACK_CM = 100
MINOR_MIN_ROAD_CM = 2000
SCHOOL_ZONE_CM, SCHOOL_POI_CM, CHILDREN_DEDUPE_CM, SCHOOL_SPEED_CM = 3000, 4000, 6000, 400
SIGNAL_CLEAR_CM = 500  # Speed, children and guide poles keep this far from signal poles.
TAGGED_REACH_CM = 2000  # Across to the road; at most twice this along it before the junction.
# Classes without school zones (no children signs, posted or class speed kept).
SCHOOL_EXCLUDED = ("motorway", "motorway_link", "trunk", "trunk_link")
SIGN_CAPS = {"guide_signs": 250, "crossing_signs": 400, "stop_signs": 250, "yield_signs": 150,
             "children_signs": 250, "speed_signs": 700}
ROAD_SIGN_LIMIT = 1500  # All road signs of a layer; MAX_PLACEMENTS still applies.
HEADING_COS = math.cos(math.radians(35))
OBLIQUE_COS = 0.5

# Street planting (map cm, ×D for source cm), mirrors of the MapKit v1 contract
# (spec/CURRENT_V1.md): a street tree reserves a 40 cm pit turned with the road
# (local x along it) and its display-only crown reaches STREET_TREE_CROWN_CM from
# the trunk, at least STREET_CANOPY_MIN_CM up beyond 30 cm of it.
STREET_TREE_PIT_CM = 40
STREET_CANOPY_MIN_CM = 120
STREET_TREE_CROWN_CM = {"builtin:street_tree_ginkgo": 60, "builtin:street_tree_zelkova": 125, "builtin:street_tree_plane": 115,
                        "builtin:street_tree_cherry": 120, "builtin:street_tree_pine": 85}
SPECIES = {asset.rsplit("_", 1)[1]: asset for asset in STREET_TREE_CROWN_CM}
# One species per street name (weights of Korean street-tree surveys); pines
# need a wide sidewalk, the narrow ginkgo is the fallback beside close buildings.
SPECIES_WEIGHTS = (("ginkgo", 30), ("zelkova", 22), ("cherry", 20), ("plane", 18), ("pine", 10))
PLANTER, MEDIAN_BED, MEDIAN_PINE = "builtin:planter", "builtin:median_bed", "builtin:median_bed_pine"
PLANTING = (*STREET_TREE_CROWN_CM, PLANTER, "builtin:planter_square", MEDIAN_BED, MEDIAN_PINE)
SIZES |= {asset: (STREET_TREE_PIT_CM // 2, STREET_TREE_PIT_CM // 2) for asset in STREET_TREE_CROWN_CM} | {
    PLANTER: (40, 15), "builtin:planter_square": (30, 30), MEDIAN_BED: (150, 40), MEDIAN_PINE: (150, 40)}
STREET_TREE_CLASSES = ("trunk", "primary", "secondary", "tertiary")  # Or lanes ≥ 2 when the class is unknown.
STREET_TREE_SPACING_CM, STREET_TREE_CURB_CM, STREET_TREE_SIDEWALK_CM = 270, 28, 60
MOUTH_CLEAR_CM, CROSSWALK_CLEAR_CM, FREE_END_CM = 60, 250, 135  # Beyond the junction mouth block; free ends.
PINE_SIDEWALK_CM, FIT_SHARE = 100, 0.75
STREET_TREE_GRID_CM = 125  # Spacing lookup cells: the largest crown reach.
MEDIAN_PROBE_CM = 600  # An opposite one-way carriageway this far beyond the edge makes a median.
STOP_CLEAR_CM, POLE_CLEAR_CM, POST_CLEAR_CM = 300, 150, 150  # Shelter centres; beyond the crown from signal/guide poles; sign posts.
ANCHOR_REACH_CM, ANCHOR_SHARE = 300, 0.6  # OSM trees beyond the sidewalk snap; they suppress stations this share of the spacing.
CARRIAGEWAY_CM, STRUCTURE_CLEAR_CM, BARRIER_CLEAR_CM = 2, 50, 10
MEDIAN_BED_PITCH_CM, MEDIAN_BED_SETBACK_CM, MEDIAN_BED_CLEAR_CM, MEDIAN_FREE_END_CM = 330, 18, 15, 165
PLANTER_EVERY, PLANTER_CHANCE, PLANTER_FRONT_CM, PLANTER_WIDE_CM, PLANTER_INSET_CM = 4, 0.5, 300, 100, 5
STREET_TREE_LIMIT, MEDIAN_BED_LIMIT, PLANTER_LIMIT = 14_000, 1_500, 1_500  # MAX_PLACEMENTS still applies.
# City streetlights (map cm, ×D for source cm), mirrors of the MapKit v1
# contract (spec/CURRENT_V1.md): one solid 12 cm pole behind the sidewalk, a
# display-only arm with a fixed reach per id from the pole axis to the head
# centre over the road (twins ±reach), every display vertex inside the
# envelope (back 25 beyond the pole axis, tip 20 beyond the head, side 8).
STREETLIGHT_REACH_CM = {"builtin:city_streetlight_75": 75, "builtin:city_streetlight_135": 135,
                        "builtin:city_streetlight_195": 195, "builtin:city_streetlight_255": 255,
                        "builtin:city_streetlight_315": 315, "builtin:city_streetlight_375": 375}
TWIN_REACH_CM = {"builtin:city_streetlight_twin_75": 75, "builtin:city_streetlight_twin_135": 135}
LAMPS = (*STREETLIGHT_REACH_CM, *TWIN_REACH_CM)
LAMP_MAX_REACH_CM = max(STREETLIGHT_REACH_CM.values())
LAMP_POLE_CM, LAMP_HEIGHT_CM, LAMP_HEAD_CM = 12, 330, 310
LAMP_BACK_CM, LAMP_TIP_CM, LAMP_SIDE_CM, LAMP_TOP_CM = 25, 20, 8, 345
SIZES |= {asset: (LAMP_POLE_CM // 2, LAMP_POLE_CM // 2) for asset in LAMPS}
# Lit roads: arterials and collectors (no motorways, residential streets or
# alleys); without an OSM class, roads with junction stop lines.
LAMP_CLASSES = ("trunk", "primary", "secondary", "tertiary", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
# Arrangements: two-way 6+ lanes opposite pairs, two-way 4-5 lanes and one-way
# 3+ lanes staggered on both sides, other roads and links one side.
LAMP_SPACING_CM = {"opposite": 1000, "staggered": 1000, "one_side": 1170}
LAMP_OVERHANG_CM = 25  # Least head-centre reach over the carriageway edge (reach steps of 60 keep it under 85).
LAMP_POLE_OFFSET_CM = CLEARANCE_CM + LAMP_POLE_CM // 2 + 2  # Pole axis beyond the sidewalk.
LAMP_NUDGE_CM, LAMP_NUDGE_STEPS = 27, 5  # Up to half a street-tree spacing either way; gaps between crowns are tried exactly.
LAMP_FREE_END_CM, LAMP_COVER_SHARE = 135, 0.6
LAMP_GAP_CM = 4  # Pole to placed pieces: a twin fits the 30 cm gaps between median beds.
LAMP_SIGNAL_CLEAR_CM, LAMP_STOP_CLEAR_CM, LAMP_POST_CLEAR_CM, LAMP_LAMP_CLEAR_CM = 300, 100, 50, 150
LAMP_DECK_CLEAR_CM = 100  # The envelope beyond bridge and elevated corridors (+20 cm walls).
# Painted pedestrian ribbons (drivable ground paint, osm_generalize.paint):
# non-grass surface areas whose mean width 2·area/perimeter is under this
# keep solid poles off them.
LAMP_RIBBON_CM, LAMP_SOFT_SURFACES = 120, ("grass",)
# Spacing widens in steps (at most LAMP_SPACING_MAX times) until the rows fit
# STREETLIGHT_LIMIT and what MAX_PLACEMENTS leaves; beyond that, `_limit` skips.
STREETLIGHT_LIMIT, LAMP_SPACING_STEP, LAMP_SPACING_MAX = 8_000, 0.05, 4.0
TALL = ("builtin:signal_h", "builtin:signal_v", GUIDE, "builtin:bus_shelter", "builtin:subway_entrance", "builtin:station_sign")
STOPS = ("builtin:bus_shelter", "builtin:subway_entrance", "builtin:station_sign")


def _unit(seed, *parts):
    """Stable value in [0, 1) from text parts."""
    digest = hashlib.sha256("\x1f".join([seed, *map(str, parts)]).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def _pose(theta_deg):
    """(quarter_turns, yaw_offset_mdeg) of a counter-clockwise map-plane angle;
    the offset stays within ±45°, so perpendicular poses alternate parity."""
    turns = round(theta_deg / 90.0)
    return turns % 4, round((theta_deg - turns * 90.0) * 1000)


class Furniture:
    def __init__(self, patches, coordinates, scale, traffic):
        self.scale = scale
        self.left_hand = traffic.get("driving_side") == "left"
        self.signal = "builtin:signal_v" if traffic.get("signal_style") == "vertical" else "builtin:signal_h"
        self.counts = Counter()
        self.items = []
        walking = set(coordinates.get("osm_pedestrian_roads", []))
        # Adoption widens other segments narrower than the floor towards it
        # (import_units.gd widen_roads, up to the nearest building): keep clear
        # of the floor width.
        floor = ROAD_FLOOR_CM * scale
        roads = [dict(r, widths_cm=[max(w, floor) for w in r["widths_cm"]]) if r["id"] not in walking and min(r["widths_cm"], default=floor) < floor else r
                 for r in (p["after"] for p in patches if p["field"] == "roads")]
        self.roads = roads
        self.vehicle = [r for r in roads if r["id"] not in walking]
        self.nodes = {p["id"]: p["after"] for p in patches if p["field"] == "nodes"}
        blocks = []
        margin = CLEARANCE_CM * scale
        for r in roads:
            points = [(q[0], q[2]) for q in r["points"]]
            sidewalk = r.get("sidewalk_cm") or 0
            # MapKit's corridor keeps the outer corner of a bend (a mitre, not a
            # round join): buffer the whole line at its widest with mitred joins.
            if len(set(points)) >= 2:
                blocks.append(LineString(points).buffer(max(r["widths_cm"]) / 2 + sidewalk + margin, quad_segs=2, join_style="mitre", mitre_limit=10.0))
        # MapKit's joint faces between two segments (street planting and lamps).
        self.joints = self._joints(roads)
        self.buildings, self.water, self.barriers = [], [], []
        for p in patches:
            if p["field"] == "buildings":
                rings = [p["after"]["footprint"]] + [part["footprint"] for part in p["after"].get("parts", [])]
                solids = [Polygon(ring) for ring in rings if len(ring) >= 3]
                blocks.extend(solid.buffer(GAP_CM * scale) for solid in solids)
                self.buildings += solids + [Polygon(ring) for ring in p["after"].get("entrances", []) if len(ring) >= 3]
            elif p["field"] == "water_bodies":
                blocks.append(Polygon(p["after"]["polygon"]))
                self.water.append(blocks[-1])
            elif p["field"] == "barriers" and len(p["after"].get("line", [])) >= 2:
                self.barriers.append(LineString([q[:2] for q in p["after"]["line"]]).buffer(p["after"].get("thickness_cm", 0) / 2 + BARRIER_CLEAR_CM * scale, quad_segs=2))
        # Junction mouths reach about √2 × the widest half width from the node.
        arms = Counter()
        half = Counter()
        for r in self.vehicle:
            for end in ("from", "to"):
                arms[r[end]] += 1
                half[r[end]] = max(half[r[end]], max(r["widths_cm"]) / 2 + (r.get("sidewalk_cm") or 0))
        self.mouths = []
        for node, count in arms.items():
            if count >= 3 and node in self.nodes:
                at = self.nodes[node]["position"]
                blocks.append(Point(at[0], at[2]).buffer(math.sqrt(2) * half[node] + margin, quad_segs=4))
                self.mouths.append(blocks[-1])
        self.arms, self.half = arms, half
        self.blocks = blocks
        self.tree = STRtree(blocks)
        self.placed = {}  # Spatial hash (BUCKET_CM cells) of placed footprints.
        self.road_lines = [(r, LineString([(q[0], q[2]) for q in r["points"]])) for r in self.vehicle if len(r["points"]) >= 2]
        self.road_tree = STRtree([g for r, g in self.road_lines])
        self.lines = {r["id"]: line for r, line in self.road_lines}
        self.walking_ids = walking
        self.incident = {}
        for r in self.vehicle:
            for end in ("from", "to"):
                self.incident.setdefault(r[end], []).append((r, end))
        self.signalled = set()  # Junction nodes that qualify for signal poles.
        self.pois = [p["after"] for p in patches if p["field"] == "pois"]
        # Narrow painted walking ribbons (map scale: the polygon's mean width).
        self.ribbons = []
        for p in patches:
            if p["field"] != "surface_areas" or p["after"].get("surface") in LAMP_SOFT_SURFACES: continue
            ring = [q[:2] for q in p["after"].get("polygon", [])]
            if len(ring) < 3: continue
            area = Polygon(ring)
            if not area.is_valid: area = area.buffer(0)
            if not area.is_empty and area.length > 0 and 2 * area.area / area.length < LAMP_RIBBON_CM * scale: self.ribbons.append(area)

    def footprint(self, asset, x, y, theta):
        hx, hy = (v * self.scale for v in SIZES[asset])
        c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        return Polygon([(x + c * px - s * py, y + s * px + c * py) for px, py in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])

    def buckets(self, shape):
        x0, y0, x1, y1 = shape.bounds
        return [(i, j) for i in range(math.floor(x0 / BUCKET_CM), math.floor(x1 / BUCKET_CM) + 1)
                for j in range(math.floor(y0 / BUCKET_CM), math.floor(y1 / BUCKET_CM) + 1)]

    def free(self, shape, blocks=None, gap=GAP_CM):
        geoms, tree = blocks or (self.blocks, self.tree)
        if any(geoms[int(i)].intersects(shape) for i in tree.query(shape)): return False
        grown = shape.buffer(gap * self.scale)
        return not any(other.intersects(grown) for key in self.buckets(grown) for other in self.placed.get(key, ()))

    def place(self, kind, asset, x, y, theta, source, nudge=(0.0, 0.0), steps=4, accept=None, blocks=None, skipped=None, gap=GAP_CM):
        """Place at (x, y) or up to `steps` nudges along `nudge` (source cm per
        step); `accept(px, py)` may reject a spot as not free. `blocks` =
        (geometries, STRtree) replaces the corridor blocks; `skipped` names the
        skip count (default `skipped_<kind>`); `gap` (map cm) to placed pieces."""
        for step in range(steps + 1):
            px, py = x + nudge[0] * step, y + nudge[1] * step
            if accept is not None and not accept(px, py): continue
            shape = self.footprint(asset, px, py, theta)
            if not self.free(shape, blocks, gap): continue
            if len(self.items) >= MAX_PLACEMENTS:
                self.counts["over_limit"] += 1
                return False
            for key in self.buckets(shape): self.placed.setdefault(key, []).append(shape)
            turns, offset = _pose(theta)
            self.items.append(dict(asset_id=asset, position=[round(px), 0, round(py)], quarter_turns=turns, yaw_offset_mdeg=offset, source_id=source))
            self.counts[kind] += 1
            return True
        self.counts[skipped or "skipped_" + kind] += 1
        return False

    def nearest_road(self, x, y, reach):
        point = Point(x, y)
        best = None
        for i in self.road_tree.query(point.buffer(reach)):
            r, line = self.road_lines[int(i)]
            d = line.distance(point)
            if best is None or d < best[0]: best = (d, r, line)
        return best

    def signals(self, signal_points):
        """One pole per inbound arm at junctions of three or more vehicle roads
        where two roads with stop lines meet or an OSM signal node lies within 15 m."""
        tagged = STRtree([Point(p["position"]) for p in signal_points]) if signal_points else None
        for node, arms in sorted(self.incident.items()):
            if len(arms) < 3 or node not in self.nodes: continue
            at = self.nodes[node]["position"]
            centre = Point(at[0], at[2])
            arterial = sum(bool((r.get("markings") or {}).get("stop_lines")) for r, end in arms) >= 2
            signalled = tagged is not None and len(tagged.query(centre.buffer(1500)))  # An OSM signal within 15 source m.
            if not (arterial or signalled): continue
            self.signalled.add(node)
            reach = math.sqrt(2) * self.half[node] + (CLEARANCE_CM + SIZES[self.signal][1] + 2) * self.scale
            for r, end in arms:
                points = r["points"]
                near, far = (points[0], points[1]) if end == "from" else (points[-1], points[-2])
                ux, uy = far[0] - near[0], far[2] - near[2]
                length = math.hypot(ux, uy)
                if length == 0: continue
                ux, uy = ux / length, uy / length
                hx, hy = -ux, -uy  # Heading of traffic arriving on this arm.
                side = (-hy, hx) if self.left_hand else (hy, -hx)  # Driver's right (left in left-hand traffic).
                width = max(r["widths_cm"]) / 2 + (r.get("sidewalk_cm") or 0) + (CLEARANCE_CM + SIZES[self.signal][0] + 2) * self.scale
                x = at[0] + ux * reach + side[0] * width
                y = at[2] + uy * reach + side[1] * width
                toward = (-side[0], -side[1])  # Local +x reaches over the road.
                self.place("signals", self.signal, x, y, math.degrees(math.atan2(toward[1], toward[0])), node, (ux * 20 * self.scale, uy * 20 * self.scale))

    def stops(self, street):
        """Bus shelters, subway entrances and station signs beside the nearest road."""
        for p in street:
            kind = p["kind"]
            if kind in ("traffic_signals", "stop", "give_way", "tree"): continue
            asset = {"bus_stop": "builtin:bus_shelter", "subway_entrance": "builtin:subway_entrance", "station": "builtin:station_sign"}[kind]
            x, y = p["position"]
            near = self.nearest_road(x, y, 3000 * self.scale)
            if near is None:
                self.place(kind, asset, x, y, 0.0, p["source_id"])
                continue
            d, r, line = near
            foot = line.interpolate(line.project(Point(x, y)))
            nx, ny = x - foot.x, y - foot.y
            length = math.hypot(nx, ny)
            if length < 1:
                # On the centreline: the side of the travel direction's right.
                a, b = line.coords[0], line.coords[-1]
                nx, ny, length = b[1] - a[1], a[0] - b[0], math.hypot(b[0] - a[0], b[1] - a[1]) or 1
            nx, ny = nx / length, ny / length
            edge = max(r["widths_cm"]) / 2 + (r.get("sidewalk_cm") or 0) + (CLEARANCE_CM + SIZES[asset][1] + 2) * self.scale
            # The open front faces the road: local +y points to it.
            theta = math.degrees(math.atan2(nx, -ny))
            self.place(kind, asset, foot.x + nx * edge, foot.y + ny * edge, theta, p["source_id"], (nx * 30 * self.scale, ny * 30 * self.scale))

    def parks(self, regions):
        """Seeded trees, benches and shrubs on jittered grids inside park areas."""
        for region in sorted(regions, key=lambda r: r["source_id"]):
            if region.get("landuse") not in PARK_KINDS or len(region["polygon"]) < 3: continue
            area = Polygon(region["polygon"], [h for h in region.get("holes", []) if len(h) >= 3])
            if not area.is_valid or area.is_empty: continue
            x0, y0, x1, y1 = area.bounds
            for asset, grid in PARK_GRID_CM.items():
                step = grid * self.scale
                for i in range(math.floor(x0 / step), math.floor(x1 / step) + 1):
                    for j in range(math.floor(y0 / step), math.floor(y1 / step) + 1):
                        seed = region["source_id"]
                        if _unit(seed, asset, i, j, "keep") >= PARK_CHANCE[asset]: continue
                        x = (i + 0.15 + 0.7 * _unit(seed, asset, i, j, "x")) * step
                        y = (j + 0.15 + 0.7 * _unit(seed, asset, i, j, "y")) * step
                        if not area.contains(self.footprint(asset, x, y, 0.0)): continue
                        theta = 90.0 * math.floor(4 * _unit(seed, asset, i, j, "turn"))
                        self.place("park_" + asset.split(":")[1], asset, x, y, theta, seed, steps=0)

    # Road signs ---------------------------------------------------------------

    @staticmethod
    def _inbound(r, end):
        """Traffic may arrive at `end` of the road."""
        one_way = (r.get("markings") or {}).get("one_way", 0)
        return one_way == 0 or (one_way == 1 and end == "to") or (one_way == -1 and end == "from")

    @staticmethod
    def _painted(r):
        return bool(r.get("markings") and r["markings"].get("lanes"))

    @staticmethod
    def _arterial(r):
        m = r.get("markings") or {}
        lanes = m.get("lanes") or 0
        return bool(m.get("stop_lines")) and (lanes >= 4 or bool(m.get("one_way")) and lanes >= 2 or bool(m.get("edge_lines")))

    @staticmethod
    def _ground(r):
        return r.get("kind", "ground") == "ground"

    def _arm(self, r, end):
        """(u, length): unit vector from the node along the arm's first segment
        (junction geometry only; signs stand along the road, _approach)."""
        points = r["points"]
        near, far = (points[0], points[1]) if end == "from" else (points[-1], points[-2])
        ux, uy = far[0] - near[0], far[2] - near[2]
        length = math.hypot(ux, uy)
        return ((ux / length, uy / length) if length else None), self.length[r["id"]]

    def _approach(self, line, end, s):
        """(x, y, heading, away) of the centreline point `s` along `line` from
        its `end` node, for traffic arriving at that node (`away`: unit along
        the road from the node, the nudge); None past the road's length."""
        if s > line.length: return None
        t, direction = (s, -1) if end == "from" else (line.length - s, 1)
        h = self._tangent(line, t, direction)
        if h is None: return None
        at = line.interpolate(t)
        return at.x, at.y, h, (-h[0], -h[1])

    def _school_road(self, r):
        info = self.road_info.get(r["id"])
        return not (info and info.get("highway") in SCHOOL_EXCLUDED)

    def _mouth(self, node, asset):
        return math.sqrt(2) * self.half[node] + (CLEARANCE_CM + SIZES[asset][1] + 2) * self.scale

    def _snap(self, speed):
        below = [v for v in SPEEDS if speed is not None and v <= speed]
        return below[-1] if below else None

    def _speed(self, r, x, y):
        """Posted speed for a sign at (x, y) on road `r`, or None."""
        if self.schools is not None and self._school_road(r) and self.schools.contains(Point(x, y)): return 30
        info = self.road_info.get(r["id"])
        if info is not None:
            if info.get("maxspeed") is not None: return self._snap(info["maxspeed"])
            return CLASS_SPEED.get(info.get("highway"))
        m = r.get("markings") or {}
        if m.get("edge_lines") and (m.get("lanes") or 0) >= 6: return 60
        return 50 if m.get("stop_lines") else None

    def _dup(self, key, x, y, h, radius):
        """A sign of the same key within `radius` facing the same way."""
        i, j = math.floor(x / radius), math.floor(y / radius)
        for a in range(i - 1, i + 2):
            for b in range(j - 1, j + 2):
                for px, py, hx, hy in self.sign_grid.get((key, radius, a, b), ()):
                    if math.hypot(px - x, py - y) < radius and hx * h[0] + hy * h[1] >= HEADING_COS: return True
        return False

    def _near_signal(self, x, y):
        return self.signal_tree is not None and len(self.signal_tree.query(Point(x, y).buffer(SIGNAL_CLEAR_CM * self.scale))) > 0

    def sign_at(self, kind, asset, r, x, y, h, nudge, dedupe=None, steps=6, clear=False):
        """Place `asset` beside road `r` at centreline point (x, y) for traffic
        heading `h`, its plate (local map +y) facing that traffic; nudges move
        `nudge` (unit) by 20 map cm. `dedupe` = (key, radius) records the sign;
        `clear` keeps the pole itself SIGNAL_CLEAR_CM from signal poles."""
        if self.counts[kind] >= SIGN_CAPS[kind]:
            self.counts[f"skipped_{kind}_limit"] += 1
            return False
        if self.road_signs_placed >= ROAD_SIGN_LIMIT:
            self.counts["skipped_road_signs_limit"] += 1
            return False
        hx, hy = h
        side = (-hy, hx) if self.left_hand else (hy, -hx)
        offset = max(r["widths_cm"]) / 2 + (r.get("sidewalk_cm") or 0) + (CLEARANCE_CM + SIZES[asset][0] + 2) * self.scale
        theta = math.degrees(math.atan2(hx, -hy))  # Local +y = -h.
        step = 20 * self.scale
        accept = (lambda px, py: not self._near_signal(px, py)) if clear else None
        if not self.place(kind, asset, x + side[0] * offset, y + side[1] * offset, theta, r["id"], (nudge[0] * step, nudge[1] * step), steps, accept):
            return False
        self.road_signs_placed += 1
        if dedupe is not None:
            key, radius = dedupe
            self.sign_grid.setdefault((key, radius, math.floor(x / radius), math.floor(y / radius)), []).append((x, y, hx, hy))
        return True

    def _order(self, *parts):
        return _unit("road-signs", *parts)

    def road_signs(self, street, regions, road_info=None, school_areas=None):
        """Traffic signs beside vehicle ground roads, after the street furniture
        and before the street planting.

        In order: OSM stop/give-way nodes; overhead guide signs on wide
        arterial approaches of signalled junctions (right-hand traffic only:
        the arm reaches along local +x); crossing signs before painted
        crosswalks of unsignalled junctions; stop or yield signs on the minor
        arms of unsignalled painted junctions; children-protection signs (and
        a 30 sign) where roads enter a school zone; speed-limit signs after
        junctions and every 250 map m per direction. Each rule has a cap, all
        signs share ROAD_SIGN_LIMIT, and lists run in a fixed seeded order."""
        self.road_info = road_info or {}
        self.road_signs_placed = 0
        self.sign_grid = {}
        self.length = {r["id"]: line.length for r, line in self.road_lines}
        lines = {r["id"]: line for r, line in self.road_lines}
        signal_points = [Point(item["position"][0], item["position"][2]) for item in self.items if item["asset_id"] == self.signal]
        self.signal_tree = STRtree(signal_points) if signal_points else None
        zones = [Polygon(ring).buffer(SCHOOL_ZONE_CM * self.scale) for ring in (school_areas or []) if len(ring) >= 3]
        zones += [Polygon(region["polygon"]).buffer(SCHOOL_ZONE_CM * self.scale) for region in regions if len(region.get("polygon", [])) >= 3
                  and (region.get("tags", {}).get("amenity") in ("school", "kindergarten") or region.get("landuse") == "school")]
        zones += [Point(*poi["position"]).buffer(SCHOOL_POI_CM * self.scale, quad_segs=8) for poi in self.pois if poi.get("category") == "school"]
        zones = [z for z in zones if z.is_valid and not z.is_empty]
        self.schools = unary_union(zones) if zones else None
        if self.schools is not None:
            from shapely import prepare
            prepare(self.schools)
        used = set()
        step = 20 * self.scale

        # 1. OSM stop and give-way nodes on the nearest vehicle ground road.
        tagged = [p for p in street if p["kind"] in ("stop", "give_way")]
        for p in sorted(tagged, key=lambda p: (self._order(p["source_id"]), p["source_id"])):
            x, y = p["position"]
            point = Point(x, y)
            best = None
            for i in self.road_tree.query(point.buffer(TAGGED_REACH_CM * self.scale)):
                r, line = self.road_lines[int(i)]
                if not self._ground(r): continue
                d = line.distance(point)
                if d <= TAGGED_REACH_CM * self.scale and (best is None or (d, r["id"]) < (best[0], best[1]["id"])): best = (d, r, line)
            if best is None:
                self.counts["skipped_tagged_signs"] += 1
                continue
            d, r, line = best
            t = line.project(point)
            ends = [(abs(t - (0 if end == "from" else line.length)), end) for end in ("from", "to")
                    if len(self.incident.get(r[end], ())) >= 3 and r[end] in self.nodes and self._inbound(r, end)]
            if not ends:
                self.counts["skipped_tagged_signs"] += 1
                continue
            along, end = min(ends)
            node = r[end]
            asset, kind = ("builtin:sign_stop", "stop_signs") if p["kind"] == "stop" else ("builtin:sign_yield", "yield_signs")
            spot = self._approach(line, end, max(self._mouth(node, asset), along))
            if along > 2 * TAGGED_REACH_CM * self.scale or spot is None:
                self.counts["skipped_tagged_signs"] += 1
                continue
            used.add((node, r["id"]))
            x, y, h, away = spot
            self.sign_at(kind, asset, r, x, y, h, away)

        # 2. Overhead guide signs on arterial approaches of signalled junctions.
        if not self.left_hand:
            approaches = []
            for node in self.signalled:
                arms = self.incident[node]
                if sum(self._arterial(r) for r, end in arms) < 2: continue
                for r, end in arms:
                    if not (self._arterial(r) and self._ground(r) and self._inbound(r, end)): continue
                    u, length = self._arm(r, end)
                    if u is None or length < GUIDE_MIN_ROAD_CM * self.scale: continue
                    sidewalk = r.get("sidewalk_cm") or 0
                    if sidewalk > GUIDE_MAX_SIDEWALK_CM * self.scale: continue
                    one_way = (r.get("markings") or {}).get("one_way", 0)
                    span = (max(r["widths_cm"]) if one_way else max(r["widths_cm"]) / 2) + sidewalk + (CLEARANCE_CM + SIZES[GUIDE][0] + 2) * self.scale
                    if span < GUIDE_REACH_CM * self.scale: continue
                    approaches.append((self._order(node, r["id"]), node, r["id"], r, end))
            for _, node, _, r, end in sorted(approaches, key=lambda a: a[:3]):
                spot = self._approach(lines[r["id"]], end, GUIDE_SETBACK_CM * self.scale)
                if spot is None: continue
                x, y, h, away = spot
                if self._dup("guide", x, y, h, GUIDE_DEDUPE_CM * self.scale): continue
                self.sign_at("guide_signs", GUIDE, r, x, y, h, away, ("guide", GUIDE_DEDUPE_CM * self.scale), clear=True)

        # 3. Crossing signs before painted crosswalks of unsignalled junctions.
        crossings = []
        for r, line in self.road_lines:
            if not (self._painted(r) and self._ground(r)): continue
            for end, key in (("from", "crosswalk_start"), ("to", "crosswalk_end")):
                node = r[end]
                if not r["markings"].get(key) or node in self.signalled or node not in self.nodes or not self._inbound(r, end): continue
                crossings.append((self._order(node, r["id"], end), node, r["id"], end, r))
        for _, node, _, end, r in sorted(crossings, key=lambda c: c[:4]):
            u, length = self._arm(r, end)
            if u is None: continue
            reach = self._mouth(node, "builtin:sign_crossing") + CROSSING_SETBACK_CM * self.scale
            spot = None if reach >= length else self._approach(lines[r["id"]], end, reach)
            if spot is None: continue
            x, y, h, away = spot
            self.sign_at("crossing_signs", "builtin:sign_crossing", r, x, y, h, away)

        # 4. Stop or yield on the minor arms of unsignalled painted junctions.
        junctions = []
        for node, arms in self.incident.items():
            if node in self.signalled or node not in self.nodes: continue
            painted = [(r, end) for r, end in arms if self._painted(r) and self._ground(r)]
            if len(painted) < 3: continue
            junctions.append((self._order(node), node, painted))
        for _, node, painted in sorted(junctions, key=lambda j: j[:2]):
            dirs = [self._arm(r, end)[0] for r, end in painted]
            if any(u is None for u in dirs): continue
            best = None
            for i in range(len(painted)):
                for j in range(i + 1, len(painted)):
                    dot = dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1]
                    if dot >= -HEADING_COS: continue
                    a, b = painted[i][0], painted[j][0]
                    rank = (bool(a["markings"].get("stop_lines") or b["markings"].get("stop_lines")),
                            min(max(a["widths_cm"]), max(b["widths_cm"])), -dot, -i, -j)
                    if best is None or rank > best[0]: best = (rank, i, j)
            if best is None: continue  # A Y junction has no through road.
            _, i, j = best
            through = dirs[i]
            for k, (r, end) in enumerate(painted):
                if k in (i, j) or (node, r["id"]) in used or not self._inbound(r, end): continue
                u, length = self._arm(r, end)
                if length < MINOR_MIN_ROAD_CM * self.scale: continue
                one_way = bool(r["markings"].get("one_way"))
                oblique = abs(u[0] * through[0] + u[1] * through[1]) > OBLIQUE_COS
                asset, kind = ("builtin:sign_yield", "yield_signs") if oblique or one_way else ("builtin:sign_stop", "stop_signs")
                spot = self._approach(lines[r["id"]], end, self._mouth(node, asset) + MINOR_SETBACK_CM * self.scale)
                if spot is None: continue
                x, y, h, away = spot
                self.sign_at(kind, asset, r, x, y, h, away)

        # 5. Children protection where painted roads enter a school zone.
        if self.schools is not None:
            boundary = self.schools.boundary
            entries = []
            for r, line in self.road_lines:
                if not (self._painted(r) and self._ground(r) and self._school_road(r)) or not line.intersects(boundary): continue
                cut = line.intersection(boundary)
                points = [g for g in getattr(cut, "geoms", [cut]) if g.geom_type == "Point"]
                one_way = r["markings"].get("one_way", 0)
                for p in points:
                    t = line.project(p)
                    for direction in ((1, -1) if one_way == 0 else (one_way,)):
                        ahead, behind = line.interpolate(t + direction * step), line.interpolate(t - direction * step)
                        if not (self.schools.contains(ahead) and not self.schools.contains(behind)): continue
                        entries.append((self._order(r["id"], round(t), direction), r["id"], round(t), direction, r, line, t))
            for _, _, _, direction, r, line, t in sorted(entries, key=lambda e: e[:4]):
                h = self._tangent(line, t, direction)
                if h is None: continue
                out = line.interpolate(t - direction * step)
                if self._dup("children", out.x, out.y, h, CHILDREN_DEDUPE_CM * self.scale): continue
                if not self.sign_at("children_signs", "builtin:sign_children", r, out.x, out.y, h, (-h[0], -h[1]),
                                    ("children", CHILDREN_DEDUPE_CM * self.scale), clear=True):
                    continue
                inside = t + direction * SCHOOL_SPEED_CM * self.scale
                if not (r["markings"].get("stop_lines") and 0 < inside < line.length): continue
                info = self.road_info.get(r["id"])
                normal = self._snap(info["maxspeed"]) if info and info.get("maxspeed") is not None else CLASS_SPEED.get(info.get("highway")) if info else 50
                if not normal or normal <= 30: continue
                at = line.interpolate(inside)
                radius = SPEED_DEDUPE_CM * self.scale
                if self._dup("speed_30", at.x, at.y, h, radius): continue
                self.sign_at("speed_signs", "builtin:sign_speed_30", r, at.x, at.y, h, h, ("speed_30", radius), clear=True)

        # 6. Speed-limit signs after junctions and every 250 map m.
        roads = []
        for r, line in self.road_lines:
            if not (self._ground(r) and (r.get("markings") or {}).get("stop_lines")) or line.length < SPEED_MIN_ROAD_CM * self.scale: continue
            roads.append((not self._arterial(r), self._order(r["id"]), r["id"], r, line))
        radius = SPEED_DEDUPE_CM * self.scale
        for _, _, _, r, line in sorted(roads, key=lambda e: e[:3]):
            one_way = r["markings"].get("one_way", 0)
            for direction in ((1, -1) if one_way == 0 else (one_way,)):
                s = SPEED_EXIT_CM * self.scale
                while s <= line.length - SPEED_EXIT_CM * self.scale:
                    t = s if direction == 1 else line.length - s
                    s += SPEED_REPEAT_CM * self.scale
                    at = line.interpolate(t)
                    h = self._tangent(line, t, direction)
                    speed = self._speed(r, at.x, at.y)
                    if h is None or speed is None: continue
                    key = f"speed_{speed}"
                    if self._dup(key, at.x, at.y, h, radius): continue
                    self.sign_at("speed_signs", f"builtin:sign_speed_{speed}", r, at.x, at.y, h, h, (key, radius), clear=True)

    # Street planting -----------------------------------------------------------

    @staticmethod
    def _index(geoms):
        geoms = [g for g in geoms if not g.is_empty]
        return geoms, STRtree(geoms)

    @staticmethod
    def _hits(blocks, shape):
        geoms, tree = blocks
        return any(geoms[int(i)].intersects(shape) for i in tree.query(shape))

    @staticmethod
    def _band(r, extra, quad_segs=2):
        """The record's carriageway grown by `extra` beyond each segment's own
        half width (MapKit sidewalks follow per-segment widths): one mitred
        buffer when the widths agree, else a union of mitred runs of equal width
        (round ends of `quad_segs` segments per quarter where the width changes)."""
        points, widths = [(q[0], q[2]) for q in r["points"]], r["widths_cm"]
        if len(set(widths)) == 1:
            return LineString(points).buffer(widths[0] / 2 + extra, quad_segs=quad_segs, join_style="mitre", mitre_limit=10.0)
        runs, start = [], 0
        for i in range(1, len(widths) + 1):
            if i == len(widths) or widths[i] != widths[start]:
                run = points[start:i + 1]
                if len(set(run)) >= 2: runs.append(LineString(run).buffer(widths[start] / 2 + extra, quad_segs=quad_segs, join_style="mitre", mitre_limit=10.0))
                start = i
        return unary_union(runs)

    @staticmethod
    def _half_at(r, t):
        """Half carriageway width of the record segment at arc length t."""
        widths, points = r["widths_cm"], r["points"]
        if len(set(widths)) == 1: return widths[0] / 2
        along = 0.0
        for i, width in enumerate(widths):
            along += math.hypot(points[i + 1][0] - points[i][0], points[i + 1][2] - points[i][2])
            if t <= along: return width / 2
        return widths[-1] / 2

    def _planting(self):
        """Blocking geometry of street planting, built once: exact carriageways
        (no sidewalk, per-segment widths) of every road, across two-arm joins and
        over MapKit's joint faces, sidewalk corridors, structure corridors,
        buildings, water, barriers and junction mouths; placed street trees for
        their spacing."""
        if hasattr(self, "carriageways"): return
        s = self.scale
        carriage, corridors, structures, self.carriage_roads = [], [], [], []
        self.tree_grid = {}
        for r in self.roads:
            points = [(q[0], q[2]) for q in r["points"]]
            if len(set(points)) < 2: continue
            line, half = LineString(points), max(r["widths_cm"]) / 2
            carriage.append(self._band(r, CARRIAGEWAY_CM * s))
            self.carriage_roads.append(r)
            corridors.append((r["id"], self._band(r, r.get("sidewalk_cm") or 0)))
            if not self._ground(r): structures.append(line.buffer(half + STRUCTURE_CLEAR_CM * s, quad_segs=2))
        ends = {}
        for r in self.roads:
            if len(r["points"]) < 2: continue
            for end in ("from", "to"): ends.setdefault(r[end], []).append((r, end))
        for node, arms in sorted(ends.items()):
            if len(arms) != 2: continue
            (a, ea), (b, eb) = arms
            before = a["points"][-2] if ea == "to" else a["points"][1]
            at = a["points"][-1] if ea == "to" else a["points"][0]
            after = b["points"][1] if eb == "from" else b["points"][-2]
            corner = [(before[0], before[2]), (at[0], at[2]), (after[0], after[2])]
            if len(set(corner)) == 3:
                half = max(a["widths_cm"][-1 if ea == "to" else 0], b["widths_cm"][0 if eb == "from" else -1]) / 2
                carriage.append(LineString(corner).buffer(half + CARRIAGEWAY_CM * s, quad_segs=2, join_style="mitre", mitre_limit=10.0))
                self.carriage_roads.append(None)
        for face, _ in self.joints:
            carriage.append(face.buffer(CARRIAGEWAY_CM * s, quad_segs=2, join_style="mitre", mitre_limit=10.0))
            self.carriage_roads.append(None)
        self.carriageways = (carriage, STRtree(carriage))
        self.corridor_ids = [i for i, _ in corridors]
        self.corridors = self._index([g for _, g in corridors])
        self.structures = self._index(structures)
        near = [g.buffer(GAP_CM * s) for g in self.buildings]
        # Pits and beds: carriageways, buildings + GAP, water, barriers and mouths.
        self.pit_blocks = self._index(carriage + near + self.water + self.barriers + self.mouths)
        self.bed_blocks = self._index(near + self.water + self.barriers + self.mouths + structures)
        self.planter_blocks = self._index(carriage + near + self.water + self.barriers + self.mouths)
        self.solid = self._index(list(self.buildings))
        tall, stops, poles, posts = [], [], [], []
        for item in self.items:
            asset, (x, _, y) = item["asset_id"], item["position"]
            theta = item["quarter_turns"] * 90 + item["yaw_offset_mdeg"] / 1000
            if asset in TALL: tall.append(self.footprint(asset, x, y, theta))
            if asset in STOPS: stops.append(Point(x, y))
            elif asset in TALL: poles.append(Point(x, y))
            elif asset in SIGN_POLE: posts.append(Point(x, y))
        self.crown_blocks = self._index(list(self.buildings) + structures + tall)
        self.stops_at, self.poles_at, self.posts_at = (self._index(points) if points else None for points in (stops, poles, posts))

    def _near(self, points, x, y, reach):
        return points is not None and self._hits(points, Point(x, y).buffer(reach, quad_segs=4))

    def _crown_fits(self, asset, x, y):
        return not self._hits(self.crown_blocks, Point(x, y).buffer(STREET_TREE_CROWN_CM[asset] * self.scale, quad_segs=8))

    def _crowded(self, asset, x, y):
        """An earlier street tree (or median pine) whose trunk stands under this
        crown, or under whose crown this trunk would stand: closer than the
        larger crown reach."""
        cell = STREET_TREE_GRID_CM * self.scale
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        reach = STREET_TREE_CROWN_CM[asset] * self.scale
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for ox, oy, other in self.tree_grid.get((gx, gy), ()):
                    if math.hypot(x - ox, y - oy) < max(reach, other): return True
        return False

    def _planted(self, asset, x, y):
        cell = STREET_TREE_GRID_CM * self.scale
        self.tree_grid.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append((x, y, STREET_TREE_CROWN_CM[asset] * self.scale))

    def _clearances(self, r, free_end):
        """Arc length kept clear at the `from` and `to` ends: junction mouth +
        MOUTH_CLEAR_CM (+ CROSSWALK_CLEAR_CM before a painted crosswalk), else
        `free_end` (so stations continue across two-arm joins)."""
        out = []
        for end, key in (("from", "crosswalk_start"), ("to", "crosswalk_end")):
            node = r[end]
            if len(self.incident.get(node, ())) >= 3 and node in self.nodes:
                clear = math.sqrt(2) * self.half[node] + (CLEARANCE_CM + MOUTH_CLEAR_CM) * self.scale
                if (r.get("markings") or {}).get(key): clear += CROSSWALK_CLEAR_CM * self.scale
            else:
                clear = free_end * self.scale
            out.append(clear)
        return out

    def _avenue(self, r, line):
        """A vehicle ground road with a sidewalk of at least 60 map cm whose OSM
        class is trunk to tertiary (painted lanes ≥ 2 when the class is unknown)."""
        if not self._ground(r) or (r.get("sidewalk_cm") or 0) < STREET_TREE_SIDEWALK_CM * self.scale: return False
        if line.length < 2 * STREET_TREE_SPACING_CM * self.scale: return False
        highway = (self.road_info.get(r["id"]) or {}).get("highway")
        if highway: return highway in STREET_TREE_CLASSES
        return ((r.get("markings") or {}).get("lanes") or 0) >= 2

    def _species(self, r):
        """One species per street (OSM name, else the road record)."""
        key = (self.road_info.get(r["id"]) or {}).get("name") or r["id"]
        pick, total = _unit("street-trees", key) * sum(w for _, w in SPECIES_WEIGHTS), 0
        for name, weight in SPECIES_WEIGHTS:
            total += weight
            if pick < total: break
        if name == "pine" and (r.get("sidewalk_cm") or 0) < PINE_SIDEWALK_CM * self.scale: name = "ginkgo"
        return SPECIES[name]

    def _opposite(self, r, line, at, normal, tangent):
        """An opposite one-way vehicle carriageway within MEDIAN_PROBE_CM beyond
        this side's edge of a one-way road (`tangent` along its points)."""
        direction = (r.get("markings") or {}).get("one_way", 0)
        if not direction: return False
        heading = (tangent[0] * direction, tangent[1] * direction)
        half = self._half_at(r, line.project(at))
        a = (at.x + normal[0] * (half + 2 * CARRIAGEWAY_CM * self.scale), at.y + normal[1] * (half + 2 * CARRIAGEWAY_CM * self.scale))
        b = (at.x + normal[0] * (half + MEDIAN_PROBE_CM * self.scale), at.y + normal[1] * (half + MEDIAN_PROBE_CM * self.scale))
        probe = LineString([a, b])
        geoms, tree = self.carriageways
        for i in tree.query(probe):
            other = self.carriage_roads[int(i)]
            if other is None or other is r or other["id"] in self.walking_ids or not self._ground(other): continue
            one_way = (other.get("markings") or {}).get("one_way", 0)
            if not one_way or not geoms[int(i)].intersects(probe): continue
            o = self.lines.get(other["id"])
            if o is None: continue
            h = self._tangent(o, o.project(at), one_way)
            if h is not None and h[0] * heading[0] + h[1] * heading[1] <= -HEADING_COS: return True
        return False

    def _sides(self, r, line, t, direction=1):
        """(centre, heading, [(side, normal)]) at arc length t: left then right
        of the heading (travel heading for `direction` ±1)."""
        h = self._tangent(line, t, direction)
        if h is None: return None
        return line.interpolate(t), h, (("left", (-h[1], h[0])), ("right", (h[1], -h[0])))

    def _tree_at(self, kind, asset, r, line, x, y, theta, heading, normal, at):
        """Place one street tree after the skip rules; True when placed."""
        s = self.scale
        if self._opposite(r, line, at, normal, heading):
            self.counts["skipped_street_trees_median"] += 1
        elif self._near(self.stops_at, x, y, STOP_CLEAR_CM * s):
            self.counts["skipped_street_trees_stop"] += 1
        elif self._near(self.posts_at, x, y, POST_CLEAR_CM * s):
            self.counts["skipped_street_trees_post"] += 1
        elif self._near(self.poles_at, x, y, (STREET_TREE_CROWN_CM[asset] + POLE_CLEAR_CM) * s):
            self.counts["skipped_street_trees_pole"] += 1
        elif not self._crown_fits(asset, x, y) or self._crowded(asset, x, y):
            self.counts["skipped_street_trees_crown"] += 1
        elif self.counts["street_trees"] + self.counts["street_trees_osm"] >= STREET_TREE_LIMIT:
            self.counts["skipped_street_trees_limit"] += 1
        elif self.place(kind, asset, x, y, theta, r["id"], steps=0, blocks=self.pit_blocks, skipped="skipped_street_trees_blocked"):
            self._planted(asset, x, y)
            return True
        return False

    def street_trees(self, street):
        """Street trees in turned 40 cm pits 28 map cm beyond the carriageway edge
        (of the segment at the station) of sidewalk avenues, every 270 map cm on
        both sides (facing pairs), clear of junction mouths, crosswalks, the
        median side of one-way pairs, stops, signal and guide poles, sign posts,
        crown misfits and earlier trees closer than the larger crown reach. OSM trees near an
        avenue anchor a pit first (their species hint kept) and suppress the
        nearest stations; elsewhere a street takes one species, or ginkgo when
        fewer than 75% of a record's pits fit the preferred crown."""
        self._planting()
        s = self.scale
        spacing = STREET_TREE_SPACING_CM * s
        avenues = sorted(((_unit("street-trees", r["id"]), r["id"], r, line) for r, line in self.road_lines if self._avenue(r, line)), key=lambda a: a[:2])
        lines = [line for _, _, _, line in avenues]
        anchors_at = []
        # 1. OSM trees snap to the nearest avenue side's pit line.
        if avenues:
            tree = STRtree(lines)
            reach = max(max(r["widths_cm"]) / 2 + r["sidewalk_cm"] for _, _, r, _ in avenues) + ANCHOR_REACH_CM * s
            for p in sorted((p for p in street if p["kind"] == "tree"), key=lambda p: (_unit("street-trees", p["source_id"]), p["source_id"])):
                point = Point(*p["position"])
                best = None
                for i in tree.query(point.buffer(reach, quad_segs=4)):
                    _, rid, r, line = avenues[int(i)]
                    d = line.distance(point)
                    if d <= max(r["widths_cm"]) / 2 + r["sidewalk_cm"] + ANCHOR_REACH_CM * s and (best is None or (d, rid) < best[:2]): best = (d, rid, r, line)
                if best is None:
                    self.counts["skipped_street_trees_osm_reach"] += 1
                    continue
                _, _, r, line = best
                t = line.project(point)
                start, end = self._clearances(r, FREE_END_CM)
                sides = self._sides(r, line, t)
                if not (start <= t <= line.length - end) or sides is None:
                    self.counts["skipped_street_trees_osm_reach"] += 1
                    continue
                at, h, pair = sides
                side = pair[0] if h[0] * (point.y - at.y) - h[1] * (point.x - at.x) >= 0 else pair[1]
                n = side[1]
                offset = self._half_at(r, t) + STREET_TREE_CURB_CM * s
                x, y = at.x + n[0] * offset, at.y + n[1] * offset
                asset = SPECIES.get(p.get("category"), self._species(r))
                if self._tree_at("street_trees_osm", asset, r, line, x, y, math.degrees(math.atan2(h[1], h[0])), h, n, at): anchors_at.append(Point(x, y))
        anchored = self._index(anchors_at) if anchors_at else None
        # 2. Stations of every avenue, one species per street.
        for _, _, r, line in avenues:
            start, end = self._clearances(r, FREE_END_CM)
            pits = []
            t = start
            while t <= line.length - end:
                sides = self._sides(r, line, t)
                offset = self._half_at(r, t) + STREET_TREE_CURB_CM * s
                t += spacing
                if sides is None: continue
                at, h, pair = sides
                for _, n in pair:
                    x, y = at.x + n[0] * offset, at.y + n[1] * offset
                    if self._near(anchored, x, y, ANCHOR_SHARE * spacing): continue
                    pits.append((x, y, math.degrees(math.atan2(h[1], h[0])), h, n, at))
            if not pits: continue
            asset = self._species(r)
            free = [pit for pit in pits if self.free(self.footprint(asset, pit[0], pit[1], pit[2]), self.pit_blocks)]
            if asset != SPECIES["ginkgo"] and free and sum(self._crown_fits(asset, x, y) for x, y, *_ in free) < FIT_SHARE * len(free):
                asset = SPECIES["ginkgo"]
            for x, y, theta, h, n, at in pits:
                self._tree_at("street_trees", asset, r, line, x, y, theta, h, n, at)

    def median_beds(self):
        """Median beds (300 × 80 map cm, every 330) beyond the median-side
        sidewalk of one-way painted pairs facing an opposite carriageway within
        6 map m, clear of every carriageway by 15 map cm and off every sidewalk
        (the partner's median-side sidewalk too); odd pieces carry a pine where
        its crown fits. A pair fills its median once (pieces over an earlier bed
        are its partner's)."""
        self._planting()
        s = self.scale
        placed = []
        for r, line in sorted(self.road_lines, key=lambda e: e[0]["id"]):
            m = r.get("markings") or {}
            one_way = m.get("one_way", 0)
            if not (self._ground(r) and one_way and (m.get("lanes") or 0) >= 2) or line.length < 2 * MEDIAN_BED_PITCH_CM * s: continue
            start, end = self._clearances(r, MEDIAN_FREE_END_CM)
            if one_way == -1: start, end = end, start
            beyond = (r.get("sidewalk_cm") or 0) + (MEDIAN_BED_SETBACK_CM + SIZES[MEDIAN_BED][1]) * s
            index, along = 0, start
            while along <= line.length - end:
                t = along if one_way == 1 else line.length - along
                offset = self._half_at(r, t) + beyond
                along += MEDIAN_BED_PITCH_CM * s
                sides = self._sides(r, line, t, one_way)
                if sides is None: continue
                at, h, pair = sides
                n = pair[1][1] if self.left_hand else pair[0][1]  # The median: left of travel (right in left-hand traffic).
                if not self._opposite(r, line, at, n, (h[0] * one_way, h[1] * one_way)): continue
                x, y = at.x + n[0] * offset, at.y + n[1] * offset
                theta = math.degrees(math.atan2(h[1], h[0]))
                shape = self.footprint(MEDIAN_BED, x, y, theta)
                if any(other.intersects(shape) for other in placed): continue  # The partner road's bed.
                index += 1
                if self.counts["median_beds"] + self.counts["median_beds_pine"] >= MEDIAN_BED_LIMIT:
                    self.counts["skipped_median_beds_limit"] += 1
                    continue
                if self._hits(self.carriageways, shape.buffer(MEDIAN_BED_CLEAR_CM * s)) or self._hits(self.corridors, shape):
                    self.counts["skipped_median_beds"] += 1
                    continue
                pine = index % 2 == 0 and not self._near(self.poles_at, x, y, (STREET_TREE_CROWN_CM[SPECIES["pine"]] + POLE_CLEAR_CM) * s) \
                    and not self._near(self.stops_at, x, y, STOP_CLEAR_CM * s) and self._crown_fits(SPECIES["pine"], x, y) \
                    and not self._crowded(SPECIES["pine"], x, y)
                if self.place("median_beds_pine" if pine else "median_beds", MEDIAN_PINE if pine else MEDIAN_BED, x, y, theta, r["id"],
                              steps=0, blocks=self.bed_blocks, skipped="skipped_median_beds"):
                    placed.append(shape)
                    if pine: self._planted(SPECIES["pine"], x, y)

    def planters(self):
        """Planters (80 × 30 map cm) along building fronts of sidewalk avenues:
        midway between tree stations every fourth gap, per side by chance, when a
        building lies within 3 map m behind; inside the outer band of a sidewalk
        of at least 1 map m, else just beyond the sidewalk."""
        self._planting()
        s = self.scale
        spacing = STREET_TREE_SPACING_CM * s
        half_depth = SIZES[PLANTER][1] * s
        for _, _, r, line in sorted(((_unit("street-trees", r["id"]), r["id"], r, line) for r, line in self.road_lines if self._avenue(r, line)), key=lambda a: a[:2]):
            start, end = self._clearances(r, FREE_END_CM)
            sidewalk = r.get("sidewalk_cm") or 0
            wide = sidewalk >= PLANTER_WIDE_CM * s
            beyond = sidewalk + (-(PLANTER_INSET_CM * s + half_depth) if wide else GAP_CM * s + half_depth)
            j = 0
            while True:
                t = start + (PLANTER_EVERY * j + 1.5) * spacing
                if t + spacing / 2 > line.length - end: break
                j += 1
                offset = self._half_at(r, t) + beyond
                sides = self._sides(r, line, t)
                if sides is None: continue
                at, h, pair = sides
                for side, n in pair:
                    if _unit("planter", r["id"], j, side) >= PLANTER_CHANCE: continue
                    x, y = at.x + n[0] * offset, at.y + n[1] * offset
                    probe = LineString([(x, y), (x + n[0] * PLANTER_FRONT_CM * s, y + n[1] * PLANTER_FRONT_CM * s)])
                    if not self._hits(self.solid, probe): continue
                    theta = math.degrees(math.atan2(h[1], h[0]))
                    shape = self.footprint(PLANTER, x, y, theta)
                    if self.counts["planters"] >= PLANTER_LIMIT:
                        self.counts["skipped_planters_limit"] += 1
                        continue
                    geoms, tree = self.corridors
                    if any(geoms[int(i)].intersects(shape) and (self.corridor_ids[int(i)] != r["id"] or not wide) for i in tree.query(shape)):
                        self.counts["skipped_planters"] += 1
                        continue
                    self.place("planters", PLANTER, x, y, theta, r["id"], steps=0, blocks=self.planter_blocks)

    # Streetlights --------------------------------------------------------------

    def _lamp_class(self, r):
        """Arrangement of a lit vehicle ground road (LAMP_CLASSES), else None."""
        if not self._ground(r) or r["id"] in self.walking_ids: return None
        m = r.get("markings") or {}
        highway = (getattr(self, "road_info", {}).get(r["id"]) or {}).get("highway")
        if highway is not None:
            if highway not in LAMP_CLASSES: return None
        elif not m.get("stop_lines"):
            return None
        lanes = m.get("lanes") or 0
        if highway is not None and highway.endswith("_link"): return "one_side"
        if m.get("one_way"): return "staggered" if lanes >= 3 else "one_side"
        return "opposite" if lanes >= 6 else "staggered" if lanes >= 4 else "one_side"

    def _lamp_setup(self):
        """Blocking geometry of streetlights, built once: per-segment road
        corridors with sidewalks + CLEARANCE_CM (across two-arm joins and over
        joint faces), junction mouths, buildings + GAP, water and narrow painted
        walking ribbons (the pole); buildings, decks, barriers, crowns and tall
        furniture (the display envelope)."""
        self._planting()
        s = self.scale
        poles = []
        for r in self.roads:
            if len(set((q[0], q[2]) for q in r["points"])) < 2: continue
            poles.append(self._band(r, (r.get("sidewalk_cm") or 0) + CLEARANCE_CM * s, 16))  # Round ends at width changes stay round.
        ends = {}
        for r in self.roads:
            if len(r["points"]) < 2: continue
            for end in ("from", "to"): ends.setdefault(r[end], []).append((r, end))
        for node, arms in sorted(ends.items()):
            if len(arms) != 2: continue
            (a, ea), (b, eb) = arms
            before = a["points"][-2] if ea == "to" else a["points"][1]
            at = a["points"][-1] if ea == "to" else a["points"][0]
            after = b["points"][1] if eb == "from" else b["points"][-2]
            corner = [(before[0], before[2]), (at[0], at[2]), (after[0], after[2])]
            if len(set(corner)) == 3:
                half = max(a["widths_cm"][-1 if ea == "to" else 0], b["widths_cm"][0 if eb == "from" else -1]) / 2
                extra = max(a.get("sidewalk_cm") or 0, b.get("sidewalk_cm") or 0) + CLEARANCE_CM * s
                poles.append(LineString(corner).buffer(half + extra, quad_segs=2, join_style="mitre", mitre_limit=10.0))
        # Joint faces (interior vertices and two-arm joins) taper to the wider segment.
        poles += [face.buffer(sidewalk + CLEARANCE_CM * s, quad_segs=2, join_style="mitre", mitre_limit=10.0) for face, sidewalk in self.joints]
        near = [g.buffer(GAP_CM * s) for g in self.buildings]
        self.lamp_blocks = self._index(poles + self.mouths + near + self.water + self.ribbons)
        self.lamp_solid = self._index(near)
        decks = [LineString([(q[0], q[2]) for q in r["points"]]).buffer(max(r["widths_cm"]) / 2 + (20 + LAMP_DECK_CLEAR_CM) * s, quad_segs=2)
                 for r in self.roads if r.get("kind") in ("bridge", "elevated") and len(set((q[0], q[2]) for q in r["points"])) >= 2]
        self.lamp_decks = self._index(decks) if decks else None
        self.lamp_barriers = self._index(self.barriers) if self.barriers else None
        signals, stops, posts = [], [], []
        self.lamp_gaps = {}  # Street trees and median beds: stations try the midpoints between them.
        cell = STREET_TREE_GRID_CM * s
        for item in self.items:
            asset, (x, _, y) = item["asset_id"], item["position"]
            if asset in STREET_TREE_CROWN_CM or asset in (MEDIAN_BED, MEDIAN_PINE):
                self.lamp_gaps.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append((x, y, 0))
            if asset in (self.signal, GUIDE): signals.append(Point(x, y))
            elif asset in STOPS: stops.append(self.footprint(asset, x, y, item["quarter_turns"] * 90 + item["yaw_offset_mdeg"] / 1000))
            elif asset in SIGN_POLE: posts.append(Point(x, y))
        self.lamp_signals, self.lamp_stops, self.lamp_posts = (self._index(g) if g else None for g in (signals, stops, posts))
        self.lamp_grid, self.lamp_heads = {}, {}

    def _joints(self, roads):
        """(face, sidewalk) of MapKit's joint faces: at every interior vertex of
        a record (its sidewalk) and at every two-arm node (the wider sidewalk)."""
        faces = []
        for r in roads:
            points = [(q[0], q[2]) for q in r["points"]]
            if len(set(points)) < 2: continue
            for i in range(1, len(points) - 1):
                faces.append((self._joint(points[i], points[i - 1], points[i + 1], r["widths_cm"][i - 1] / 2, r["widths_cm"][i] / 2), r.get("sidewalk_cm") or 0))
        ends = {}
        for r in roads:
            if len(r["points"]) < 2: continue
            for end in ("from", "to"): ends.setdefault(r[end], []).append((r, end))
        for node, arms in sorted(ends.items()):
            if len(arms) != 2: continue
            (a, ea), (b, eb) = arms
            before = a["points"][-2] if ea == "to" else a["points"][1]
            at = a["points"][-1] if ea == "to" else a["points"][0]
            after = b["points"][1] if eb == "from" else b["points"][-2]
            corner = [(before[0], before[2]), (at[0], at[2]), (after[0], after[2])]
            if len(set(corner)) == 3:
                faces.append((self._joint(corner[1], corner[0], corner[2], a["widths_cm"][-1 if ea == "to" else 0] / 2, b["widths_cm"][0 if eb == "from" else -1] / 2),
                              max(a.get("sidewalk_cm") or 0, b.get("sidewalk_cm") or 0)))
        return [(face, sidewalk) for face, sidewalk in faces if face is not None and not face.is_empty]

    def _joint(self, vertex, before, after, half_before, half_after):
        """MapKit's face where two segments meet (road_plan plan_junction): each
        arm's mouth, set back min(larger half width, 40% of the segment) along
        it and as wide as its own segment; on each side the two edges continue
        from the mouths to where they meet (a concave meeting rounded by
        MapKit's fillet of the wider segment), else a straight edge joins the
        mouths (towards the wider segment, or where the edges meet behind a
        mouth). A superset: convex corners stay unrounded."""
        radius = max(half_before, half_after)
        arms = []
        for other, half in ((before, half_before), (after, half_after)):
            dx, dy = other[0] - vertex[0], other[1] - vertex[1]
            length = math.hypot(dx, dy)
            if length == 0: return None
            ux, uy = dx / length, dy / length
            back = min(radius, 0.4 * length)
            cx, cy = vertex[0] + ux * back, vertex[1] + uy * back
            arms.append(((cx - uy * half, cy + ux * half), (cx + uy * half, cy - ux * half), (-ux, -uy)))
        (a_left, a_right, (ax, ay)), (b_left, b_right, (bx, by)) = arms
        det = bx * ay - ax * by  # p + t·(ax, ay) = q + u·(bx, by): the edges towards the vertex.

        def side(p, q):  # p on the first arm, q on the second.
            if abs(det) <= 1e-9: return None
            wx, wy = q[0] - p[0], q[1] - p[1]
            t, u = (bx * wy - by * wx) / det, (ax * wy - ay * wx) / det
            if t < 0 or u < 0: return None
            m = (p[0] + ax * t, p[1] + ay * t)
            return m if math.hypot(m[0] - vertex[0], m[1] - vertex[1]) <= 10 * radius else None

        # The arms point away from the vertex in opposite senses: one arm's left
        # edge continues the other's right edge.
        right, left = side(a_left, b_right), side(a_right, b_left)
        ring = [a_left, *([right] if right else []), b_right, b_left, *([left] if left else []), a_right]
        face = Polygon(ring)
        if not face.is_valid: return MultiPoint(ring).convex_hull  # Folded sharp bends: the hull covers them.
        caps = []
        for m, p, q in ((right, a_left, b_right), (left, b_left, a_right)):
            # A concave meeting turns against the ring's winding.
            if m is None or ((m[0] - p[0]) * (q[1] - m[1]) - (m[1] - p[1]) * (q[0] - m[0])) * (1 if face.exterior.is_ccw else -1) >= 0: continue
            arc = self._fillet(p, m, q, min(max(0.3 * radius, 20 * self.scale), 100 * self.scale))
            if len(arc) >= 2: caps.append(Polygon([m, *arc]))
        caps = [c for c in caps if c.is_valid and not c.is_empty]
        return unary_union([face, *caps]) if caps else face

    def _fillet(self, a, p, b, radius):
        """Points of MapKit's fillet at p between edges a-p and p-b (road_plan
        fillet: tangent at most 45% along either edge), else []."""
        la, lb = math.hypot(p[0] - a[0], p[1] - a[1]), math.hypot(b[0] - p[0], b[1] - p[1])
        if la < 2 * self.scale or lb < 2 * self.scale: return []
        u = ((p[0] - a[0]) / la, (p[1] - a[1]) / la)
        v = ((b[0] - p[0]) / lb, (b[1] - p[1]) / lb)
        turn = math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])
        if abs(turn) < 0.001: return []
        tangent = math.tan(abs(turn) / 2)
        distance = min(radius * tangent, 0.45 * la, 0.45 * lb)
        r = distance / tangent
        start = (p[0] - u[0] * distance, p[1] - u[1] * distance)
        sign = math.copysign(1, turn)
        centre = (start[0] - u[1] * sign * r, start[1] + u[0] * sign * r)
        theta = math.atan2(start[1] - centre[1], start[0] - centre[0])
        n = max(2, math.ceil(abs(turn) / (math.pi / 36)))
        return [(centre[0] + r * math.cos(theta + turn * i / n), centre[1] + r * math.sin(theta + turn * i / n)) for i in range(n + 1)]

    def _envelope(self, x, y, theta, reach, twin, back=None):
        """Display envelope polygon (source cm) of a lamp at (x, y), local +x at theta."""
        s = self.scale
        x0 = -(reach + LAMP_TIP_CM) * s if twin else -LAMP_BACK_CM * s
        x1 = (reach + LAMP_TIP_CM) * s if back is None else back
        if back is not None: x0 = -back
        side = LAMP_SIDE_CM * s
        c, n = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        return Polygon([(x + c * px - n * py, y + n * px + c * py) for px, py in ((x0, -side), (x1, -side), (x1, side), (x0, side))])

    def _grid_near(self, grid, x, y, reach, cell):
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        k = math.ceil(reach / cell)
        for gx in range(cx - k, cx + k + 1):
            for gy in range(cy - k, cy + k + 1):
                yield from grid.get((gx, gy), ())

    def _lamp_misfit(self, asset, x, y, theta, reach, twin):
        """Why a lamp cannot stand at (x, y) turned to theta, else None."""
        s = self.scale
        if not self.free(self.footprint(asset, x, y, theta), self.lamp_blocks, LAMP_GAP_CM): return "blocked"
        envelope = self._envelope(x, y, theta, reach, twin)
        if self._hits(self.lamp_solid, envelope): return "building"
        if self.lamp_decks is not None and self._hits(self.lamp_decks, envelope): return "deck"
        if self.lamp_barriers is not None and self._hits(self.lamp_barriers, self._envelope(x, y, theta, reach, twin, LAMP_BACK_CM * s)): return "barrier"
        pole = Point(x, y)
        if self.lamp_signals is not None and self._hits(self.lamp_signals, pole.buffer(LAMP_SIGNAL_CLEAR_CM * s, quad_segs=4)): return "signal"
        if self.lamp_stops is not None and self._hits(self.lamp_stops, pole.buffer(LAMP_STOP_CLEAR_CM * s, quad_segs=4)): return "stop"
        if self.lamp_posts is not None and self._hits(self.lamp_posts, pole.buffer(LAMP_POST_CLEAR_CM * s, quad_segs=4)): return "sign"
        span = (reach + LAMP_TIP_CM + LAMP_BACK_CM) * s
        crown = max(STREET_TREE_CROWN_CM.values()) * s
        cell = STREET_TREE_GRID_CM * s
        for ox, oy, other in self._grid_near(self.tree_grid, x, y, span + crown, cell):
            if abs(ox - x) <= span + other and abs(oy - y) <= span + other and envelope.distance(Point(ox, oy)) < other: return "crown"
        cell = 1000 * s
        grown = envelope.buffer(GAP_CM * s, quad_segs=1)
        for ox, oy, other in self._grid_near(self.lamp_grid, x, y, 2 * (LAMP_MAX_REACH_CM + LAMP_TIP_CM) * s, cell):
            if math.hypot(ox - x, oy - y) < LAMP_LAMP_CLEAR_CM * s or other.intersects(grown): return "lamp"
        return None

    def _lamp_placed(self, x, y, theta, reach, twin):
        s = self.scale
        cell = 1000 * s
        self.lamp_grid.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append((x, y, self._envelope(x, y, theta, reach, twin)))
        c, n = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        for sign in ((1, -1) if twin else (1,)):
            hx, hy = x + sign * c * reach * s, y + sign * n * reach * s
            self.lamp_heads.setdefault((math.floor(hx / cell), math.floor(hy / cell)), []).append((hx, hy, sign * c, sign * n))

    def _covered(self, hx, hy, fx, fy, radius):
        """An earlier lamp head within `radius` facing the same way (it lights this spot)."""
        for ox, oy, gx, gy in self._grid_near(self.lamp_heads, hx, hy, radius, 1000 * self.scale):
            if math.hypot(ox - hx, oy - hy) < radius and gx * fx + gy * fy > 0.5: return True
        return False

    def _lamp_chains(self):
        """Chains of lit records through two-arm nodes of the same arrangement
        (one-way records only in their travel sense): (arrangement, travel,
        [(road, line, reversed)]), travel = the one-way sense along the chain."""
        lit = {}
        for r, line in self.road_lines:
            kind = self._lamp_class(r)
            if kind is not None and line.length > 0: lit[r["id"]] = (r, line, kind)
        link = {}
        for node, arms in self.incident.items():
            if len(arms) != 2: continue
            (a, ea), (b, eb) = arms
            if a is b or a["id"] not in lit or b["id"] not in lit or lit[a["id"]][2] != lit[b["id"]][2]: continue
            oa, ob = (a.get("markings") or {}).get("one_way", 0), (b.get("markings") or {}).get("one_way", 0)
            if bool(oa) != bool(ob): continue
            if oa and ((oa == 1) == (ea == "to")) == ((ob == 1) == (eb == "to")): continue  # Both arrive or both leave.
            link[(a["id"], ea)], link[(b["id"], eb)] = (b["id"], eb), (a["id"], ea)
        other = lambda end: "to" if end == "from" else "from"
        seen, chains = set(), []
        for rid in sorted(lit):
            if rid in seen: continue
            cur, end, guard = rid, "from", {rid}
            while (cur, end) in link:
                o, oe = link[(cur, end)]
                if o in guard:
                    cur, end = rid, "from"
                    break
                guard.add(o)
                cur, end = o, other(oe)
            pieces = []
            while cur not in seen:
                seen.add(cur)
                r, line, kind = lit[cur]
                pieces.append((r, line, end == "to"))
                nxt = link.get((cur, other(end)))
                if nxt is None: break
                cur, end = nxt
            first, line, reversed_ = pieces[0]
            travel = (first.get("markings") or {}).get("one_way", 0) * (-1 if reversed_ else 1)
            chains.append((lit[rid][2], travel, pieces))
        return chains

    def _chain_spot(self, pieces, s):
        """(road, line, t, direction) at chain arc length s."""
        for i, (r, line, reversed_) in enumerate(pieces):
            if s <= line.length or i == len(pieces) - 1:
                s = min(max(s, 0.0), line.length)
                return r, line, (line.length - s if reversed_ else s), (-1 if reversed_ else 1)
            s -= line.length

    def _chain_ends(self, pieces):
        first, _, rev = pieces[0]
        last, _, rev_last = pieces[-1]
        start = self._clearances(first, LAMP_FREE_END_CM)[1 if rev else 0]
        end = self._clearances(last, LAMP_FREE_END_CM)[0 if rev_last else 1]
        return start, sum(line.length for _, line, _ in pieces) - end

    @staticmethod
    def _stations(start, stop, spacing, phase):
        """Stations every `spacing` centred in [start, stop], shifted by phase × spacing."""
        if stop < start: return []
        n = math.floor((stop - start) / spacing) + 1
        first = start + (stop - start - (n - 1) * spacing) / 2 + phase * spacing
        return [first + k * spacing for k in range(n) if first + k * spacing <= stop]

    def _median_gap(self, r, line, at, normal, heading):
        """(distance from this edge to the nearest opposite one-way
        carriageway within MEDIAN_PROBE_CM on the `normal` side, that road),
        else None."""
        s = self.scale
        half = self._half_at(r, line.project(at))
        a = Point(at.x + normal[0] * (half + 2 * CARRIAGEWAY_CM * s), at.y + normal[1] * (half + 2 * CARRIAGEWAY_CM * s))
        probe = LineString([(a.x, a.y), (at.x + normal[0] * (half + MEDIAN_PROBE_CM * s), at.y + normal[1] * (half + MEDIAN_PROBE_CM * s))])
        geoms, tree = self.carriageways
        best = None
        for i in tree.query(probe):
            other = self.carriage_roads[int(i)]
            if other is None or other is r or other["id"] in self.walking_ids or not self._ground(other): continue
            one_way = (other.get("markings") or {}).get("one_way", 0)
            if not one_way or not geoms[int(i)].intersects(probe): continue
            o = self.lines.get(other["id"])
            h = None if o is None else self._tangent(o, o.project(at), one_way)
            if h is None or h[0] * heading[0] + h[1] * heading[1] > -HEADING_COS: continue
            d = a.distance(geoms[int(i)]) + 3 * CARRIAGEWAY_CM * s  # Bands are grown by CARRIAGEWAY_CM.
            if best is None or d < best[0]: best = (d, other)
        return best

    def _lamp_at(self, pieces, s, side, travel, median):
        """(asset, x, y, theta, reach, twin, road id) of the lamp for chain arc s
        on `side` (+1 left of the chain direction, -1 right), else (reason,)."""
        sc = self.scale
        r, line, t, direction = self._chain_spot(pieces, s)
        h = self._tangent(line, t, direction)
        if h is None: return ("blocked",)
        n = (-h[1] * side, h[0] * side)
        at = line.interpolate(t)
        half = self._half_at(r, t)
        theta = math.degrees(math.atan2(-n[1], -n[0]))
        if median:
            found = self._median_gap(r, line, at, n, (h[0] * travel, h[1] * travel))
            if found is not None:
                # A pole at the median centre clears both bands (each grown by
                # its own sidewalk + CLEARANCE_CM) by its half and LAMP_GAP_CM.
                gap, other = found
                widest = max(r.get("sidewalk_cm") or 0, other.get("sidewalk_cm") or 0)
                if gap < 2 * widest + 2 * (CLEARANCE_CM + LAMP_POLE_CM // 2 + LAMP_GAP_CM) * sc: return ("median",)
                for asset, reach in TWIN_REACH_CM.items():
                    if gap / 2 + LAMP_OVERHANG_CM * sc <= reach * sc:
                        x, y = at.x + n[0] * (half + gap / 2), at.y + n[1] * (half + gap / 2)
                        return asset, x, y, theta, reach, True, r["id"]
        sidewalk = r.get("sidewalk_cm") or 0
        need = sidewalk + (LAMP_POLE_OFFSET_CM + LAMP_OVERHANG_CM) * sc
        for asset, reach in STREETLIGHT_REACH_CM.items():
            if reach * sc >= need:
                offset = half + sidewalk + LAMP_POLE_OFFSET_CM * sc
                return asset, at.x + n[0] * offset, at.y + n[1] * offset, theta, reach, False, r["id"]
        return ("reach",)

    def _lamp_offsets(self, pieces, s):
        """Chain arc lengths to try for station s, nearest first: s, nudges of
        LAMP_NUDGE_CM and the midpoints between the street trees and median
        beds along the road, within LAMP_NUDGE_STEPS nudges."""
        sc = self.scale
        reach = LAMP_NUDGE_STEPS * LAMP_NUDGE_CM * sc
        offsets = {0.0} | {k * LAMP_NUDGE_CM * sc for k in range(-LAMP_NUDGE_STEPS, LAMP_NUDGE_STEPS + 1)}
        r, line, t, direction = self._chain_spot(pieces, s)
        at = line.interpolate(t)
        span = reach + STREET_TREE_SPACING_CM * sc
        along = sorted({round((line.project(Point(ox, oy)) - t) * direction, 3)
                        for ox, oy, _ in self._grid_near(self.lamp_gaps, at.x, at.y, span + 400 * sc, STREET_TREE_GRID_CM * sc)
                        if math.hypot(ox - at.x, oy - at.y) <= span + 400 * sc})
        offsets |= {(a + b) / 2 for a, b in zip(along, along[1:]) if abs(a + b) / 2 <= reach}
        return [s + d for d in sorted(offsets, key=lambda d: (abs(d), d))]

    def _lamp_try(self, pieces, s, side, travel, median, bounds, place, kind):
        """Try station s and its nudges; place the first fit when `place`.
        Returns None when it fits (or is placed), else the reason: the first
        specific one (a building, crown, signal...) over the tried offsets,
        "blocked" only when nothing more specific stopped them."""
        first = None
        for at in self._lamp_offsets(pieces, s):
            if not (bounds[0] <= at <= bounds[1]): continue
            spot = self._lamp_at(pieces, at, side, travel, median)
            if len(spot) == 1:
                if spot[0] in ("reach", "median"): return spot[0]
                if first in (None, "blocked"): first = spot[0]
                continue
            asset, x, y, theta, reach, twin, road = spot
            reason = self._lamp_misfit(asset, x, y, theta, reach, twin)
            if reason is not None:
                if first in (None, "blocked"): first = reason
                continue
            if not place: return None
            label = "streetlights_twin" if twin else "streetlights_" + kind
            if self.place(label, asset, x, y, theta, road, steps=0, blocks=self.lamp_blocks, skipped="skipped_streetlights_blocked", gap=LAMP_GAP_CM):
                self._lamp_placed(x, y, theta, reach, twin)
            return None
        return first or "blocked"

    def streetlights(self):
        """City streetlights along arterials and collectors, after every other
        placement (earlier IDs never move): solid poles beside the road behind
        its sidewalk + CLEARANCE_CM (and off narrow painted walking ribbons),
        the arm id chosen so the head centre stands 25-85 map cm over the
        carriageway (sidewalks up to 312 map cm); opposite pairs, staggered rows or one
        side by arrangement; twins in narrow medians of one-way pairs (the head
        over both carriageways), single lamps at wider median edges. Stations
        nudge up to half a tree spacing into gaps between street-tree crowns.
        Spacing widens in steps until the rows fit the remaining budget."""
        self._lamp_setup()
        sc = self.scale
        chains = sorted(((_unit("streetlights", pieces[0][0]["id"]), pieces[0][0]["id"], kind, travel, pieces)
                         for kind, travel, pieces in self._lamp_chains()), key=lambda c: c[:2])
        drive = -1 if self.left_hand else 1  # Travel +1 along the chain: driver's right is side -1 (left in left-hand traffic).
        plans = []
        for _, _, kind, travel, pieces in chains:
            start, stop = self._chain_ends(pieces)
            if kind == "one_side":
                sides = [(-travel * drive if travel else None, 0.0)]  # One-way: the driver's side.
            else:
                sides = [(1, 0.0), (-1, 0.0 if kind == "opposite" else 0.5)]
            plans.append((kind, travel, pieces, start, stop, sides))
        budget = max(0, min(STREETLIGHT_LIMIT, MAX_PLACEMENTS - len(self.items)))
        total = lambda factor: sum(len(self._stations(start, stop, LAMP_SPACING_CM[kind] * sc * factor, phase))
                                   for kind, _, _, start, stop, sides in plans for _, phase in sides)
        factor, nominal = 1.0, total(1.0)
        while total(factor) > budget and factor < LAMP_SPACING_MAX: factor = round(factor + LAMP_SPACING_STEP, 2)
        if budget == 0: plans = []
        self.counts["skipped_streetlights_spacing"] += nominal - (total(factor) if plans else 0)
        for kind, travel, pieces, start, stop, sides in plans:
            spacing = LAMP_SPACING_CM[kind] * sc * factor
            for side, phase in sides:
                stations = self._stations(start, stop, spacing, phase)
                if side is None:
                    # Two-way one-side rows: the side with more free stations (a seeded tie-break).
                    fits = [sum(self._lamp_try(pieces, s, d, travel, False, (start, stop), False, None) is None for s in stations) for d in (1, -1)]
                    side = 1 if fits[0] > fits[1] or fits[0] == fits[1] and _unit("streetlights", pieces[0][0]["id"], "side") < 0.5 else -1
                median = bool(travel) and side == travel * drive  # Left of travel (right in left-hand traffic).
                for s in stations:
                    spot = self._lamp_at(pieces, s, side, travel, median)
                    if len(spot) > 1:
                        asset, x, y, theta, reach, twin, _ = spot
                        c, n = math.cos(math.radians(theta)), math.sin(math.radians(theta))
                        if self._covered(x + c * reach * sc, y + n * reach * sc, c, n, LAMP_COVER_SHARE * spacing):
                            self.counts["skipped_streetlights_covered"] += 1
                            continue
                    if len(self.items) >= MAX_PLACEMENTS or self._lamp_total() >= STREETLIGHT_LIMIT:
                        self.counts["skipped_streetlights_limit"] += 1
                        continue
                    reason = self._lamp_try(pieces, s, side, travel, median, (start, stop), True, kind)
                    if reason is not None: self.counts["skipped_streetlights_" + reason] += 1

    def _lamp_total(self):
        return sum(v for k, v in self.counts.items() if k.startswith("streetlights_"))

    @staticmethod
    def _tangent(line, t, direction):
        """Unit travel heading at distance t along `line` for a direction ±1."""
        a, b = line.interpolate(max(0.0, t - 1.0)), line.interpolate(min(line.length, t + 1.0))
        hx, hy = (b.x - a.x) * direction, (b.y - a.y) * direction
        length = math.hypot(hx, hy)
        return (hx / length, hy / length) if length else None


def generate(layer_id, patches, coordinates, scale, traffic, road_info=None, school_areas=None):
    """(placement records, counts) for a converted city layer. `road_info`
    (road id -> {highway, name, maxspeed}) and `school_areas` (source-cm rings)
    are transient conversion inputs of the road signs and street trees."""
    furniture = Furniture(patches, coordinates, scale, traffic)
    street = coordinates.get("osm_street_points", [])
    furniture.signals([p for p in street if p["kind"] == "traffic_signals"])
    furniture.stops(street)
    furniture.parks(coordinates.get("generation_regions", []))
    furniture.road_signs(street, coordinates.get("generation_regions", []), road_info, school_areas)
    furniture.street_trees(street)
    furniture.median_beds()
    furniture.planters()
    furniture.streetlights()
    records = [dict(id=f"import-{layer_id}-place-{index:05d}", asset_id=item["asset_id"], position=item["position"],
                    quarter_turns=item["quarter_turns"], **({"yaw_offset_mdeg": item["yaw_offset_mdeg"]} if item["yaw_offset_mdeg"] else {}))
               for index, item in enumerate(furniture.items)]
    return records, dict(sorted(furniture.counts.items()))
