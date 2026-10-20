"""Bounded offline OSM snapshot adapter; no private modules or source writes."""
import hashlib
from importlib.metadata import version, PackageNotFoundError
import re
from collections import Counter
# Highway classes for walking and cycling: no vehicle junctions, no width floor.
# Steps are imported by the city profile only (ground paint).
PEDESTRIAN = ("path", "footway", "cycleway", "pedestrian", "steps")
HIGHWAYS = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "road",
            "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "track", "path", "footway", "cycleway", "pedestrian")

from import_layer import MAX_INPUT, MAX_POINTS, INPUT_CEILING, soft_limit
from polygon_geometry import Budget, SpatialBudget, group_rings
from osm_review import Review, source_error

LICENSE = "ODbL-1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright"
MAX_ENTITIES = 250_000
MAX_REFS = 200_000
MAX_FEATURES = 20_000
CITY_STRUCTURE_REFS = 4_000_000  # City-mode warning threshold for structural incidence.
MAX_TAGS = 128  # Warn above.
TAG_CEILING = 1024  # Beyond this an entity carries a source-error marker.
TAG_TEXT = 512  # Tag keys/values longer than this mark the entity (output text bound).


def dependency():
    try:
        if version("osmium") != "4.3.1":
            raise ValueError("OSM requires osmium 4.3.1; install requirements-import.txt in the selected Python")
        import osmium
        return osmium
    except (ImportError, PackageNotFoundError) as exc:
        raise ValueError("OSM requires osmium 4.3.1; install requirements-import.txt in the selected Python") from exc


def category(tags):
    kinds = []
    if tags.get("highway"):
        kinds.append("road")
    if tags.get("building", "no") != "no" or "building:part" in tags:
        kinds.append("building")
    if tags.get("landuse") in ("forest", "orchard") or tags.get("natural") == "wood":
        kinds.append("zone")
    if len(kinds) > 1:
        raise ValueError("ambiguous OSM feature categories; prepare an explicit extract")
    if not kinds and (tags.get("landuse") or tags.get("leisure") in ("park", "nature_reserve") or tags.get("natural") in ("water", "wetland", "bare_rock", "scrub", "grassland") or tags.get("boundary") == "protected_area"):
        return "region"
    return kinds[0] if kinds else None


def region_properties(tags):
    landuse = tags.get("landuse") or {"wood":"forest", "water":"water"}.get(tags.get("natural"), tags.get("natural")) or tags.get("leisure", "unknown")
    protected = tags.get("boundary") == "protected_area" or tags.get("leisure") == "nature_reserve" or tags.get("access") in ("no", "private")
    return dict(landuse=landuse or "unknown", osm_region=True, protected=protected,
                region_tags={k: tags[k] for k in ("landuse", "natural", "leisure", "boundary", "access", "protect_class") if k in tags})


def metres(tags, name):
    raw = tags[name]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?: m)?", raw):
        raise ValueError(f"OSM {name}: only a positive decimal metre value is supported")
    value = float(raw.removesuffix(" m"))
    if not 0 < value <= 1000:
        raise ValueError(f"OSM {name}: expected 0 < metres <= 1000")
    return value


def vertical(tags):
    if any(tags.get(key, "no") not in ("no", "0") for key in ("bridge", "tunnel")) or tags.get("layer", "0") != "0":
        raise ValueError("OSM bridge/tunnel/nonzero layer requires explicit vertical geometry")
    if any(key in tags for key in ("building:part", "min_height", "building:min_level", "incline", "ele", "level")):
        raise ValueError("OSM unsupported vertical semantics")


def road_vertical(tags, references, node_tags):
    """Explicit EGM96 node heights; layer is ordering, never metres."""
    bridge, tunnel = tags.get("bridge", "no"), tags.get("tunnel", "no")
    if bridge not in ("no", "0", "yes") or tunnel not in ("no", "0", "yes") or bridge == tunnel == "yes":
        raise ValueError("OSM unsupported/ambiguous bridge or tunnel type")
    kind = "bridge" if bridge == "yes" else "tunnel" if tunnel == "yes" else "ground"
    if not re.fullmatch(r"-?[0-9]+", tags.get("layer", "0")) or not -5 <= int(tags.get("layer", "0")) <= 5:
        raise ValueError("OSM layer requires an integer from -5 to 5; it is not elevation")
    if kind == "ground" and int(tags.get("layer", "0")) != 0:
        raise ValueError("OSM nonzero ground layer requires explicit supported structure")
    forbidden = ("building:part", "min_height", "building:min_level", "incline", "ele", "level", "height", "covered", "location")
    if any(k in tags for k in forbidden) or any(k.startswith("ele:") for k in tags):
        raise ValueError("OSM unsupported vertical semantics on road")
    elevations = []
    for ref in references:
        tags_at_node = node_tags.get(ref, {})
        if any(k in tags_at_node for k in ("layer", "level", "incline", "bridge", "tunnel")) or any(k.startswith("ele:") for k in tags_at_node):
            raise ValueError("OSM unsupported road-node vertical semantics")
        if "ele" in tags_at_node:
            raw = tags_at_node["ele"]
            if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?(?: m)?", raw):
                raise ValueError("OSM node ele requires signed decimal metres (EGM96)")
            value = float(raw.removesuffix(" m"))
            if not -10000 <= value <= 10000:
                raise ValueError("OSM node elevation outside native range")
            elevations.append(value)
    if elevations and len(elevations) != len(references) or kind != "ground" and not elevations:
        raise ValueError("OSM explicit vertical geometry requires ele on every road node; no interpolation of missing heights")
    if not elevations:
        if "maxheight:physical" in tags:
            raise ValueError("OSM physical clearance requires an explicit supported tunnel")
        return {}
    result = dict(elevations_m=elevations, road_kind=kind, osm_node_refs=references,
                  osm_way_layer=int(tags.get("layer", "0")))
    if kind == "tunnel":
        if "maxheight:physical" not in tags:
            raise ValueError("OSM tunnel requires maxheight:physical; legal maxheight is not geometry")
        clearance = metres(tags, "maxheight:physical")
        if not 2 <= clearance <= 50:
            raise ValueError("OSM tunnel physical clearance requires 2..50 metres")
        result["clearance_m"] = clearance
    elif "maxheight:physical" in tags:
        raise ValueError("OSM physical clearance only supported on tunnel ways")
    return result


LEVEL_TAGS = ("bridge", "tunnel", "layer", "covered", "location", "maxheight:physical")


