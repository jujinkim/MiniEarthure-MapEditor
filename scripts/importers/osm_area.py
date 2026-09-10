"""Bounded derived geometry crop; captured OSM bytes are never rewritten."""
from importlib.metadata import version
import json
from import_layer import number, MAX_POINTS
from polygon_geometry import Budget, group_rings

VERTICAL_PROFILE = "explicit-ground-crop-v1"


def segment_interval(a, b, selected):
    """Nonzero source-parameter interval inside the closed rectangle, or None."""
    lo, hi = 0.0, 1.0
    for axis in range(2):
        delta = b[axis] - a[axis]
        if delta == 0:
            if not selected[axis] <= a[axis] <= selected[axis+2]: return None
        else:
            limits = sorted(((selected[axis]-a[axis])/delta, (selected[axis+2]-a[axis])/delta))
            lo, hi = max(lo, limits[0]), min(hi, limits[1])
    return (lo, hi) if lo < hi and a != b else None


def ground_parts(feature, selected, identity):
    """Clip in source traversal order; never join separate visits to the window.

    Heights interpolate only between two supplied node elevations. Synthetic cut
    IDs are local to this feature/segment; position equality is not connectivity.
    """
    p = feature["properties"]
    coordinates, refs, heights = feature["geometry"]["coordinates"], p["osm_node_refs"], p["elevations_m"]
    current = None
    for index, (a, b) in enumerate(zip(coordinates, coordinates[1:])):
        if a == b:
            raise ValueError("OSM explicit crop has a zero-length source segment")
        interval = segment_interval(a, b, selected)
        if interval is None:
            if current is not None:
                yield current
                current = None
            continue
        lo, hi = interval

        def endpoint(t, side):
            if t == 0: return list(a), refs[index], heights[index]
            if t == 1: return list(b), refs[index+1], heights[index+1]
            point = [max(selected[k], min(selected[k+2], a[k]+t*(b[k]-a[k]))) for k in range(2)]
            # Preserve the selected boundary exactly (including corner ties),
            # rather than retaining cancellation error from a + t * delta.
            for axis in range(2):
                if b[axis] != a[axis]:
                    for boundary in (selected[axis], selected[axis+2]):
                        if t == (boundary-a[axis])/(b[axis]-a[axis]): point[axis] = boundary
            return point, f"crop-{identity}-{index}-{side}", heights[index]+t*(heights[index+1]-heights[index])

        start, end = endpoint(lo, "in"), endpoint(hi, "out")
        if current is None:
            current = dict(type="Feature", properties=dict(p, osm_node_refs=[start[1]], elevations_m=[start[2]]),
                           geometry=dict(type="LineString", coordinates=[start[0]]))
        current["geometry"]["coordinates"].append(end[0])
        current["properties"]["osm_node_refs"].append(end[1])
        current["properties"]["elevations_m"].append(end[2])
        if hi < 1:
            yield current
            current = None
    if current is not None: yield current


