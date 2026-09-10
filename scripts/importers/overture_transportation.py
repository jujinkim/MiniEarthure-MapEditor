"""Bounded, complete Overture road/connector snapshots. Public MIT adapter.

Connectivity comes only from source IDs, never snapping or geometric crossings.
This profile retains whole in-area segments and refuses unsupported semantics.
"""
from bisect import bisect_right
import hashlib
import json
from import_layer import ImportLayer, Source, MAX_INPUT, number, text, strict_json
from projection import Coordinates
import overture_area as area

LICENSE = "ODbL-1.0; © OpenStreetMap contributors; TomTom; Overture Maps Foundation; https://docs.overturemaps.org/attribution/#transportation"
MAX_FEATURES = 1024
MAX_POINTS = 8192
MAX_ROADS = 2048
MAX_RULES = 1024
MAX_OUTPUT_POINTS = 16384
CONNECTOR_TOLERANCE_M = 0.001
MAX_CONNECTOR_EDGE_CHECKS = 65536
CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "living_street", "service", "unclassified"}
COMMON = {"id", "bbox", "theme", "type", "version", "sources"}
SEGMENT = COMMON | {"subtype", "class", "connectors", "road_flags", "road_surface", "width_rules", "level", "level_rules", "subclass", "subclass_rules", "names", "routes", "destinations", "speed_limits"}


def plan(release, bbox, ground_m):
    result = area.plan(release, bbox)
    result.update(theme="transportation", type="segment", license=LICENSE,
                  profile="ground-graph-v1", ground_m=number(ground_m, "chosen road plane", -9000, 9000))
    return result


def checked_plan(value):
    return plan(value.get("release"), value.get("bbox"), value.get("ground_m"))


def identity(value):
    result = text(value, "Overture ID", 128)
    if result != value: raise ValueError("Overture ID must not contain surrounding whitespace")
    return result


def uniform(properties, key, default=None):
    """Only one whole-segment physical rule; never erase scoping/restrictions."""
    rules = properties.get(key)
    if rules is None or rules == []: return default
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        raise ValueError(f"{key}: requires one whole-segment rule")
    rule = rules[0]
    if set(rule) - {"value", "between"} or "value" not in rule:
        raise ValueError(f"{key}: unsupported conditional/unknown rule")
    between = rule.get("between")
    if between is not None:
        if not isinstance(between, list) or len(between) != 2 or [number(v,key,0,1) for v in between] != [0,1]:
            raise ValueError(f"{key}: partial physical rule requires explicit authoring")
    return rule["value"]


def physical_rules(properties, key):
    """Canonical complete partition. Gaps/overlap never acquire guessed priority."""
    rules = properties.get(key)
    if rules is None or rules == []: return [(0, 1, None)]
    if not isinstance(rules, list) or not 1 <= len(rules) <= MAX_RULES:
        raise ValueError(f"{key}: physical rule budget exceeded")
    result = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {"value", "between"} or "value" not in rule:
            raise ValueError(f"{key}: unsupported conditional/unknown rule")
        between = rule.get("between")
        if between is None: between = [0, 1]
        if not isinstance(between, list) or len(between) != 2:
            raise ValueError(f"{key}: expected bounded interval")
        start, end = [number(v, key, 0, 1) for v in between]
        if start >= end: raise ValueError(f"{key}: empty/reversed interval")
        value = rule["value"]
        if key == "width_rules": number(value, "road width", 0.2, 100)
        elif value not in ("unknown", "paved", "gravel", "dirt"):
            raise ValueError("Unsupported/ambiguous road surface")
        result.append((start, end, value))
    result.sort(key=lambda rule: rule[:2])
    previous = 0
    for start, end, _ in result:
        if start != previous: raise ValueError(f"{key}: interval gap/overlap")
        previous = end
    if previous != 1: raise ValueError(f"{key}: incomplete interval coverage")
    return result