def is_structure(tags):
    return tags.get("bridge", "no") not in ("no", "0") or tags.get("tunnel", "no") not in ("no", "0") or tags.get("layer", "0") != "0"


def city_tags(tags):
    """City profile: a ground walking way's incline is its slope on the flat
    1:8 city, not a structure; steps must be ground stairs, not escalators."""
    if tags.get("highway") == "steps" and (is_structure(tags) or tags.get("conveying", "no") != "no"):
        raise ValueError("OSM city steps are ground paint; structural or conveying steps are unsupported")
    if tags.get("highway") in PEDESTRIAN and not is_structure(tags) and "incline" in tags:
        return {key: value for key, value in tags.items() if key != "incline"}
    return tags


def city_building_tags(tags, member=False):
    """City profile: a building above other features (positive layer, not a
    roof canopy or barrier) stands on the flat 1:8 ground. `member` lifts an
    untagged outline way of such a building relation too."""
    if ((member and "building" not in tags or tags.get("building", "no") not in ("no", "roof")) and "barrier" not in tags
            and re.fullmatch(r"[1-9][0-9]*", tags.get("layer", ""))):
        return {key: value for key, value in tags.items() if key != "layer"}
    return tags


def city_node_tags(tags):
    """City profile: an entrance's level is a building floor, not road height."""
    if "entrance" in tags and "level" in tags:
        return {key: value for key, value in tags.items() if key != "level"}
    return tags


CUT_STRUCTURE = "OSM city structure ends where an excluded way continued it; it is not estimated without that connection"


def level_structures(ways, nodes, node_tags):
    """City profile: structures without source heights that cross no other road.

    A bridge, tunnel or layered way meeting other roads only at shared nodes
    (a river bridge, culvert or building passage) is drawn at ground level on
    the flat 1:8 city. Ways crossing another road keep needing explicit heights.
    """
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    roads = [(identity, refs, tags) for identity, kind, refs, tags in ways
             if kind == "road" and len(refs) >= 2 and all(ref in nodes for ref in refs)]
    def structure(tags):
        return tags.get("bridge", "no") not in ("no", "0") or tags.get("tunnel", "no") not in ("no", "0") or tags.get("layer", "0") != "0"
    candidates = [i for i, (_, refs, tags) in enumerate(roads)
                  if structure(tags) and not any("ele" in node_tags.get(ref, {}) for ref in refs)]
    if not candidates:
        return set()
    lines = [LineString([nodes[ref] for ref in refs]) for _, refs, _ in roads]
    tree = STRtree(lines)
    result = set()
    for i in candidates:
        identity, refs, _ = roads[i]
        clear = True
        for j in tree.query(lines[i]):
            if j == i:
                continue
            meet = lines[i].intersection(lines[j])
            if meet.is_empty:
                continue
            shared = {tuple(nodes[ref]) for ref in set(refs).intersection(roads[j][1])}
            points = [meet] if meet.geom_type == "Point" else list(meet.geoms) if meet.geom_type == "MultiPoint" else None
            if points is None or any((point.x, point.y) not in shared for point in points):
                clear = False
                break
        if clear:
            result.add(identity)
    return result


DECK_M = 6.0  # Deck height per layer: 4.5 m road clearance plus the structure.
GRADE = 0.08
LEAD_M = 8.0  # Level lead at each ground anchor; native aprons stay on it.
SEPARATION_M = 5.0  # Real metres; ÷8 on the map.
TUNNEL_CLEARANCE_M = 4.5


