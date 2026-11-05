"""Generated city street furniture, road signs and park details (Editor-only, current v1).

OSM gives where bus stops, stations, subway entrances and signals are, not what
they look like; parks give an area. These rules place MapKit builtins at those
positions with fixed-seed variation, in the layer's source centimetres (÷D at
adoption), clear of road corridors, junction mouths, buildings, water and each
other. Road signs follow last (`Furniture.road_signs`): OSM stop/give-way nodes,
then signs derived from the road graph, its markings, the OSM road class and
posted speed, and school sites. A candidate that finds no free spot is skipped
and counted.
"""
from collections import Counter
import hashlib
import math

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

# Map-centimetre sizes (×D gives source cm): footprint half sizes along local
# x (across the asset's front) and y.
SIZES = {"builtin:signal_h": (4, 4), "builtin:signal_v": (4, 4), "builtin:bus_shelter": (80, 25),
         "builtin:subway_entrance": (40, 60), "builtin:station_sign": (12, 12), "builtin:bench": (40, 40),
         "builtin:shrub": (35, 35), "builtin:tree": (200, 200)}
CLEARANCE_CM = 30  # Beyond the road edge and sidewalk.
GAP_CM = 10  # Between placements.
PARK_KINDS = ("park", "garden", "playground", "recreation_ground", "village_green")
# Park trees are MapKit vegetation zones of city trees (osm_generalize.CITY_ZONES).
PARK_GRID_CM = {"builtin:bench": 1500, "builtin:shrub": 600}
PARK_CHANCE = {"builtin:bench": 0.25, "builtin:shrub": 0.35}
MAX_PLACEMENTS = 8000
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
        roads = [p["after"] for p in patches if p["field"] == "roads"]
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
        for p in patches:
            if p["field"] == "buildings":
                rings = [p["after"]["footprint"]] + [part["footprint"] for part in p["after"].get("parts", [])]
                blocks.extend(Polygon(ring).buffer(GAP_CM * scale) for ring in rings if len(ring) >= 3)
            elif p["field"] == "water_bodies":
                blocks.append(Polygon(p["after"]["polygon"]))
        # Junction mouths reach about √2 × the widest half width from the node.
        arms = Counter()
        half = Counter()
        for r in self.vehicle:
            for end in ("from", "to"):
                arms[r[end]] += 1
                half[r[end]] = max(half[r[end]], max(r["widths_cm"]) / 2 + (r.get("sidewalk_cm") or 0))
        for node, count in arms.items():
            if count >= 3 and node in self.nodes:
                at = self.nodes[node]["position"]
                blocks.append(Point(at[0], at[2]).buffer(math.sqrt(2) * half[node] + margin, quad_segs=4))
        self.arms, self.half = arms, half
        self.blocks = blocks
        self.tree = STRtree(blocks)
        self.placed = {}  # Spatial hash (BUCKET_CM cells) of placed footprints.
        self.road_lines = [(r, LineString([(q[0], q[2]) for q in r["points"]])) for r in self.vehicle if len(r["points"]) >= 2]
        self.road_tree = STRtree([g for r, g in self.road_lines])
        self.incident = {}
        for r in self.vehicle:
            for end in ("from", "to"):
                self.incident.setdefault(r[end], []).append((r, end))
        self.signalled = set()  # Junction nodes that qualify for signal poles.
        self.pois = [p["after"] for p in patches if p["field"] == "pois"]

    def footprint(self, asset, x, y, theta):
        hx, hy = (v * self.scale for v in SIZES[asset])
        c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        return Polygon([(x + c * px - s * py, y + s * px + c * py) for px, py in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])

    def buckets(self, shape):
        x0, y0, x1, y1 = shape.bounds
        return [(i, j) for i in range(math.floor(x0 / BUCKET_CM), math.floor(x1 / BUCKET_CM) + 1)
                for j in range(math.floor(y0 / BUCKET_CM), math.floor(y1 / BUCKET_CM) + 1)]

    def free(self, shape):
        if any(self.blocks[int(i)].intersects(shape) for i in self.tree.query(shape)): return False
        grown = shape.buffer(GAP_CM * self.scale)
        return not any(other.intersects(grown) for key in self.buckets(grown) for other in self.placed.get(key, ()))

    def place(self, kind, asset, x, y, theta, source, nudge=(0.0, 0.0), steps=4, accept=None):
        """Place at (x, y) or up to `steps` nudges along `nudge` (source cm per
        step); `accept(px, py)` may reject a spot as not free."""
        for step in range(steps + 1):
            px, py = x + nudge[0] * step, y + nudge[1] * step
            if accept is not None and not accept(px, py): continue
            shape = self.footprint(asset, px, py, theta)
            if not self.free(shape): continue
            if len(self.items) >= MAX_PLACEMENTS:
                self.counts["over_limit"] += 1
                return False
            for key in self.buckets(shape): self.placed.setdefault(key, []).append(shape)
            turns, offset = _pose(theta)
            self.items.append(dict(asset_id=asset, position=[round(px), 0, round(py)], quarter_turns=turns, yaw_offset_mdeg=offset, source_id=source))
            self.counts[kind] += 1
            return True
        self.counts["skipped_" + kind] += 1
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
            if kind in ("traffic_signals", "stop", "give_way"): continue
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
        """Traffic signs beside vehicle ground roads, after every other placement.

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

    @staticmethod
    def _tangent(line, t, direction):
        """Unit travel heading at distance t along `line` for a direction ±1."""
        a, b = line.interpolate(max(0.0, t - 1.0)), line.interpolate(min(line.length, t + 1.0))
        hx, hy = (b.x - a.x) * direction, (b.y - a.y) * direction
        length = math.hypot(hx, hy)
        return (hx / length, hy / length) if length else None


def generate(layer_id, patches, coordinates, scale, traffic, road_info=None, school_areas=None):
    """(placement records, counts) for a converted city layer. `road_info`
    (road id -> {highway, maxspeed}) and `school_areas` (source-cm rings) are
    transient conversion inputs of the road signs."""
    furniture = Furniture(patches, coordinates, scale, traffic)
    street = coordinates.get("osm_street_points", [])
    furniture.signals([p for p in street if p["kind"] == "traffic_signals"])
    furniture.stops(street)
    furniture.parks(coordinates.get("generation_regions", []))
    furniture.road_signs(street, coordinates.get("generation_regions", []), road_info, school_areas)
    records = [dict(id=f"import-{layer_id}-place-{index:05d}", asset_id=item["asset_id"], position=item["position"],
                    quarter_turns=item["quarter_turns"], **({"yaw_offset_mdeg": item["yaw_offset_mdeg"]} if item["yaw_offset_mdeg"] else {}))
               for index, item in enumerate(furniture.items)]
    return records, dict(sorted(furniture.counts.items()))