def densify(coords, lengths, widths, surfaces, geod, connections=None):
    """Split physical edges, never graph nodes, at WGS84 distance fractions."""
    fractions = [distance / lengths[-1] for distance in lengths]
    boundaries = {v for rules in (widths, surfaces) for a,b,_ in rules for v in (a,b)}
    positions = dict(zip(fractions, coords))
    for at in sorted(boundaries - positions.keys()):
        edge = bisect_right(fractions, at) - 1
        azimuth, _, _ = geod.inv(*coords[edge], *coords[edge+1])
        lon, lat, _ = geod.fwd(*coords[edge], azimuth, at*lengths[-1]-lengths[edge])
        positions[at] = [lon, lat]
    positions.update(connections or {})
    ordered = sorted(positions)
    indices = {at:i for i,at in enumerate(ordered)}
    def values(rules):
        index, output = 0, []
        for start in ordered[:-1]:
            while start >= rules[index][1]: index += 1
            output.append(rules[index][2])
        return output
    return ordered, [positions[a] for a in ordered], [indices[a] for a in fractions], values(widths), values(surfaces)


def connection_position(point, at, coords, lengths, geod, budget):
    """Explicit reference only: bounded geodetic closest point, no ID inference.

    Canonical shared node is the connector coordinate. At most 1 mm correction
    is permitted and recorded; multiple nearby positions reject, never choose one.
    """
    fractions = [v/lengths[-1] for v in lengths]
    if point in coords:
        index = coords.index(point)
        if abs(at-fractions[index]) > 1e-7:
            raise ValueError("Connector at disagrees with WGS84 geodetic vertex fraction")
        return fractions[index], index, 0.0
    budget[0] += len(coords)-1
    if budget[0] > MAX_CONNECTOR_EDGE_CHECKS:
        raise ValueError("Connector edge comparison budget exceeded")
    candidates = []
    for i, (a,b) in enumerate(zip(coords,coords[1:])):
        azimuth, _, distance = geod.inv(*a,*b)
        def evaluate(offset):
            lon,lat,_ = geod.fwd(*a,azimuth,offset)
            return geod.inv(lon,lat,*point)[2]
        # Convex distance on these bounded (<~3 km), non-antipodal edges.
        lo,hi = 0.0,distance
        ratio = (5**0.5-1)/2
        x,y = hi-ratio*(hi-lo),lo+ratio*(hi-lo)
        dx,dy = evaluate(x),evaluate(y)
        for _ in range(48):
            if dx < dy:
                hi,y,dy = y,x,dx
                x = hi-ratio*(hi-lo); dx = evaluate(x)
            else:
                lo,x,dx = x,y,dy
                y = lo+ratio*(hi-lo); dy = evaluate(y)
        offset = min((0.0,distance,(lo+hi)/2),key=evaluate)
        separation = evaluate(offset)
        if separation <= CONNECTOR_TOLERANCE_M:
            fraction = (lengths[i]+offset)/lengths[-1]
            if not any(abs(fraction-prev[0])*lengths[-1] <= 0.000001 for prev in candidates):
                candidates.append((fraction,separation))
    if len(candidates) != 1:
        raise ValueError("Off-line/ambiguous connector position")
    closest,_ = candidates[0]
    if abs(at-closest) > 1e-7:
        raise ValueError("Connector at disagrees with closest geodetic position")
    # Reuse a closest source endpoint; interior locations use the explicit at,
    # so an exactly equal physical boundary remains one shape vertex.
    vertex = next((i for i,v in enumerate(fractions) if closest == v),None)
    resolved = fractions[vertex] if vertex is not None else at
    if vertex is None:
        if not 0 < resolved < 1: raise ValueError("Off-vertex endpoint mismatch")
        edge = bisect_right(fractions,resolved)-1
        azimuth,_,_ = geod.inv(*coords[edge],*coords[edge+1])
        lon,lat,_ = geod.fwd(*coords[edge],azimuth,resolved*lengths[-1]-lengths[edge])
        expected = [lon,lat]
    else: expected = coords[vertex]
    displacement = geod.inv(*expected,*point)[2]
    if displacement > CONNECTOR_TOLERANCE_M:
        raise ValueError("Connector position exceeds 1 mm correction")
    return resolved,vertex,displacement