def estimate_structures(ways, nodes, node_tags, level, cut_nodes=frozenset(), cut_chains=None, chain_of=None):
    """City profile: estimated heights for structures crossing other roads.

    A chain of bridge (or tunnel) ways joined end to end is lifted (or lowered)
    6 m per layer. Ramps of at most 8 % run over the chain and, where it is too
    short, over whole ground ways continuing it up to a junction or dead end,
    which become the same structure. Each anchor keeps an 8 m level lead. Chain
    ways have no side roads along them, and every crossing with another road
    keeps 5 m of separation; any other chain is left to the explicit-height rule.

    A chain whose crossings are all with excluded structures is drawn at
    ground level like a structure crossing nothing; one bending more than 60°
    at a vertex keeps needing source heights (native structure mouths overlap).
    A chain that cannot be estimated but crosses only open ground walking ways
    (city paint: no closed-road contact, no source heights, not a ramp of an
    estimated chain) is drawn at ground level too.

    `ways` holds only ways that can be imported. A chain that would get heights
    but ends at a dead end left by an excluded way (a source node in
    `cut_nodes`) is not estimated; its ways are added to `cut_chains`.

    Returns ({way: [(lon, lat, height_m, ref or None)]}, leveled ways): each
    estimated way's vertices in its own order, with unreferenced vertices added
    where the profile bends. `chain_of` receives each estimated way's chain key.
    """
    import math
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    roads = {identity: (refs, tags) for identity, kind, refs, tags in ways
             if kind == "road" and len(refs) >= 2 and all(ref in nodes for ref in refs)}
    if not roads:
        return {}, set()
    lat0 = math.radians(sum(nodes[refs[0]][1] for refs, _ in roads.values()) / len(roads))
    def metres(ref):
        lon, lat = nodes[ref]
        return lon * 111320 * math.cos(lat0), lat * 110540
    def layer_of(tags):
        if re.fullmatch(r"-?[0-9]+", tags.get("layer", "")): return int(tags["layer"])
        return 1 if tags.get("bridge", "no") not in ("no", "0") else -1 if tags.get("tunnel", "no") not in ("no", "0") else 0
    def structure(tags):
        return tags.get("bridge", "no") not in ("no", "0") or tags.get("tunnel", "no") not in ("no", "0") or tags.get("layer", "0") != "0"
    arms, ends = Counter(), {}
    for identity, (refs, _) in roads.items():
        for i, ref in enumerate(refs):
            arms[ref] += 1 if i in (0, len(refs) - 1) else 2
        for ref in (refs[0], refs[-1]):
            ends.setdefault(ref, []).append(identity)
    def plain(way):
        """No other road meets this way between its ends."""
        refs = roads[way][0]
        return refs[0] != refs[-1] and all(arms[ref] == 2 for ref in refs[1:-1])
    candidates = {identity for identity, (refs, tags) in roads.items()
                  if identity not in level and structure(tags) and layer_of(tags) != 0
                  and not any("ele" in node_tags.get(ref, {}) for ref in refs)}
    def beyond(path, at_end):
        way, flipped = path[-1] if at_end else path[0]
        refs = roads[way][0]
        node = (refs[0] if flipped else refs[-1]) if at_end else (refs[-1] if flipped else refs[0])
        others = [w for w in ends.get(node, []) if w != way]
        return node, (others[0] if arms[node] == 2 and len(others) == 1 else None)
    def attach(path, at_end, node, way):
        refs = roads[way][0]
        if at_end: path.append((way, refs[-1] == node))
        else: path.insert(0, (way, refs[0] == node))
    used, chains = set(), []
    for start in sorted(candidates):
        if start in used: continue
        layer = layer_of(roads[start][1])
        path = [(start, False)]
        used.add(start)
        for at_end in (True, False):
            while True:
                node, way = beyond(path, at_end)
                if way is None or way in used or way not in candidates or layer_of(roads[way][1]) != layer: break
                used.add(way)
                attach(path, at_end, node, way)
        chains.append((layer, path))
    lines = {identity: LineString([metres(ref) for ref in refs]) for identity, (refs, _) in roads.items()}
    order = sorted(lines)
    tree = STRtree([lines[i] for i in order])
    def crossings(way):
        """Plan crossings with other roads, not at shared source nodes."""
        refs = roads[way][0]
        for j in tree.query(lines[way]):
            other = order[j]
            if other == way: continue
            meet = lines[way].intersection(lines[other])
            if meet.is_empty: continue
            shared = {metres(ref) for ref in set(refs).intersection(roads[other][0])}
            points = [meet] if meet.geom_type == "Point" else list(meet.geoms) if meet.geom_type == "MultiPoint" else None
            if points is None:
                yield other, None  # Overlapping roads cannot be separated.
                continue
            for point in points:
                if (point.x, point.y) not in shared: yield other, point
    def vertices(path):
        out = []
        for way, flipped in path:
            refs = roads[way][0][::-1] if flipped else roads[way][0]
            out.extend(refs if not out else refs[1:])
        return out
    looped = {ref for refs, _ in roads.values() if refs[0] == refs[-1] for ref in refs}
    def drawn(other):
        return not structure(roads[other][1]) or other in level or other in candidates
    leveled = set()
    def sharp(refs):
        """Native structure bends need separated mouths: a turn of θ needs both
        neighbouring segments of at least 12 m · tan(θ/2) + 2 m (the widest
        floored 1:8 road), and no turn may exceed 60°."""
        for a, b, c in zip(refs, refs[1:], refs[2:]):
            (ax, ay), (bx, by), (cx, cy) = metres(a), metres(b), metres(c)
            u, v = (bx - ax, by - ay), (cx - bx, cy - by)
            lu, lv = math.hypot(*u), math.hypot(*v)
            if not lu or not lv: return True
            turn = math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv))))
            if turn > math.pi / 3 or min(lu, lv) < 12.0 * math.tan(turn / 2) + 2.0 and turn > math.radians(2): return True
        return False
    absorbed = set()
    result, cut_keys = {}, set()
    for layer, path in chains:
        if not all(plain(way) for way, _ in path): continue
        if not any(drawn(other) for way, _ in path for other, _ in crossings(way)):
            leveled.update(way for way, _ in path)
            continue
        height = DECK_M * abs(layer)
        core = LineString([metres(ref) for ref in vertices(path)])
        cut = [core.project(point) for way, _ in path for _, point in crossings(way) if point is not None]
        ramp = LEAD_M + height / GRADE + 10.0  # Full height just before the first crossing.
        for at_end, need in ((False, ramp - min(cut, default=ramp)), (True, ramp - (core.length - max(cut, default=0.0)))):
            length = 0.0
            while length < need:
                node, way = beyond(path, at_end)
                if way is None or way in absorbed or way in candidates or way in used or not plain(way) or structure(roads[way][1]) and way not in level:
                    break
                absorbed.add(way)
                attach(path, at_end, node, way)
                length += lines[way].length
        refs = vertices(path)
        # Ways meeting a closed road join the explicit source-node loop graph.
        if len(set(refs)) != len(refs) or not looped.isdisjoint(refs) or sharp(refs): continue
        line = LineString([metres(ref) for ref in refs])
        total = line.length
        def profile(d, total=total, height=height, layer=layer):
            rise = min(GRADE * max(0.0, d - LEAD_M), GRADE * max(0.0, total - d - LEAD_M))
            return math.copysign(min(height, rise), layer) if rise else 0.0
        result[path[0][0]] = (path, line, profile)
        if any(end in cut_nodes and arms[end] == 1 for end in (refs[0], refs[-1])):
            cut_keys.add(path[0][0])
    # Separation at every plan crossing (not at a shared node) with another road.
    changed = True
    while changed:
        changed = False
        owner = {way: key for key, (path, _, _) in result.items() for way, _ in path}
        for key in sorted(result):
            path, line, profile = result[key]
            ok, checked = True, 0
            for way, _ in path:
                for other, point in crossings(way):
                    if owner.get(other) == key: continue
                    if other not in owner and structure(roads[other][1]) and other not in level and other not in leveled:
                        continue  # An unestimated structure is excluded, not drawn.
                    checked += 1
                    if point is None:
                        ok = False
                        break
                    theirs = 0.0
                    if other in owner:
                        _, other_line, other_profile = result[owner[other]]
                        theirs = other_profile(other_line.project(point))
                    if abs(profile(line.project(point)) - theirs) < SEPARATION_M:
                        ok = False
                        break
                if not ok: break
            if not ok or not checked or key in cut_keys:
                # Crossing nothing drawn, the chain lies on the ground instead;
                # a cut chain's profile would end where the excluded way was.
                if ok and not checked: leveled.update(way for way, _ in path if way in candidates)
                elif ok and cut_chains is not None: cut_chains.update(way for way, _ in path if way in candidates)
                del result[key]
                changed = True
                break
    estimated = {}
    for path, line, profile in result.values():
        total = line.length
        top = LEAD_M + abs(profile(total / 2)) / GRADE
        # A peak below full height is one bend, not two nearly coincident ones.
        tops = (top, total - top) if total - 2 * top >= 1.0 else ((total / 2),)
        bends = sorted({d for d in (LEAD_M, *tops, total - LEAD_M) if 0 < d < total})
        offset = 0.0
        for way, flipped in path:
            refs = roads[way][0][::-1] if flipped else roads[way][0]
            points = []
            for a, b in zip(refs, refs[1:]):
                pa, pb = metres(a), metres(b)
                step = math.dist(pa, pb)
                points.append((nodes[a][0], nodes[a][1], profile(offset), a))
                for d in bends:
                    if offset + 0.5 < d < offset + step - 0.5:
                        t = (d - offset) / step
                        points.append((nodes[a][0] + (nodes[b][0] - nodes[a][0]) * t, nodes[a][1] + (nodes[b][1] - nodes[a][1]) * t, profile(d), None))
                offset += step
            points.append((nodes[refs[-1]][0], nodes[refs[-1]][1], profile(offset), refs[-1]))
            estimated[way] = (points[::-1] if flipped else points, "bridge" if profile(total / 2) > 0 else "tunnel")
            if chain_of is not None: chain_of[way] = path[0][0]
    ramps = {way for path, _, _ in result.values() for way, _ in path if way not in candidates}
    def paint(other):
        refs, tags = roads[other]
        return (tags.get("highway") in PEDESTRIAN and not structure(tags) and other not in ramps
                and looped.isdisjoint(refs) and not any("ele" in node_tags.get(ref, {}) for ref in refs))
    for _, path in chains:
        members = [way for way, _ in path if way in candidates]
        if any(way in estimated or way in leveled for way in members): continue
        hits = [other for way in members for other, _ in crossings(way) if drawn(other) and other not in members]
        if hits and all(paint(other) for other in hits):
            leveled.update(members)
            if cut_chains is not None: cut_chains.difference_update(members)
    return estimated, leveled