def bounds(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("OSM bbox requires west/south/east/north")
    w, s, e, n = [number(v, "OSM bbox", -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84) for i, v in enumerate(value)]
    if not 0 < e-w <= 0.02 or not 0 < n-s <= 0.02:
        raise ValueError("OSM bbox needs west < east, south < north and at most 0.02 degrees per side")
    return [w, s, e, n]


def crop(collection, selected):
    selected = bounds(selected)
    if version("shapely") != "2.1.2":
        raise ValueError("OSM crop requires shapely 2.1.2; install requirements-import.txt")
    import shapely
    from shapely.geometry import shape, mapping
    window = shapely.box(*selected)
    output, budget = [], Budget()
    counts = dict(input_features=len(collection["features"]), outside_features=0, changed_features=0, output_features=0, boundary_contacts=0)
    points = 0
    has_explicit = any("osm_node_refs" in f["properties"] for f in collection["features"])
    vertical_counts = dict(clipped_ground_features=0, outside_explicit_features=0, retained_structure_features=0)
    retained_structures, incomplete_structures = set(), set()
    source_ground_refs = {ref for f in collection["features"] if f["properties"].get("road_kind") == "ground"
                          for ref in f["properties"]["osm_node_refs"]}

    def append(feature):
        nonlocal points
        def count(value):
            if isinstance(value[0], (int, float)): return 1
            return sum(count(v) for v in value)
        points += count(feature["geometry"]["coordinates"])
        if points > MAX_POINTS or len(output) >= 20_000:
            raise ValueError("OSM crop output budget exceeded")
        output.append(feature)

    def parts(geometry, expected):
        if geometry.is_empty: return []
        if geometry.geom_type == expected: return [geometry]
        if geometry.geom_type.startswith("Multi") or geometry.geom_type == "GeometryCollection":
            return [p for child in geometry.geoms for p in parts(child, expected)]
        # Point/line-only contacts have no road length / polygon area.
        counts["boundary_contacts"] += 1
        return []
    for index, feature in enumerate(collection["features"]):
        source = shape(feature["geometry"])
        if not source.is_valid or source.is_empty:
            raise ValueError("Invalid OSM geometry before crop; no repair or silent filtering")
        if source.bounds[2]-source.bounds[0] > 180:
            raise ValueError("OSM antimeridian geometry is unsupported")
        if "osm_node_refs" in feature["properties"]:
            p = feature["properties"]
            structure = p["road_kind"] != "ground"
            complete = window.covers(source)
            if structure and not complete: incomplete_structures.add(p["osm_way_id"])
            before = len(output)
            if structure:
                if not complete:
                    coordinates = feature["geometry"]["coordinates"]
                    if any(segment_interval(a,b,selected) is not None for a,b in zip(coordinates,coordinates[1:])):
                        raise ValueError("OSM bbox must contain complete bridge/tunnel spans; partial structure crop is unsupported")
                else:
                    retained_structures.add(p["osm_way_id"])
                    vertical_counts["retained_structure_features"] += 1
            if complete:
                # Retain exact vertex order/profile and original graph node IDs.
                append(feature)
            elif not structure:
                for part in ground_parts(feature, selected, index): append(part)
                if len(output) > before:
                    counts["changed_features"] += 1
                    vertical_counts["clipped_ground_features"] += 1
            if len(output) == before:
                counts["outside_features"] += 1
                counts["boundary_contacts"] += source.intersects(window)
                vertical_counts["outside_explicit_features"] += 1
            continue
        clipped = source.intersection(window)
        expected = "LineString" if source.geom_type == "LineString" else "Polygon"
        geometries = parts(clipped, expected)
        if not geometries:
            counts["outside_features"] += 1
            continue
        counts["changed_features"] += not source.equals(clipped)
        if expected == "Polygon":
            # Shared normalizer retains holes, islands and stable part ordering.
            polygons = group_rings([list(map(list, g.exterior.coords)) for g in geometries],
                [list(map(list, ring.coords)) for g in geometries for ring in g.interiors], budget)
            geometries_json = [dict(type="MultiPolygon", coordinates=polygons)]
        else:
            geometries_json = [json.loads(json.dumps(mapping(g))) for g in geometries]
        for geometry in geometries_json:
            append(dict(type="Feature", properties=feature["properties"], geometry=geometry))
    if retained_structures & incomplete_structures:
        raise ValueError("OSM bbox must contain complete bridge/tunnel spans, including split source-way pieces")
    # A boundary-only contact is not a drivable approach. Check the retained graph,
    # not the complete source's earlier connectivity proof.
    ground_ends = {ref for f in output if f["properties"].get("road_kind") == "ground"
                   for ref in (f["properties"]["osm_node_refs"][0], f["properties"]["osm_node_refs"][-1])}
    for feature in output:
        p = feature["properties"]
        if p.get("road_kind") in ("bridge", "tunnel") and any(ref in source_ground_refs and ref not in ground_ends for ref in (p["osm_node_refs"][0], p["osm_node_refs"][-1])):
            raise ValueError("OSM crop removes a required nonzero explicit-height ground approach; expand bbox")
    if not output: raise ValueError("OSM bbox contains no supported nonzero geometry")
    counts["output_features"] = len(output)
    meta = dict(bbox=selected, policy="geometry-intersection-v1", shapely="2.1.2", geos=shapely.geos_version_string, counts=counts)
    if has_explicit:
        meta["policy"] = "geometry-intersection-v2"
        meta["vertical"] = dict(profile=VERTICAL_PROFILE, **vertical_counts)
    return dict(type="FeatureCollection", features=output), meta