def parse(raw):
    from pyproj import Geod
    from shapely.geometry import LineString
    if len(raw) > MAX_INPUT: raise ValueError("Overture snapshot exceeds 32 MiB")
    value = strict_json(raw)
    if not isinstance(value, dict) or number(value.get("snapshot_version"),"snapshot version",1,1) != 1:
        raise ValueError("Expected Overture transportation snapshot version 1")
    query = checked_plan(value)
    if set(value) != set(query) | {"snapshot_version", "features"} or any(value[k] != v for k,v in query.items()):
        raise ValueError("Invalid transportation source contract/license")
    features = value["features"]
    if not isinstance(features, list) or not 1 <= len(features) <= MAX_FEATURES:
        raise ValueError("Transportation feature budget exceeded (1..1024)")
    segments, connectors, provenance, seen = {}, {}, {}, set()
    total_points = 0
    w,s,e,n = query["bbox"]
    def position(pos):
        if not isinstance(pos, list) or len(pos) != 2: raise ValueError("Expected 2D WGS84 position")
        x,y = number(pos[0],"longitude",-180,180), number(pos[1],"latitude",-80,84)
        if not w < x < e or not s < y < n:
            raise ValueError("Whole road graph must be strictly inside query; enlarge area, no clipping")
        return [x,y]
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature": raise ValueError("Expected Overture Feature")
        fid = identity(feature.get("id"))
        if fid in seen: raise ValueError("Duplicate Overture ID")
        seen.add(fid)
        p,g = feature.get("properties"), feature.get("geometry")
        if not isinstance(p, dict) or p.get("id") != fid or p.get("theme") != "transportation" or not isinstance(g, dict):
            raise ValueError("Invalid transportation identity/theme/geometry")
        kind = p.get("type")
        if kind not in ("segment", "connector"): raise ValueError("Unsupported transportation feature type")
        version = number(p.get("version"),"source version",1,2147483647)
        if int(version) != version: raise ValueError("Invalid source version")
        for key in set(p) - (COMMON if kind == "connector" else SEGMENT):
            if p[key] is not None and p[key] != []:
                raise ValueError(f"Unsupported transportation property {key}; no silent loss")
        sources = p.get("sources")
        if not isinstance(sources, list) or not 1 <= len(sources) <= 128 or len(json.dumps(sources).encode()) > 16384:
            raise ValueError("Missing/oversized transportation attribution")
        for source in sources:
            if not isinstance(source, dict): raise ValueError("Invalid source attribution")
            text(source.get("dataset"), "source dataset")
            if source.get("license") is not None: text(source["license"], "source license")
        provenance[fid] = dict(id=fid, version=p["version"], sources=sources)
        coords = g.get("coordinates")
        if kind == "connector":
            if g.get("type") != "Point": raise ValueError("Connector requires Point")
            total_points += 1
            connectors[fid] = position(coords)
        else:
            if g.get("type") != "LineString" or not isinstance(coords,list) or not 2 <= len(coords) <= MAX_POINTS:
                raise ValueError("Segment requires bounded LineString")
            total_points += len(coords)
            coords = [position(pos) for pos in coords]
            if len(set(map(tuple,coords))) != len(coords) or not LineString(coords).is_simple:
                raise ValueError("Repeated/self-crossing road geometry is unsupported")
            if p.get("subtype") != "road" or p.get("class") not in CLASSES:
                raise ValueError("Unsupported road subtype/class; no partial graph")
            if number(p.get("level",0) if p.get("level") is not None else 0,"level",-100,100) != 0 or number(uniform(p,"level_rules",0),"level rule",-100,100) != 0:
                raise ValueError("Z-order is not height; elevated/underground roads require explicit authoring")
            flags = p.get("road_flags")
            if flags not in (None, []):
                # Historical flag arrays and current rules are both explicit.
                if isinstance(flags,list) and all(isinstance(f,str) for f in flags):
                    values = flags
                elif isinstance(flags,list) and len(flags) == 1 and isinstance(flags[0],dict) and set(flags[0]) <= {"values","between"} and flags[0].get("between") is None:
                    values = flags[0].get("values")
                else: raise ValueError("Scoped road flags require explicit authoring")
                if not isinstance(values,list) or not values or any(f != "is_link" for f in values):
                    raise ValueError("Bridge/tunnel/other road flags unsupported without metric geometry")
            if p.get("subclass") not in (None,"link") or uniform(p,"subclass_rules",None) not in (None,"link"):
                raise ValueError("Unsupported road subclass")
            widths = physical_rules(p,"width_rules")
            surfaces = physical_rules(p,"road_surface")
            segments[fid] = dict(coords=coords, properties=p, widths=widths, surfaces=surfaces)
        if total_points > MAX_POINTS: raise ValueError("Transportation point budget exceeded")
    if not segments or not connectors: raise ValueError("Requires complete segments and connectors")
    geod = Geod(ellps="WGS84")
    used, roads = set(), []
    output_points = len(connectors)
    comparison_budget = [0]
    for fid, segment in sorted(segments.items()):
        coords, p = segment["coords"], segment["properties"]
        refs = p.get("connectors")
        if not isinstance(refs,list) or not 2 <= len(refs) <= MAX_FEATURES: raise ValueError("Missing/bounded connector references")
        lengths = [0.0]
        for a,b in zip(coords,coords[1:]):
            lengths.append(lengths[-1] + geod.inv(*a,*b)[2])
        linked, ids = [], set()
        for ref in refs:
            if not isinstance(ref,dict) or set(ref) != {"connector_id","at"}: raise ValueError("Invalid connector reference")
            cid = identity(ref["connector_id"])
            at = number(ref["at"],"connector at",0,1)
            if cid in ids or cid not in connectors: raise ValueError("Duplicate/missing connector reference")
            ids.add(cid)
            resolved,index,displacement = connection_position(connectors[cid],at,coords,lengths,geod,comparison_budget)
            linked.append((resolved,cid,at,index,displacement))
        linked.sort()
        if linked[0][0] != 0 or linked[-1][0] != 1 or len({v[0] for v in linked}) != len(linked):
            raise ValueError("Incomplete/ambiguous segment endpoints")
        used.update(ids)
        provenance[fid].update(road_class=p["class"], connectors=[dict(connector_id=c, at=a, vertex=i,
            resolved_at=r, displacement_m=d) for r,c,a,i,d in linked], road_ids=[])
        connections = {r:connectors[c] for r,c,_,_,_ in linked}
        fractions, points, _, widths, surfaces = densify(coords, lengths, segment["widths"], segment["surfaces"], geod, connections)
        indices = {at:i for i,at in enumerate(fractions)}
        provenance[fid].update(road_spans=[], source_fractions=[v/lengths[-1] for v in lengths], physical_rules=dict(width_rules=segment["widths"], road_surface=segment["surfaces"]))
        for left,right in zip(linked,linked[1:]):
            if len(roads) >= MAX_ROADS: raise ValueError("Transportation split-road budget exceeded")
            a,b = indices[left[0]], indices[right[0]]
            output_points += b-a+1
            if output_points > MAX_OUTPUT_POINTS: raise ValueError("Transportation output point budget exceeded")
            roads.append(dict(source_id=fid, start=left[1], end=right[1], coords=points[a:b+1],
                              fractions=fractions[a:b+1], widths=widths[a:b], surfaces=surfaces[a:b]))
    if used != set(connectors): raise ValueError("Unreferenced connectors; incomplete graph is not adopted")
    metadata = dict(query, connection_profile="explicit-position-v1", source_position_count=total_points, segment_sources=[provenance[f] for f in sorted(segments)],
                    connector_sources=[provenance[f] for f in sorted(connectors)])
    return dict(roads=roads, connectors=connectors, metadata=metadata)