def closed_road(properties):
    return properties.get("osm_closed_ground") or properties.get("osm_closed_structure")


def structure_connections(roads, source_uses, ref_limit=None, join_limit=None):
    """Prove explicit source incidence before crop, then let native test geometry.

    Interior source vertices contribute two directed arms. A star links each
    junction in linear space; dense input never allocates a peer cross-product.
    """
    ref_limit = MAX_REFS if ref_limit is None else ref_limit
    join_limit = MAX_FEATURES if join_limit is None else join_limit
    ground = {ref for f in roads if f["properties"]["road_kind"] == "ground" and "elevations_m" in f["properties"]
              for ref in f["properties"]["osm_node_refs"]}
    structures = {f["properties"]["osm_way_id"]: f["properties"] for f in roads
                  if f["properties"]["road_kind"] != "ground"}
    incident = {}
    for way, p in structures.items():
        for index, ref in enumerate(p["osm_node_refs"][:-1] if closed_road(p) else p["osm_node_refs"]):
            incident.setdefault(ref, []).append((way, index))
    links, joins = {way: [] for way in structures}, []
    total_arms = 0
    for ref, uses in sorted(incident.items()):
        if ref in ground: continue
        if len(uses) != source_uses[ref]:
            raise ValueError("OSM structural junction requires every incident highway's explicit height profile")
        arms = []
        for way, index in uses:
            p = structures[way]
            for end, present in (("to", index > 0 or closed_road(p)), ("from", index < len(p["osm_node_refs"])-1)):
                if present:
                    if len(arms) >= 32:
                        raise ValueError("OSM structural junction exceeds 32 native arms")
                    arms.append(dict(source_way=str(way), end=end, kind=p["road_kind"],
                        clearance_cm=round(p["clearance_m"]*100) if p["road_kind"] == "tunnel" else None))
        if len(arms) < 2:
            raise ValueError("OSM structure endpoints require explicit-height ground connections or explicit structural peers; missing approaches are unsupported")
        if len(uses) == 1: continue  # Ordinary authored bend, not a graph junction.
        total_arms += len(arms)
        if total_arms > ref_limit:
            soft_limit("osm_structure_arms", total_arms, ref_limit, "OSM structural source incidence budget exceeded")
        if len(joins) >= join_limit:
            soft_limit("osm_structure_joins", len(joins) + 1, join_limit, "OSM structural junction budget exceeded")
        if len({a["clearance_cm"] for a in arms if a["kind"] == "tunnel"}) > 1:
            raise ValueError("OSM joined tunnel clearances must agree after centimetre quantization")
        ways = sorted(way for way, _ in uses)
        for peer in ways[1:]:
            links[ways[0]].append(peer)
            links[peer].append(ways[0])
        kinds = {a["kind"] for a in arms}
        join = dict(ref=str(ref), kind=next(iter(kinds)) if len(kinds) == 1 else "mixed", source_ways=list(map(str, ways)))
        join["source_arms"] = sorted(arms, key=lambda a: (int(a["source_way"]), a["end"]))
        joins.append(join)
    visited = set()
    for first in structures:
        if first in visited: continue
        pending, grounded = [first], set()
        visited.add(first)
        while pending:
            way = pending.pop()
            refs = structures[way]["osm_node_refs"]
            grounded.update(ref for ref in refs if ref in ground)
            for peer in links[way]:
                if peer not in visited:
                    visited.add(peer)
                    pending.append(peer)
        if len(grounded) < 2:
            raise ValueError("OSM structure component requires at least two distinct explicit ground connections; unanchored cycles are unsupported")
    return joins


def split_vertical_roads(features, source_uses=None, connections=None, feature_limit=None, review=None, ref_limit=None):
    """Join only shared source node IDs; split explicit roads at graph junctions."""
    feature_limit = MAX_FEATURES if feature_limit is None else feature_limit
    roads = [f for f in features if "osm_node_refs" in f["properties"]]
    rejected = set()
    for f in roads:
        refs = f["properties"]["osm_node_refs"]
        unique = refs[:-1] if closed_road(f["properties"]) else refs
        if len(set(unique)) != len(unique):
            message = "OSM explicit road repeats nodes; prepare unambiguous segments"
            if review is None: raise ValueError(message)
            review.reject(f["properties"]["osm_source_id"], message)
            rejected.add(f["properties"]["osm_source_id"])
    features = [f for f in features if f["properties"].get("osm_source_id") not in rejected]
    roads = [f for f in features if "osm_node_refs" in f["properties"]]
    uses = Counter(ref for f in roads for ref in set(f["properties"]["osm_node_refs"]))
    joins = structure_connections(roads, uses if source_uses is None else source_uses, ref_limit, max(feature_limit, MAX_FEATURES))
    if connections is not None: connections.extend(joins)
    arms = Counter()
    for f in roads:
        p = f["properties"]
        for i, ref in enumerate(p["osm_node_refs"]):
            arms[ref] += int(i > 0) + int(i < len(p["osm_node_refs"])-1)
    if any(arms[ref] > 32 for f in roads if "osm_loop_range" in f["properties"] for ref in f["properties"]["osm_node_refs"]):
        raise ValueError("OSM loop graph exceeds 32 native arms")
    output = []
    for feature in features:
        p = feature["properties"]
        if "osm_node_refs" not in p:
            output.append(feature)
            continue
        refs = p["osm_node_refs"]
        cuts = [0] + [i for i in range(1, len(refs)-1) if closed_road(p) or uses[refs[i]] > 1] + [len(refs)-1]
        for a,b in zip(cuts,cuts[1:]):
            if len(output) >= feature_limit:
                soft_limit("osm_split_features", len(output) + 1, feature_limit, "OSM split feature budget exceeded")
            properties = dict(p, osm_node_refs=refs[a:b+1])
            if "elevations_m" in p: properties["elevations_m"] = p["elevations_m"][a:b+1]
            if "osm_loop_range" in p: properties["osm_loop_range"] = [a,b]
            output.append(dict(type="Feature", properties=properties, geometry=dict(type="LineString", coordinates=feature["geometry"]["coordinates"][a:b+1])))
    return output


