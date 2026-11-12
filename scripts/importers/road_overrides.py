"""Explicit, immutable-snapshot road corrections; no geographic special cases.

A way row may correct its width and lane count, and may re-route segments
between two adjacent source nodes through author points (WGS84) that stay
within a stated distance of the original segment. Every original node and
connection is kept; inserted vertices get synthetic refs that never join
another way."""
from copy import deepcopy
import math
import re

# Synthetic refs (19 digits) for inserted vertices: below the bridge-lead refs
# (8e18) and above every OSM node ID; base + way ID * 10000 + index (< 4097).
OVERRIDE_REF_BASE = 7 * 10 ** 18
MAX_SEGMENTS = 16
MAX_POINTS = 256
MAX_DISPLACEMENT_M = 5.0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _node(value):
    return type(value) in (int, float) and float(value).is_integer() and 1 <= value < 10 ** 15


def _validate_segments(segments):
    if not isinstance(segments, list) or not 1 <= len(segments) <= MAX_SEGMENTS:
        raise ValueError("road override segments must contain 1..16 records")
    pairs = set()
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {"from_node", "to_node", "max_displacement_m", "points"}:
            raise ValueError("road override segment needs from_node, to_node, max_displacement_m and points")
        if not _node(segment["from_node"]) or not _node(segment["to_node"]) or segment["from_node"] == segment["to_node"]:
            raise ValueError("road override segment nodes must be two distinct OSM node IDs")
        pair = frozenset((int(segment["from_node"]), int(segment["to_node"])))
        if pair in pairs: raise ValueError("road override segments must be unique")
        pairs.add(pair)
        if not _number(segment["max_displacement_m"]) or not 0 < segment["max_displacement_m"] <= MAX_DISPLACEMENT_M:
            raise ValueError("road override max_displacement_m must be in (0, 5]")
        points = segment["points"]
        if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
            raise ValueError("road override segment points must contain 1..256 [lon, lat] points")
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or not all(_number(v) for v in point) or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90:
                raise ValueError("road override points must be [lon, lat] in WGS84")