def convert(parsed, source, raw, *, layer_id, coordinates, accuracy="unknown", progress=None):
    from shapely.geometry import LineString
    transform = Coordinates(coordinates)
    if transform.metadata["mode"] != "wgs84-utm": raise ValueError("Transportation needs explicit WGS84 origins")
    # Metadata is owned by this conversion, not mutated on the reusable parse result.
    metadata = json.loads(json.dumps(parsed["metadata"]))
    layer = ImportLayer(layer_id, Source(source,hashlib.sha256(raw).hexdigest(),len(raw),LICENSE,accuracy),
                        transform.metadata, adapter="overture-transportation-v1")
    layer.coordinates["overture_transportation"] = metadata
    layer.feature_count = len(metadata["segment_sources"]) + len(metadata["connector_sources"])
    height = round(metadata["ground_m"]*100)
    prefix = f"import-{layer_id}-"
    projected, occupied = {}, {}
    def point(pos):
        key = tuple(pos)
        if key not in projected:
            x,z = transform.point(pos)
            if (x,z) in occupied and occupied[x,z] != key:
                raise ValueError("Distinct source vertices collapse after centimetre projection")
            occupied[x,z] = key
            projected[key] = [x,height,z]
        p = projected[key]
        layer.point(p[0],p[2])
        return p
    node_ids = {}
    for index, entry in enumerate(metadata["connector_sources"]):
        cid = entry["id"]
        nid = prefix + f"connector-{index}"
        node_ids[cid] = nid
        p = point(parsed["connectors"][cid])
        entry.update(node_id=nid, position_cm=p)
        layer.add("nodes",dict(id=nid,position=p,level=0))
    segments = {entry["id"]:entry for entry in metadata["segment_sources"]}
    for index, road in enumerate(parsed["roads"]):
        rid = prefix + f"road-{index}"
        points = [point(p) for p in road["coords"]]
        if not LineString([(p[0],p[2]) for p in points]).is_simple: raise ValueError("Road self-crosses after projection")
        widths, surfaces = [], []
        for width, surface in zip(road["widths"], road["surfaces"]):
            if width is None:
                width = 8
                layer.estimate("width_m")
            if surface in (None,"unknown","paved"):
                surface = "asphalt"
                layer.estimate("asphalt_surface")
            widths.append(round(width*100))
            surfaces.append(surface)
        layer.estimate("chosen_road_plane")
        layer.add("roads",dict(id=rid,**{"from":node_ids[road["start"]],"to":node_ids[road["end"]]},
            points=points,widths_cm=widths,surfaces=surfaces,
            kind="ground",clearance_cm=None,sidewalk_cm=None))
        segments[road["source_id"]]["road_spans"].append(dict(road_id=rid, fractions=road["fractions"],
            points_cm=points, widths_cm=widths, surfaces=surfaces))
        segments[road["source_id"]]["road_ids"].append(rid)
        if progress: progress(index+1,len(parsed["roads"]))
    layer.warning("Transportation ground graph only; exact connector IDs connect endpoints. Interior connectors split whole source segments. Physical boundaries add geodetically interpolated vertices, never connectors. Crossing coordinates never create graph connections.")
    layer.warning("Explicit connector positions: WGS84 closest position and at are checked; shared ID uses the source connector coordinate with at most 1 mm correction. Ambiguous/off-line positions reject the entire graph.")
    layer.warning("Chosen road plane is an estimate, not source elevation or terrain sampling. Recipe 2+ ground ribbons follow terrain. Verify terrain alignment before adoption; level is not metric height.")
    layer.warning("Absent width estimates 8 m; paved/unknown/absent surface estimates asphalt. Source names, routes, destinations and speed limits remain in the snapshot, not game rules. No inferred sidewalks.")
    layer.warning("Complete segment/connector query required. Crossing bbox, missing refs, rail/water, restrictions, structures and incomplete/overlapping/conditional physical rules reject the whole candidate. No clipped or repaired graph.")
    layer.encode()
    return layer