def canonical_ring(ring):
    values = ring[:-1]
    smallest = values.index(min(values))
    forward = values[smallest:] + values[:smallest]
    reverse = [forward[0]] + list(reversed(forward[1:]))
    result = min(forward, reverse)
    return result + [result[0]]


def assemble(segments):
    """Join complete way endpoints in either direction, never infer missing edges."""
    endpoints, remaining, rings = {}, {}, []
    for identity, refs in segments:
        if len(refs) < 2 or len(set(refs[:-1] if refs[0] == refs[-1] else refs)) != len(refs)-(refs[0] == refs[-1]):
            raise ValueError("OSM multipolygon short/repeated way nodes")
        if refs[0] == refs[-1]:
            if len(refs) < 4:
                raise ValueError("OSM multipolygon short closed ring")
            rings.append(canonical_ring(refs))
            continue
        remaining[identity] = refs
        for endpoint in (refs[0], refs[-1]):
            endpoints.setdefault(endpoint, []).append(identity)
    if any(len(ways) != 2 for ways in endpoints.values()):
        raise ValueError("OSM multipolygon incomplete or ambiguous endpoint joins")
    for identity in sorted(remaining):
        if identity not in remaining:
            continue
        ring = remaining.pop(identity)[:]
        while ring[-1] != ring[0]:
            following = [key for key in endpoints[ring[-1]] if key in remaining]
            if len(following) != 1:
                raise ValueError("OSM multipolygon incomplete or ambiguous ring")
            refs = remaining.pop(following[0])
            ring.extend((refs if refs[0] == ring[-1] else refs[::-1])[1:])
        if len(set(ring[:-1])) != len(ring)-1:
            raise ValueError("OSM multipolygon repeats a ring node")
        rings.append(canonical_ring(ring))
    return sorted(rings)


def relation_features(relations, all_ways, nodes, blocked_members, counts, budget):
    features, consumed = [], set()
    semantic = {"building", "building:part", "height", "landuse", "natural", "highway", "width", "surface"}
    for identity, kind, members, tags in sorted(relations):
        vertical(tags)
        selected = {"outer": [], "inner": []}
        local = set()
        for member_type, ref, role in members:
            if member_type != "w" or role not in selected or ref in local or ref in consumed or ref in blocked_members:
                raise ValueError("OSM multipolygon requires unique explicit outer/inner ways without shared area ownership")
            if ref not in all_ways:
                raise ValueError("OSM multipolygon missing member way; use a complete extract")
            refs, member_tags = all_ways[ref]
            vertical(member_tags)
            if any(key in member_tags and member_tags[key] != tags.get(key) for key in semantic) or (role == "inner" and category(member_tags)):
                raise ValueError("OSM multipolygon member feature tags conflict; prepare explicit relation geometry")
            if any(node not in nodes for node in refs):
                raise ValueError("OSM multipolygon missing referenced node; use a complete extract")
            local.add(ref)
            selected[role].append((ref, refs))
        outers = [[nodes[n] for n in ring] for ring in assemble(selected["outer"])]
        inners = [[nodes[n] for n in ring] for ring in assemble(selected["inner"])]
        polygons = group_rings(outers, inners, budget)
        properties = {}
        if kind == "building":
            if "height" in tags: properties["height_m"] = metres(tags, "height")
            if tags["building"] != "yes": properties["usage"] = tags["building"]
        else:
            properties.update(region_properties(tags))
        properties["osm_source_id"] = "relation/" + str(identity)
        features.append(dict(type="Feature", properties=properties, geometry=dict(type="MultiPolygon", coordinates=polygons)))
        consumed.update(local)
        counts["assembled_relations"] += 1
        counts["outer_rings"] += len(outers)
        counts["inner_rings"] += len(inners)
    counts["member_ways"] += len(consumed)
    return features, consumed