def validate(value):
    if not isinstance(value, dict) or set(value) != {"osm_sha256", "ways"}:
        raise ValueError("road_overrides needs osm_sha256 and ways")
    if not isinstance(value["osm_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["osm_sha256"]):
        raise ValueError("road_overrides requires the exact source SHA-256")
    if not isinstance(value["ways"], list) or not 1 <= len(value["ways"]) <= 10000:
        raise ValueError("road_overrides ways must contain 1..10000 records")
    seen = set()
    for row in value["ways"]:
        keys = set(row) if isinstance(row, dict) else set()
        dimensions = {"width_m", "lanes"} <= keys
        if not isinstance(row, dict) or "source_id" not in keys or keys - {"source_id", "width_m", "lanes", "segments"} \
                or len(keys & {"width_m", "lanes"}) == 1 or not (dimensions or "segments" in keys):
            raise ValueError("road override needs source_id with width_m and lanes and/or segments")
        sid = row["source_id"]
        if not isinstance(sid, str) or not re.fullmatch(r"way/[1-9][0-9]*", sid) or sid in seen:
            raise ValueError("road override source IDs must be unique OSM ways")
        seen.add(sid)
        if dimensions:
            if type(row["lanes"]) not in (int, float) or not float(row["lanes"]).is_integer() or not 1 <= row["lanes"] <= 16:
                raise ValueError("road override lanes must be an integer in 1..16")
            if type(row["width_m"]) not in (int, float) or not math.isfinite(row["width_m"]) or not .2 <= row["width_m"] <= 200:
                raise ValueError("road override width_m must be finite and in .2..200")
        if "segments" in row: _validate_segments(row["segments"])
    return value


def _local(origin):
    """Metres in the UTM frame of `origin`, the frame city maps are projected in."""
    import pyproj
    pyproj.network.set_network_enabled(False)
    zone = min(60, math.floor((origin[0] + 180) / 6) + 1)
    epsg = (32700 if origin[1] < 0 else 32600) + zone
    transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True, allow_ballpark=False, only_best=True)
    def project(point):
        return transformer.transform(point[0], point[1], errcheck=True)
    return project


def _plan_segment(feature, segment, sid):
    """Where and how one segment insertion applies, or ValueError."""
    p = feature["properties"]
    coords = feature["geometry"]["coordinates"]
    refs = p.get("_city_refs")
    a, b = int(segment["from_node"]), int(segment["to_node"])
    hits = [i for i in range(len(coords) - 1) if refs and {refs[i], refs[i + 1]} == {a, b}] if refs and len(refs) == len(coords) else []
    if not hits: return None
    if "osm_node_refs" in p or "_city_estimated_m" in p:
        raise ValueError(f"road override segment of {sid} must be an ordinary ground road")
    i = hits[0]
    forward = refs[i] == a
    start, end = (coords[i], coords[i + 1]) if forward else (coords[i + 1], coords[i])
    project = _local(start)
    sx, sy = project(start)
    ex, ey = project(end)
    length = math.hypot(ex - sx, ey - sy)
    if length <= 0: raise ValueError(f"road override segment of {sid} has zero length")
    offsets, params = [], []
    for point in segment["points"]:
        x, y = project(point)
        t = ((x - sx) * (ex - sx) + (y - sy) * (ey - sy)) / length ** 2
        if not 0 < t < 1: raise ValueError(f"road override points of {sid} must lie between its segment nodes")
        offsets.append(abs((x - sx) * (ey - sy) - (y - sy) * (ex - sx)) / length)
        params.append(t)
    if any(b <= a for a, b in zip(params, params[1:])):
        raise ValueError(f"road override points of {sid} must advance along the segment")
    if max(offsets) > segment["max_displacement_m"] + 1e-6:  # 1 µm for decimal degrees
        raise ValueError(f"road override points of {sid} exceed max_displacement_m")
    return dict(index=i, forward=forward, params=params, max_offset_m=max(offsets),
                original=[list(start[:2]), list(end[:2])])


def apply(collection, value, source_sha256):
    validate(value)
    if value["osm_sha256"] != source_sha256:
        raise ValueError("road_overrides OSM snapshot SHA-256 mismatch")
    edits = {r["source_id"]: r for r in value["ways"]}
    roads = [f for f in collection["features"] if f["geometry"]["type"] == "LineString" and "_city_road_tags" in f["properties"]]
    # Check every target before changing the collection; failure is atomic.
    found = {f["properties"].get("osm_source_id") for f in roads}
    missing = sorted(set(edits) - found)
    if missing: raise ValueError("road_overrides target missing from selected source: " + ", ".join(missing))
    plans = {}
    for sid, row in edits.items():
        for n, segment in enumerate(row.get("segments", [])):
            matches = []
            for index, feature in enumerate(collection["features"]):
                if feature["geometry"]["type"] == "LineString" and "_city_road_tags" in feature["properties"] \
                        and feature["properties"].get("osm_source_id") == sid:
                    plan = _plan_segment(feature, segment, sid)
                    if plan is not None: matches.append((index, plan))
            if len(matches) != 1:
                raise ValueError(f"road override segment {segment['from_node']}-{segment['to_node']} of {sid} must match one adjacent source node pair")
            plans.setdefault(matches[0][0], []).append((sid, n, segment, matches[0][1]))
    result = deepcopy(collection)
    report = {}
    for feature in result["features"]:
        p = feature["properties"]
        sid = p.get("osm_source_id")
        if sid not in edits or feature["geometry"]["type"] != "LineString" or "_city_road_tags" not in p: continue
        row = edits[sid]
        entry = report.setdefault(sid, {"source_id": sid, "original_width_m": p.get("width_m"),
                                        "original_lanes": p["_city_road_tags"].get("lanes")})
        if "width_m" in row:
            entry.update(width_m=row["width_m"], lanes=row["lanes"])
            p["width_m"] = float(row["width_m"])
            p["_city_road_tags"]["lanes"] = str(int(row["lanes"]))
            p.pop("_city_width_estimate", None)
            p["_city_author_override"] = True
    way_number = {sid: int(sid.split("/")[1]) for sid in edits}
    counters = {}
    for index, items in plans.items():
        feature = result["features"][index]
        p = feature["properties"]
        coords, refs = feature["geometry"]["coordinates"], p["_city_refs"]
        # Later positions first keep earlier indices valid.
        for sid, n, segment, plan in sorted(items, key=lambda item: -item[3]["index"]):
            i, start, end = plan["index"], coords[plan["index"]], coords[plan["index"] + 1]
            points = segment["points"] if plan["forward"] else list(reversed(segment["points"]))
            params = plan["params"] if plan["forward"] else [1 - t for t in reversed(plan["params"])]
            inserted, inserted_refs = [], []
            for point, t in zip(points, params):
                vertex = [float(point[0]), float(point[1])]
                if len(start) > 2: vertex.extend(start[k] + (end[k] - start[k]) * t for k in range(2, len(start)))
                counters[sid] = counters.get(sid, 0) + 1
                inserted.append(vertex)
                inserted_refs.append(OVERRIDE_REF_BASE + way_number[sid] * 10000 + counters[sid])
            coords[i + 1:i + 1] = inserted
            refs[i + 1:i + 1] = inserted_refs
            p["_city_author_geometry"] = True
            report[sid].setdefault("segments", []).append(dict(
                from_node=int(segment["from_node"]), to_node=int(segment["to_node"]),
                original_wgs84=plan["original"], points=deepcopy(segment["points"]),
                inserted_refs=inserted_refs if plan["forward"] else list(reversed(inserted_refs)),
                max_offset_m=round(plan["max_offset_m"], 4)))
    for entry in report.values():
        entry.get("segments", []).sort(key=lambda s: (s["from_node"], s["to_node"]))
    return result, {"request": deepcopy(value), "applied": sorted(report.values(), key=lambda r: r["source_id"])}
