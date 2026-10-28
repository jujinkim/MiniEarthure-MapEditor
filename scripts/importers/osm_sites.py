"""City sites, building records, painted urban ground and barriers.

Editor-only city rules on projected source-metre features (current v1):

- Buildings keep their own footprints. Nearby buildings of one site (or 256 m
  source tile) and category become one record whose solids are MapKit
  `Building.parts`; the record groups objects, never vertices.
- Green land paints grass and parking asphalt over the city's concrete
  `ground_surface`; water is never painted.
- Explicit OSM barrier ways and inferred site perimeters become `barriers`.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math

from shapely.geometry import LineString, MultiPolygon, Point
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

TILE_M = 256  # Source-metre fallback when no site encloses a building.
MAX_SOLIDS = 256  # MapKit: a footprint plus at most 255 parts per record.
RECORD_CELL_M = 32  # Locality order of a record's solids (Z-order of 32 m cells).
SITE_KINDS = ("residential", "commercial", "retail", "industrial", "school", "hospital", "university", "college")
WATER = ("water", "reservoir", "basin")
# Area paint surfaces in priority order (pedestrian ribbons always come first).
AREA_SURFACES = ("asphalt", "concrete", "gravel", "dirt", "grass")
# Inferred perimeters (source metres, ÷D on the map).
APARTMENT_COUNT = 2
APARTMENT_TALL_M = 20.0
RESIDENTIAL = ("apartments", "residential", "house", "detached", "terrace", "dormitory")
# Facade rule inputs: OSM `building` values by MapKit use, in rule order.
PUBLIC_BUILDINGS = ("public", "civic", "government", "school", "university", "college", "kindergarten", "hospital",
                    "church", "cathedral", "chapel", "mosque", "temple", "synagogue", "shrine", "train_station",
                    "transportation", "fire_station", "stadium", "sports_hall", "museum", "library")
PUBLIC_AMENITIES = ("school", "university", "college", "kindergarten", "hospital", "clinic", "place_of_worship", "townhall",
                    "police", "fire_station", "library", "community_centre", "public_building", "courthouse")
TALL_RESIDENTIAL = ("apartments", "dormitory")
HOUSES = ("house", "detached", "terrace", "semidetached_house", "bungalow", "villa", "cabin", "hut")
COMMERCIAL_BUILDINGS = ("commercial", "retail", "office", "hotel", "supermarket", "kiosk", "shop", "mall")
INDUSTRIAL_BUILDINGS = ("industrial", "warehouse", "factory", "manufacture", "service", "garage", "garages", "hangar",
                        "greenhouse", "barn", "farm_auxiliary", "shed")
WOODEN_INDUSTRIAL = ("greenhouse", "barn", "farm_auxiliary", "shed")
HOUSE_TALL_M = 12.0  # Unknown residential below this is a brick house.
LEVEL_M = 3.0  # Estimated storey height when `height` is missing.
# Untagged blocks of an apartment complex (a residential site with at least
# APARTMENT_COUNT apartment buildings): one seeded base storey count per site,
# each block varies by the site's seeded spread, clamped to COMPLEX_FLOORS.
COMPLEX_FLOORS = (10, 50)
COMPLEX_BASE = (15, 35)
COMPLEX_SPREAD = (5, 10)
COMPLEX_MIN_AREA_M2 = 250.0  # Smaller untagged buildings are annexes.
COMPLEX_BUILDINGS = ("apartments", "residential", "dormitory", "yes")
COVERAGE = 0.15
GATE_M = 2.0  # Beyond a crossing way's half width.
EXPLICIT_WINS_M = 3.0
BUILDING_GAP_M = 0.3
MIN_PIECE_M = 2.0
MIN_EXPLICIT_M = 0.5  # Explicit barrier stubs left beside a gate.
LINE_TOLERANCE_M = 0.5
MAX_POINTS = 4096
HEIGHT_CM = (10, 1000)
THICKNESS_CM = (5, 100)
# Barrier heights on the map are this fraction of the source height ÷D, so
# fences and walls only frame the road instead of hiding the city.
BARRIER_HEIGHT_FACTOR = 1 / 3
# Source-metre heights of inferred perimeters (kind, height, thickness).
INFERRED = {"residential": ("fence", 1.2, 0.1), "school": ("fence", 2.0, 0.1), "hospital": ("fence", 2.0, 0.1),
            "university": ("fence", 2.0, 0.1), "college": ("fence", 2.0, 0.1), "industrial": ("wall", 2.0, 0.3)}


def _morton(x, y):
    x, y = x + (1 << 20), y + (1 << 20)
    code = 0
    for bit in range(21):
        code |= ((x >> bit) & 1) << (2 * bit) | ((y >> bit) & 1) << (2 * bit + 1)
    return code


def _polygons(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "Polygon": return [geometry]
    return [p for g in getattr(geometry, "geoms", []) for p in _polygons(g)]


def _lines(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "LineString": return [geometry]
    return [p for g in getattr(geometry, "geoms", []) for p in _lines(g)]


def _seeded(*parts):
    """Stable integer from text parts (independent of Python hash seeds)."""
    return int.from_bytes(hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).digest()[:8], "big")


def _height(p):
    """Building height for the tall-residential and house tests: `height`,
    else 3 m per level, else 0 (unknown)."""
    if "height_m" in p: return float(p["height_m"])
    return LEVEL_M * p["_city_levels"] if "_city_levels" in p else 0.0


def rectangular(geometry):
    """An axis-aligned rectangle without holes: the only footprint MapKit
    accepts under a gable roof (placement.rs)."""
    if geometry.geom_type != "Polygon" or geometry.interiors or len(geometry.exterior.coords) != 5: return False
    corners = list(geometry.exterior.coords)[:-1]
    return len({x for x, y in corners}) == 2 and len({y for x, y in corners}) == 2


def _building(p):
    """The source `building` value (kept even after the facade rule sets the MapKit use)."""
    return p.get("_city_building") or p.get("usage", "yes")


class Sites:
    """Site polygons (landuse residential/commercial/retail/industrial and
    school/hospital/university/college grounds) enclosing city buildings."""

    def __init__(self, features, source_ids):
        self.items = [(f, g) for f, g in features if g.geom_type != "LineString" and f["properties"].get("_city_site") in SITE_KINDS]
        self.tree = STRtree([g for f, g in self.items])
        self.ids = [min(source_ids(f)) for f, g in self.items]
        self.areas = [g.area for f, g in self.items]
        # Residential sites holding at least APARTMENT_COUNT apartment buildings.
        apartments = Counter()
        for f, g in features:
            p = f["properties"]
            if g.geom_type == "LineString" or p.get("osm_region") or p.get("landuse") in ("forest", "orchard"): continue
            if not (_building(p) in TALL_RESIDENTIAL or p.get("_city_flats")): continue
            key = self.key(f, g)
            if key[0] == "site": apartments[key[1]] += 1
        self.complexes = {i for i, count in apartments.items() if count >= APARTMENT_COUNT and self.kind(("site", i)) == "residential"}

    def key(self, feature, geometry):
        """("relation", id) for a type=site member, ("site", id) for the smallest
        enclosing site polygon, else ("tile", x, y) of the 256 m source tile."""
        p = feature["properties"]
        if p.get("_city_site_relation"): return ("relation", p["_city_site_relation"])
        point = geometry.representative_point()
        found = [int(i) for i in self.tree.query(point, predicate="within")]
        if found:
            best = min(found, key=lambda i: (self.areas[i], self.ids[i]))
            return ("site", self.ids[best])
        centre = geometry.centroid
        return ("tile", math.floor(centre.x / TILE_M), math.floor(centre.y / TILE_M))

    def kind(self, key):
        """The landuse/amenity kind of a ("site", id) key, else None."""
        if key[0] != "site": return None
        return next((f["properties"]["_city_site"] for (f, g), i in zip(self.items, self.ids) if i == key[1]), None)


def complex_height(sites, key, p, geometry, source_id):
    """Seeded height (source metres) of an untagged apartment-complex block,
    else None. Tagged `height` or `building:levels` always wins."""
    if key[0] != "site" or key[1] not in sites.complexes: return None
    if "height_m" in p or "_city_levels" in p or _building(p) not in COMPLEX_BUILDINGS: return None
    if geometry.area < COMPLEX_MIN_AREA_M2: return None
    base = COMPLEX_BASE[0] + _seeded("complex-base", key[1]) % (COMPLEX_BASE[1] - COMPLEX_BASE[0] + 1)
    spread = COMPLEX_SPREAD[0] + _seeded("complex-spread", key[1]) % (COMPLEX_SPREAD[1] - COMPLEX_SPREAD[0] + 1)
    floors = base - spread + _seeded("complex-block", key[1], source_id) % (2 * spread + 1)
    return LEVEL_M * min(COMPLEX_FLOORS[1], max(COMPLEX_FLOORS[0], floors))


def facade(p, site_kind):
    """Current-v1 facade of a city building: (material, usage, roof,
    inferred) from the OSM `building` value, use tags, height and enclosing
    site, in rule order; a tagged `building:material` replaces the rule's
    material. `inferred` is True when the use is not an explicit MapKit use
    value, so review counts it as an estimate."""
    material, usage, roof, inferred = _facade(p, site_kind)
    return p.get("_city_material", material), usage, roof, inferred


def _facade(p, site_kind):
    value = p.get("_city_building") or p.get("usage", "yes")
    amenity = p.get("_city_amenity")
    height = _height(p)
    roof = "gable" if p.get("_city_roof") == "gabled" else "flat"
    inferred = value not in ("residential", "commercial", "industrial", "public")
    if value in PUBLIC_BUILDINGS or amenity in PUBLIC_AMENITIES:
        return "concrete", "public", roof, inferred
    if value in TALL_RESIDENTIAL or p.get("_city_flats"):
        return "concrete", "residential", roof, inferred
    if value in HOUSES:
        return "brick", "residential", roof, inferred
    if value in COMMERCIAL_BUILDINGS or p.get("_city_use") or amenity:
        return "concrete", "commercial", roof, inferred
    if value in INDUSTRIAL_BUILDINGS:
        return ("wood" if value in WOODEN_INDUSTRIAL else "concrete"), "industrial", roof, inferred
    site = site_kind if value == "yes" else {"residential": "residential"}.get(value)
    if site in ("commercial", "retail"): return "concrete", "commercial", roof, inferred
    if site == "industrial": return "concrete", "industrial", roof, inferred
    if site in ("school", "hospital", "university", "college"): return "concrete", "public", roof, inferred
    if site == "residential" and 0 < height < HOUSE_TALL_M: return "brick", "residential", roof, inferred
    return "concrete", "residential", roof, inferred


def building_records(items, is_building, source_ids, key):
    """One record per record key; its solids (≤256, in Z-order of 32 m cells
    then source order) become `parts` of the first. A one-solid record is
    unchanged. Returns (items, counts)."""
    rest, groups = [], defaultdict(list)
    for f, g in items:
        if not is_building(f, g):
            rest.append((f, g))
            continue
        groups[f["properties"].get("_city_record") or json.dumps(["own", source_ids(f)])].append((f, g))
    counts = Counter()
    for name in sorted(groups):
        def order(item):
            c = item[1].representative_point()
            return (_morton(math.floor(c.x / RECORD_CELL_M), math.floor(c.y / RECORD_CELL_M)), source_ids(item[0]), key(item[1]))
        members = sorted(groups[name], key=order)
        for start in range(0, len(members), MAX_SOLIDS):
            chunk = members[start:start + MAX_SOLIDS]
            counts["records"] += 1
            counts["solids"] += len(chunk)
            if len(chunk) == 1:
                rest.append(chunk[0])
                continue
            counts["grouped_records"] += 1
            feature = deepcopy(chunk[0][0])
            p = feature["properties"]
            sources = sorted({s for f, g in chunk for s in source_ids(f)})
            names = set()
            for f, g in chunk:
                q = f["properties"]
                if q.get("_city_name"): names.add(q["_city_name"])
                names.update(q.get("_city_names", []))
            p["_city_sources"] = sources
            p["_city_name"] = ""
            if names: p["_city_names"] = sorted(names)
            else: p.pop("_city_names", None)
            if any(f["properties"].get("_city_estimated_height") for f, g in chunk): p["_city_estimated_height"] = True
            p["_city_parts"] = [{k: f["properties"][k] for k in ("height_m", "base_m", "_city_levels_height") if k in f["properties"]} for f, g in chunk]
            rest.append((feature, MultiPolygon([g for f, g in chunk])))
    return rest, counts


def ground_areas(features, tolerance, surfaces, source_ids):
    """Painted area sources: [(sources, surface, polygon)] and the water union.
    Green land is grass (a tagged hard surface wins), parking asphalt."""
    areas, water = [], []
    for f, g in features:
        if g.geom_type == "LineString": continue
        p = f["properties"]
        if p.get("osm_region") and p.get("landuse") in WATER:
            water.append(g)
            continue
        ground = p.get("_city_ground")
        if not ground: continue
        mapped = surfaces.get(ground.get("surface") or "", None)
        if ground["kind"] == "parking": surface = mapped or "asphalt"
        else: surface = mapped if mapped in ("asphalt", "concrete", "gravel", "dirt") else "grass"
        shape = g.simplify(tolerance, preserve_topology=True) if tolerance else g
        if not shape.is_valid: shape = g
        for part in _polygons(shape):
            areas.append((source_ids(f), surface, part))
    return areas, water


class Barriers:
    """Explicit OSM barrier ways and inferred site perimeters, quantized to the
    1:D map lattice. Gaps are cut where walking or painted ways cross (half their
    width + 2 m each side) and at gate nodes (their width); MapKit gates vehicle
    roads itself."""

    def __init__(self, worker, explicit):
        self.worker = worker
        self.counts = Counter()
        self.kinds = Counter()
        self.items = []
        self.dropped = []  # Sources without a barrier at map scale (disclosed).
        kept = []
        self.walking = [(g, float(f["properties"].get("width_m", 1.6))) for f, g in worker.features
                        if g.geom_type == "LineString" and worker.is_walking(f)]
        self.walking_tree = STRtree([g for g, w in self.walking])
        # Bridge decks (source-height and estimated structures) with their safety furniture.
        structures = [g.buffer(float(f["properties"].get("width_m", 8)) / 2 + GATE_M) for f, g in worker.features
                      if g.geom_type == "LineString" and (f["properties"].get("road_kind", "ground") != "ground" or "_city_estimated_m" in f["properties"])]
        structure_tree = STRtree(structures)
        for f, g in explicit:
            info = f["properties"]["_city_barrier"]
            sid = f["properties"]["osm_source_id"]
            self.counts["explicit_ways"] += 1
            if info["source"] == "guard_rail":
                near = [structures[int(i)] for i in structure_tree.query(g)]
                if near and g.intersection(unary_union(near)).length >= 0.5 * g.length:
                    self.counts["skipped_bridge_guard_rails"] += 1
                    self.dropped.append(sid)
                    continue
            kept.append((sid, info, g))
            line = self.gated(g, f["properties"].get("_city_gates", []))
            pieces = [piece for piece in _lines(line) if piece.length >= MIN_EXPLICIT_M]
            made = sum(self.emit([sid], info["kind"], info["height_m"], info["thickness_m"], piece, "explicit") for piece in pieces)
            if not made:
                # Wholly inside gates and crossings, or under one map centimetre.
                self.counts["opened" if line.is_empty or not pieces else "collapsed"] += 1
                self.dropped.append(sid)
        self.explicit = [g for sid, info, g in kept]
        self.infer(worker)

    def gated(self, line, gates, cuts=()):
        """`line` minus walking-way crossings, gate nodes and further `cuts`, merged."""
        cuts = list(cuts)
        for i in self.walking_tree.query(line):
            way, width = self.walking[int(i)]
            meet = line.intersection(way)
            if not meet.is_empty: cuts.append(meet.buffer(width / 2 + GATE_M))
        cuts.extend(Point(x, y).buffer(width / 2) for x, y, width in gates)
        self.worker.spend(len(cuts) + 1)
        if cuts:
            self.counts["gate_cuts"] += len(cuts)
            line = line.difference(unary_union(cuts))
        return linemerge(_lines(line)) if not line.is_empty else line

    def quantized(self, metres, limits):
        scale = self.worker.scale
        cm = min(limits[1], max(limits[0], round(metres * 100 / scale)))
        return cm * scale / 100

    def emit(self, sources, kind, height, thickness, line, origin):
        made = 0
        for piece in _lines(line.simplify(LINE_TOLERANCE_M) if len(line.coords) > 2 else line):
            points = []
            for point in piece.coords:
                snapped = self.worker.snap(point)
                if not points or points[-1] != snapped: points.append(snapped)
            if len(points) < 2: continue
            for start in range(0, len(points) - 1, MAX_POINTS - 1):
                chunk = points[start:start + MAX_POINTS]
                if len(chunk) < 2: continue
                feature = dict(type="Feature", properties=dict(osm_source_id=min(sources), _city_sources=sorted(sources),
                    _city_barrier=dict(kind=kind, height_m=self.quantized(height * BARRIER_HEIGHT_FACTOR, HEIGHT_CM), thickness_m=self.quantized(thickness, THICKNESS_CM), origin=origin)), geometry=None)
                self.items.append((feature, LineString(chunk)))
                self.counts[origin + "_records"] += 1
                self.counts["points"] += len(chunk)
                self.kinds[kind] += 1
                made += 1
        return made

    def infer(self, worker):
        buildings = [(f, g) for f, g in worker.features if g.geom_type != "LineString" and not (f["properties"].get("osm_region")
                     or f["properties"].get("landuse") in ("forest", "orchard"))]
        building_tree = STRtree([g for f, g in buildings])
        explicit_tree = STRtree(self.explicit)
        for f, g in worker.features:
            p = f["properties"]
            site = p.get("_city_site")
            if g.geom_type == "LineString" or site not in INFERRED or not p.get("osm_region"): continue
            inside = [buildings[int(i)] for i in building_tree.query(g, predicate="intersects")]
            worker.spend(len(inside) + 1)
            if site == "residential":
                covered = sum(b.intersection(g).area for _, b in inside)
                tall = sum(1 for q, b in inside if g.contains(b.representative_point()) and (_building(q["properties"]) == "apartments"
                           or (_building(q["properties"]) in RESIDENTIAL + ("yes",) and _height(q["properties"]) >= APARTMENT_TALL_M)))
                if tall < APARTMENT_COUNT or g.area <= 0 or covered / g.area < COVERAGE: continue
            outline = p.get("_city_outline")
            if not outline: continue
            line = unary_union([LineString(ring) for ring in outline]).intersection(g.buffer(0.05))
            if line.is_empty: continue
            cuts = [b.buffer(BUILDING_GAP_M, join_style="mitre") for _, b in inside]
            cuts.extend(self.explicit[int(i)].buffer(EXPLICIT_WINS_M) for i in explicit_tree.query(line.buffer(EXPLICIT_WINS_M)))
            merged = self.gated(line, p.get("_city_gates", []), cuts)
            pieces = [piece for piece in _lines(merged) if piece.length >= MIN_PIECE_M]
            if not pieces:
                self.counts["inferred_sites_without_perimeter"] += 1
                continue
            kind, height, thickness = INFERRED[site]
            self.counts["inferred_sites"] += 1
            for piece in pieces:
                self.emit(sorted(set(worker.source_ids(f))), kind, height, thickness, piece, "inferred")