def parse(raw, input_format, supplement=None, city=False):
    """Capture scalars only: osmium entities expire at the next iteration.

    Bounds include ignored entities/references, so filtering cannot evade admission.
    No implicit libosmium location/area cache or unbounded sparse ID array is used.
    """
    if not raw or len(raw) > INPUT_CEILING or input_format not in ("pbf", "osm"):
        raise ValueError("expected a nonempty OSM PBF/XML snapshot up to 256 MiB")
    if len(raw) > MAX_INPUT:
        soft_limit("input_bytes", len(raw), MAX_INPUT, "OSM snapshot exceeds 32 MiB; PBF streaming with a bbox uses less memory")
    if input_format == "osm":
        xml = raw.decode("utf-8-sig")
        if "\x00" in xml or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper() or "<osmChange" in xml:
            raise ValueError("OSM XML must be UTF-8 without entities, DTDs or change records")
    osmium = dependency()
    nodes, ways, seen, area_members = {}, [], set(), set()
    node_tags = {}
    all_ways, relations = {}, []
    counts = dict(nodes=0, ways=0, relations=0, ignored_ways=0, ignored_relations=0, tagged_nodes=0, assembled_relations=0, outer_rings=0, inner_rings=0, member_ways=0)
    refs = 0
    try:
        processor = osmium.FileProcessor(osmium.io.FileBuffer(raw, input_format))
        if processor.header.has_multiple_object_versions:
            raise ValueError("OSM history input is unsupported; use a current snapshot")
        for entity in processor:
            kind = entity.type_str()
            identity = (kind, entity.id)
            if identity in seen or entity.id <= 0 or not entity.visible:
                raise ValueError("OSM duplicate/history ID or deleted object")
            if len(seen) >= MAX_ENTITIES:
                soft_limit("osm_entities", len(seen) + 1, MAX_ENTITIES, "OSM entity budget exceeded")
            seen.add(identity)
            tag_count = len(entity.tags)
            if tag_count > MAX_TAGS:
                soft_limit("osm_tags", tag_count, MAX_TAGS, "OSM object has many source tags")
            tags, failure = {}, "more than 1024 source tags are unsupported" if tag_count > TAG_CEILING else ""
            for tag in entity.tags:
                if tag.k in tags:
                    raise ValueError("OSM duplicate tag")
                if len(tag.k) > TAG_TEXT or len(tag.v) > TAG_TEXT:
                    failure = "oversized source tag"
                elif len(tags) < TAG_CEILING:
                    tags[tag.k] = tag.v
            if failure:
                # As in PBF streaming: geometry using this object rejects (or is
                # reviewed); an unselected label no longer refuses the import.
                keys = {"type", "highway", "building", "building:part", "landuse", "natural", "leisure", "boundary", "bridge", "tunnel"}
                tags = {k: v[:TAG_TEXT] for k, v in tags.items() if k in keys}
                tags["_source_error"] = f"{kind}/{entity.id}: {failure}"
            if kind == "n":
                counts["nodes"] += 1
                counts["tagged_nodes"] += bool(tags)
                if not entity.location.valid():
                    raise ValueError("OSM invalid location")
                if len(nodes) >= MAX_POINTS:
                    soft_limit("osm_nodes", len(nodes) + 1, MAX_POINTS, "OSM node budget exceeded")
                nodes[entity.id] = [entity.lon, entity.lat]
                if tags: node_tags[entity.id] = tags
            elif kind == "w":
                counts["ways"] += 1
                refs += len(entity.nodes)
                if refs > MAX_REFS:
                    soft_limit("osm_references", refs, MAX_REFS, "OSM reference budget exceeded")
                all_ways[entity.id] = ([n.ref for n in entity.nodes], tags)
                selected = category(tags)
                if selected:
                    if len(ways) + len(relations) >= MAX_FEATURES:
                        soft_limit("osm_features", len(ways) + len(relations) + 1, MAX_FEATURES, "OSM selected feature budget exceeded")
                    ways.append((entity.id, selected, [n.ref for n in entity.nodes], tags))
                else:
                    counts["ignored_ways"] += 1
            elif kind == "r":
                counts["relations"] += 1
                refs += len(entity.members)
                if refs > MAX_REFS:
                    soft_limit("osm_references", refs, MAX_REFS, "OSM reference budget exceeded")
                selected = category(tags)
                if selected:
                    if (tags.get("type") != "multipolygon" and not (selected=="region" and tags.get("type")=="boundary")) or selected == "road":
                        raise ValueError("OSM selected relation requires an area multipolygon or protected boundary")
                    if len(ways) + len(relations) >= MAX_FEATURES:
                        soft_limit("osm_features", len(ways) + len(relations) + 1, MAX_FEATURES, "OSM selected feature budget exceeded")
                    relations.append((entity.id, selected, [(m.type, m.ref, m.role) for m in entity.members], tags))
                else:
                    if tags.get("type") in ("multipolygon", "boundary"):
                        area_members.update(m.ref for m in entity.members if m.type == "w")
                    counts["ignored_relations"] += 1
            else:
                raise ValueError("unsupported OSM entity")
    except RuntimeError as exc:
        raise ValueError("invalid OSM snapshot: " + str(exc)[:300]) from exc
    return build_features(nodes, node_tags, ways, all_ways, relations, area_members, counts,
                          supplement, hashlib.sha256(raw).hexdigest() if supplement is not None else None, city=city)


def way_feature(identity, kind, references, tags, nodes, node_tags, area_members, topology, city=False):
    if identity in area_members:
        raise ValueError("selected OSM way belongs to an area relation; no silent holes/flattening")
    if any(ref not in nodes for ref in references):
        raise ValueError(f"OSM way {identity}: missing referenced node; use a complete extract")
    source_error(tags)
    for ref in references: source_error(node_tags.get(ref, {}))
    if kind != "road": vertical(tags)
    points = [nodes[ref] for ref in references]
    properties = {}
    if kind == "road":
        if tags["highway"] not in HIGHWAYS + (("steps",) if city else ()) or tags.get("area", "no") != "no":
            raise ValueError(f"OSM way {identity}: unsupported highway/area profile")
        if len(references) < 2:
            raise ValueError(f"OSM way {identity}: short road")
        if any(nodes[a] == nodes[b] for a,b in zip(references, references[1:])):
            raise ValueError("road has a zero-length source segment")
        properties.update(road_vertical(tags, references, node_tags))
        if references[0] == references[-1]:
            if len(references) < 4 or len(set(references[:-1])) != len(references)-1:
                raise ValueError(f"OSM way {identity}: closed road requires at least three distinct nodes without repeated interiors")
            group_rings([points], [], topology)  # Simple ring; never repair a crossing or backtrack.
            properties["osm_closed_ground" if properties.get("road_kind", "ground") == "ground" else "osm_closed_structure"] = True
        if "osm_node_refs" in properties: properties["osm_way_id"] = identity
        if "width" in tags: properties["width_m"] = metres(tags, "width")
        if "surface" in tags: properties["surface"] = tags["surface"]
        geometry = dict(type="LineString", coordinates=points)
    else:
        if len(references) < 4 or references[0] != references[-1]:
            raise ValueError(f"OSM way {identity}: polygon must be a closed way")
        if kind == "building":
            if "height" in tags: properties["height_m"] = metres(tags, "height")
            if tags["building"] != "yes": properties["usage"] = tags["building"]
        else:
            properties.update(region_properties(tags))
        geometry = dict(type="Polygon", coordinates=[points])
    # Temporary source identity for selecting loop incidence, removed from
    # ordinary unconnected ground roads below to preserve their old contract.
    if kind == "road": properties["osm_source_way"] = identity
    properties["osm_source_id"] = "way/" + str(identity)
    return dict(type="Feature", properties=properties, geometry=geometry)


