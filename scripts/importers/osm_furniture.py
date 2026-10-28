"""Generated city street furniture and park details (Editor-only, current v1).

OSM gives where bus stops, stations, subway entrances and signals are, not what
they look like; parks give an area. These rules place MapKit builtins at those
positions with fixed-seed variation, in the layer's source centimetres (÷D at
adoption), clear of road corridors, junction mouths, buildings, water and each
other. A candidate that finds no free spot is skipped and counted.
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
PARK_GRID_CM = {"builtin:tree": 1000, "builtin:bench": 1500, "builtin:shrub": 600}
PARK_CHANCE = {"builtin:tree": 0.35, "builtin:bench": 0.25, "builtin:shrub": 0.35}
MAX_PLACEMENTS = 8000
BUCKET_CM = 3000
SIGNAL_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary")


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

    def place(self, kind, asset, x, y, theta, source, nudge=(0.0, 0.0), steps=4):
        """Place at (x, y) or up to `steps` nudges along `nudge` (source cm per step)."""
        for step in range(steps + 1):
            px, py = x + nudge[0] * step, y + nudge[1] * step
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
        incident = {}
        for r in self.vehicle:
            for end in ("from", "to"):
                incident.setdefault(r[end], []).append((r, end))
        for node, arms in sorted(incident.items()):
            if len(arms) < 3 or node not in self.nodes: continue
            at = self.nodes[node]["position"]
            centre = Point(at[0], at[2])
            arterial = sum(bool((r.get("markings") or {}).get("stop_lines")) for r, end in arms) >= 2
            signalled = tagged is not None and len(tagged.query(centre.buffer(1500)))  # An OSM signal within 15 source m.
            if not (arterial or signalled): continue
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
            if kind == "traffic_signals": continue
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


def generate(layer_id, patches, coordinates, scale, traffic):
    """(placement records, counts) for a converted city layer."""
    furniture = Furniture(patches, coordinates, scale, traffic)
    street = coordinates.get("osm_street_points", [])
    furniture.signals([p for p in street if p["kind"] == "traffic_signals"])
    furniture.stops(street)
    furniture.parks(coordinates.get("generation_regions", []))
    records = [dict(id=f"import-{layer_id}-place-{index:05d}", asset_id=item["asset_id"], position=item["position"],
                    quarter_turns=item["quarter_turns"], **({"yaw_offset_mdeg": item["yaw_offset_mdeg"]} if item["yaw_offset_mdeg"] else {}))
               for index, item in enumerate(furniture.items)]
    return records, dict(sorted(furniture.counts.items()))