def build_features(nodes, node_tags, ways, all_ways, relations, area_members, counts, supplement=None, source_sha256=None, review=None, *, feature_limit=None, city=False):
    """Normalize a complete bounded selection from either snapshot reader."""
    if supplement is not None:
        node_tags = supplement.apply(nodes, node_tags, ways, source_sha256)
    review = review or Review()
    feature_limit = MAX_FEATURES if feature_limit is None else feature_limit
    topology = SpatialBudget() if city else Budget()
    layered = set()
    if city:
        node_tags = {ref: city_node_tags(tags) for ref, tags in node_tags.items()}
        lifted = {identity: city_building_tags(tags) for identity, (_, tags) in all_ways.items()}
        layered = {"way/" + str(identity) for identity, (_, tags) in all_ways.items() if lifted[identity] is not tags}
        all_ways = {identity: (refs, lifted[identity]) for identity, (refs, _) in all_ways.items()}
        ways = [(identity, kind, refs, lifted.get(identity, tags)) for identity, kind, refs, tags in ways]
        lifted_relations = []
        for identity, kind, members, tags in relations:
            raised = city_building_tags(tags) if kind == "building" else tags
            if kind == "building" and raised.get("building") != "roof":
                for kind_, ref, _ in members:
                    if kind_ != "w" or ref not in all_ways: continue
                    outline = city_building_tags(all_ways[ref][1], member=True)
                    if outline is not all_ways[ref][1]:
                        all_ways[ref] = (all_ways[ref][0], outline)
                        layered.add("way/" + str(ref))
            if kind == "building" and (raised is not tags or any("way/" + str(ref) in layered for kind_, ref, _ in members if kind_ == "w")):
                layered.add("relation/" + str(identity))
            lifted_relations.append((identity, kind, members, raised))
        relations = lifted_relations
    assembled, consumed = [], set()
    for relation in sorted(relations):
        try:
            source_error(relation[3])
            for member_type, ref, _role in relation[2]:
                if member_type == "w" and ref in all_ways:
                    source_error(all_ways[ref][1])
            parts, members = relation_features([relation], all_ways, nodes, area_members | consumed, counts, topology)
            assembled.extend(parts)
            consumed.update(members)
        except ValueError as exc:
            review.reject("relation/" + str(relation[0]), exc)
            # Failed area members never escape as flattened standalone polygons.
            for member_type, ref, _role in relation[2]:
                if member_type == "w":
                    consumed.add(ref)
                    review.reject("way/" + str(ref), "Member of excluded relation/" + str(relation[0]))
    supported_ids = {way[0] for way in ways}
    counts["ignored_ways"] -= sum(ref not in supported_ids for ref in consumed if ref in all_ways)
    features = []
    # City structures are estimated over importable roads only: a chain must
    # not ramp through a way that is excluded anyway (structures without their
    # height tags, as if estimated), nor through a relation member.
    absent = {}
    if city:
        probe = SpatialBudget()
        for identity, kind, references, tags in ways:
            if kind != "road": continue
            if identity in consumed:
                absent[identity] = None
                continue
            try:
                probed = city_tags(tags)
                if is_structure(tags):
                    probed = {key: value for key, value in probed.items() if key not in LEVEL_TAGS}
                way_feature(identity, kind, references, probed, nodes, node_tags, area_members, probe, city=True)
            except ValueError as exc:
                absent[identity] = exc
    present = [way for way in ways if way[0] not in absent]
    cut_nodes = {ref for identity, _, references, _ in ways if identity in absent for ref in references}
    cut_chains, chain_of = set(), {}
    level = level_structures(present, nodes, node_tags) if city else set()
    estimated, leveled = estimate_structures(present, nodes, node_tags, level, cut_nodes, cut_chains, chain_of) if city else ({}, set())
    level |= leveled
    for identity, kind, references, tags in sorted(ways):
        if identity in consumed:
            continue
        try:
            if absent.get(identity) is not None:
                raise absent[identity]
            if identity in cut_chains:
                raise ValueError(CUT_STRUCTURE)
            if city and kind == "road":
                tags = city_tags(tags)
            if identity in level or identity in estimated:
                tags = {key: value for key, value in tags.items() if key not in LEVEL_TAGS}
            features.append(way_feature(identity, kind, references, tags, nodes, node_tags, area_members, topology, city=city))
            if identity in level:
                features[-1]["properties"]["_city_level_structure"] = True
            if "way/" + str(identity) in layered and kind == "building":
                features[-1]["properties"]["_city_layer_building"] = True
            if identity in estimated:
                points, structure = estimated[identity]
                # Profile bends add unreferenced vertices; chain ways have no
                # side roads, so later source-junction splits never cut them.
                feature = features[-1]
                feature["geometry"]["coordinates"] = [[x, y] for x, y, _, _ in points]
                feature["properties"].update(_city_estimated_m=[round(h, 2) for _, _, h, _ in points], _city_estimated_kind=structure,
                    _city_estimated_refs=[ref for _, _, _, ref in points], _city_ends=[str(references[0]), str(references[-1])],
                    _city_estimated_chain=chain_of[identity])
                if structure == "tunnel": feature["properties"]["_city_estimated_clearance_m"] = TUNNEL_CLEARANCE_M
        except ValueError as exc:
            review.reject("way/" + str(identity), exc)
    loop_refs = {ref for f in features if closed_road(f["properties"])
                 for ref in all_ways[f["properties"]["osm_source_way"]][0]}
    loop_sources = []
    for f in features:
        p = f["properties"]
        identity = p.pop("osm_source_way", None)
        if identity is None: continue
        refs = all_ways[identity][0]
        if not loop_refs.intersection(refs): continue
        if any(nodes[a] == nodes[b] for a,b in zip(refs, refs[1:])):
            raise ValueError("OSM loop graph has a zero-length source segment")
        p.update(osm_node_refs=refs, osm_way_id=identity, road_kind=p.get("road_kind", "ground"), osm_loop_range=[0,len(refs)-1])
        loop_sources.append(dict(way=str(identity), refs=list(map(str,refs)), closed=bool(closed_road(p)),
            kind=p["road_kind"], clearance_cm=round(p["clearance_m"]*100) if p["road_kind"] == "tunnel" else None))
    connections = []
    features = split_vertical_roads(features,
        Counter(ref for _, kind, refs, _ in ways if kind == "road" for ref in set(refs)), connections, feature_limit, review,
        CITY_STRUCTURE_REFS if city else MAX_REFS)
    retained_ways = {f["properties"].get("osm_way_id") for f in features}
    loop_sources = [s for s in loop_sources if int(s["way"]) in retained_ways]
    counts["explicit_height_roads"] = sum("elevations_m" in f["properties"] for f in features)
    counts["bridge_segments"] = sum(f["properties"].get("road_kind") == "bridge" for f in features)
    counts["tunnel_segments"] = sum(f["properties"].get("road_kind") == "tunnel" for f in features)
    for feature in assembled:
        if feature["properties"]["osm_source_id"] in layered: feature["properties"]["_city_layer_building"] = True
    features.extend(assembled)
    if len(features) > feature_limit:
        soft_limit("osm_features", len(features), feature_limit, "OSM selected feature budget exceeded")
    if not features:
        raise ValueError("OSM extract contains no supported road/building/forest/orchard features")
    counts["structure_continuations"] = len(connections)
    collection = dict(type="FeatureCollection", features=features)
    relation_tags = {identity: tags for identity, kind, members, tags in relations}
    for feature in features:
        p = feature["properties"]
        kind, identity = p["osm_source_id"].split("/")
        refs, tags = all_ways[int(identity)] if kind == "way" else ([], relation_tags[int(identity)])
        p["_city_name"] = tags.get("name", "")
        p["_city_landmark"] = any(key in tags for key in ("historic", "tourism", "amenity"))
        if feature["geometry"]["type"] == "LineString":
            # Do not merge roads across semantic changes omitted by the
            # legacy display adapter (oneway, access, name, classification).
            # Loop and structural roads keep the class too (pedestrian handling).
            p["_city_road_tags"] = {key: tags[key] for key in ("highway", "name", "ref", "oneway", "access", "vehicle", "motor_vehicle", "lanes", "junction") if key in tags}
            if "osm_node_refs" not in p: p["_city_refs"] = p.pop("_city_estimated_refs", refs)
    # Preserve ordinary source junctions between vehicle roads without assigning an
    # elevation datum. Split at shared original IDs before simplification/merging
    # and crop. Pedestrian ways keep independent ends, as dense path networks would
    # otherwise multiply junctions beyond what a city cell can generate.
    def vehicle(feature):
        return feature["properties"].get("_city_road_tags", {}).get("highway") not in PEDESTRIAN
    uses = Counter(ref for f in features if vehicle(f) for ref in set(f["properties"].get("_city_refs", [])))
    connected_features = []
    for feature in features:
        p = feature["properties"]
        refs = p.get("_city_refs")
        if not refs or not vehicle(feature):
            connected_features.append(feature)
            continue
        cuts = [0] + [i for i in range(1,len(refs)-1) if refs[i] is not None and uses[refs[i]] > 1] + [len(refs)-1]
        for a,b in zip(cuts,cuts[1:]):
            props = dict(p, _city_refs=refs[a:b+1], _city_ends=[str(refs[a]),str(refs[b])])
            if "_city_estimated_m" in p: props["_city_estimated_m"] = p["_city_estimated_m"][a:b+1]
            connected_features.append(dict(type="Feature", properties=props,
                geometry=dict(type="LineString",coordinates=feature["geometry"]["coordinates"][a:b+1])))
            if len(connected_features)>feature_limit: soft_limit("osm_split_features", len(connected_features), feature_limit, "OSM split feature budget exceeded")
    collection["features"] = connected_features
    if connections: collection["osm_connections"] = connections
    if loop_sources:
        structural = any(s["kind"] != "ground" for s in loop_sources)
        counts["closed_ground_ways"] = sum(s["closed"] and s["kind"] == "ground" for s in loop_sources)
        if structural:
            counts["closed_structural_ways"] = sum(s["closed"] and s["kind"] != "ground" for s in loop_sources)
        collection["osm_ground_loops"] = dict(profile="source-node-segments-v1", sources=loop_sources)
    else:
        counts["closed_ground_ways"] = 0
    return collection, counts


def finish(layer, counts):
    layer.adapter = "osm-extract-v1"
    previous = layer.warnings
    layer.warnings = []
    layer.warning("OSM snapshot via osmium 4.3.1; © OpenStreetMap contributors; ODbL-1.0; https://www.openstreetmap.org/copyright")
    layer.warning("OSM input counts: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    layer.warning("Selected ways and explicit multipolygons are imported; POIs, other ways/relations and other tags are omitted. No routing/access/oneway semantics.")
    layer.warning("Ground elevation/base, missing width/height/surface, vegetation and materials are estimates; building levels/roof tags are not interpreted.")
    if "closed_structural_ways" in counts:
        layer.warning("Closed roads and their incident ways split by original source node IDs. Structural loops and direct bridge/tunnel connections require complete explicit heights and two distinct ground anchors; no inferred ramps. Source kind/clearance and crop cuts remain reviewable. At most 16 native validation cells per adoption.")
    elif counts.get("closed_ground_ways"):
        layer.warning("Closed ground roads split at every original node; incident ground approaches join by source node ID only. Crop cuts stay separate. No routing/access/oneway or roundabout priority semantics. At most 16 native validation cells per adoption.")
    if counts.get("explicit_height_roads"):
        vertical = layer.coordinates.get("vertical")
        if vertical is None:
            layer.warning("Explicit OSM node ele metres use EGM96 sea level as map Y=0; no vertical offset/datum conversion or terrain alignment. Verify against your map before adoption.")
        else:
            layer.warning(f"Explicit OSM EGM96 heights → {vertical['target_crs']} minus {vertical['vertical_zero_m']} m at local zero; {vertical['method']}. Convert original vertices before crop, then linearly grade target heights. No terrain fitting. Local authored/estimated heights and physical clearance are unchanged; source and correction accuracy are separate.")
        layer.warning("Explicit-height roads join only shared OSM node IDs. Structural components need at least two distinct explicit ground connections before crop. Branches, interior joins and bridge/tunnel transitions use at most 32 native arms with matching tunnel clearance. Native apron/terrain checks still apply. Layer is ordering only. Bridges add no invented supports; tunnel ceiling uses maxheight:physical, not legal maxheight.")
        if any("source_arms" in join for join in layer.coordinates.get("osm_connections", {}).get("joins", [])):
            layer.warning("Structural junction floor fans use authored mouths and the source node. Native road-ID ownership assigns each fan face its material/kind; only tunnel-owned sectors have ceilings and outer side walls. Mixed portal boundaries follow those sectors, not an inferred portal plane. Cropping rebuilds the retained junction; missing source arms remain in review metadata. Cross-sections are estimates; inspect the generated map.")
        layer.warning("Only bridge=yes/tunnel=yes with complete node elevations supported. Road grades interpolate between supplied nodes; tunnel cross-section is rectangular and physical clearance is constant (shape estimate). Access/oneway/vehicle limits remain omitted.")
        if counts.get("tunnel_segments"): layer.estimate("rectangular_tunnel_cross_section")
    # Put source-level omissions before per-road warning samples, even at the cap.
    layer.warnings = (layer.warnings + previous)[:50]
    layer.encode()
    return layer
