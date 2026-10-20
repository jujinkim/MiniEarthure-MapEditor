"""Bounded derived geometry crop; captured OSM bytes are never rewritten."""
from collections import Counter
from importlib.metadata import version
import json
from import_layer import number, MAX_POINTS, soft_limit
from polygon_geometry import Budget, SpatialBudget, group_rings

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


def region_intervals(a, b, region):
    """Ordered source-parameter intervals of segment a→b inside a polygonal region.

    Cut points are the exact GEOS intersection coordinates; touching points carry
    no length and are not intervals.
    """
    import shapely
    from shapely.geometry import LineString
    if a == b: return []
    segment = LineString([a, b])
    # `region` is prepared by the caller; most segments are wholly in or out.
    if shapely.covers(region, segment): return [(0.0, 1.0, None, None)]
    if not shapely.intersects(region, segment): return []
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx + dy*dy
    found = []
    pieces = segment.intersection(region)
    for piece in getattr(pieces, "geoms", [pieces]):
        if piece.geom_type != "LineString" or piece.length == 0: continue
        ends = [list(piece.coords[0]), list(piece.coords[-1])]
        t = [min(1.0, max(0.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / length)) for p in ends]
        if t[0] > t[1]: t, ends = t[::-1], ends[::-1]
        found.append((t[0], t[1], ends[0], ends[1]))
    found.sort(key=lambda v: v[0])
    merged = []
    for item in found:
        if merged and item[0] <= merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], item[1]), merged[-1][2], item[3] if item[1] >= merged[-1][1] else merged[-1][3])
        else: merged.append(item)
    return [(lo, hi, (pa if lo > 0 else None), (pb if hi < 1 else None)) for lo, hi, pa, pb in merged if lo < hi]


# A region cut shorter than one 1:8 map centimetre (8 source cm) has no drivable
# length; like a point contact it is a boundary contact, not a road piece.
MIN_REGION_PIECE_M = 0.08


def geographic_length_m(points):
    import math
    total = 0.0
    for a, b in zip(points, points[1:]):
        scale = math.cos(math.radians((a[1]+b[1])/2))
        total += math.hypot((b[0]-a[0])*scale, b[1]-a[1]) * 111_320
    return total


def region_line_parts(coordinates, region):
    """Pieces of a polyline inside `region`, keeping every source vertex exact.

    Only the cut points come from GEOS; whole-line overlay could snap original
    vertices and separate shared source nodes by centimetres.
    """
    pieces, current = [], None
    for a, b in zip(coordinates, coordinates[1:]):
        intervals = region_intervals(a, b, region)
        if not intervals and current is not None:
            pieces.append(current)
            current = None
        for lo, hi, cut_in, cut_out in intervals:
            if lo > 0 and current is not None:
                pieces.append(current)
                current = None
            if current is None: current = [list(a) if lo == 0 else list(cut_in)]
            current.append(list(b) if hi == 1 else list(cut_out))
            if hi < 1:
                pieces.append(current)
                current = None
    if current is not None: pieces.append(current)
    return [piece for piece in pieces if geographic_length_m(piece) >= MIN_REGION_PIECE_M]


def explicit_parts(feature, selected, identity, region=None):
    """Clip in source traversal order; never join separate visits to the window.

    Heights interpolate only between two supplied node elevations. Synthetic cut
    IDs are local to this feature/segment; position equality is not connectivity.
    A polygonal `region` (rectangle ∩ selected areas) may cut one segment more than
    once; its cut IDs also carry the interval number.
    """
    p = feature["properties"]
    coordinates, refs = feature["geometry"]["coordinates"], p["osm_node_refs"]
    heights = p.get("elevations_m")

    def endpoint(a, b, index, t, side, cut, number):
        if t == 0: return list(a), refs[index], heights[index] if heights is not None else None
        if t == 1: return list(b), refs[index+1], heights[index+1] if heights is not None else None
        height = heights[index]+t*(heights[index+1]-heights[index]) if heights is not None else None
        if cut is not None: return list(cut), f"crop-{identity}-{index}-{number}-{side}", height
        point = [max(selected[k], min(selected[k+2], a[k]+t*(b[k]-a[k]))) for k in range(2)]
        # Preserve the selected boundary exactly (including corner ties),
        # rather than retaining cancellation error from a + t * delta.
        for axis in range(2):
            if b[axis] != a[axis]:
                for boundary in (selected[axis], selected[axis+2]):
                    if t == (boundary-a[axis])/(b[axis]-a[axis]): point[axis] = boundary
        return point, f"crop-{identity}-{index}-{side}", height

    current = None
    for index, (a, b) in enumerate(zip(coordinates, coordinates[1:])):
        if a == b:
            raise ValueError("OSM explicit crop has a zero-length source segment")
        if region is None:
            interval = segment_interval(a, b, selected)
            intervals = [] if interval is None else [(*interval, None, None)]
        else:
            intervals = region_intervals(a, b, region)
        if not intervals and current is not None:
            yield current, span
            current = None
        for number, (lo, hi, cut_in, cut_out) in enumerate(intervals):
            if lo > 0 and current is not None:
                yield current, span
                current = None
            start, end = endpoint(a, b, index, lo, "in", cut_in, number), endpoint(a, b, index, hi, "out", cut_out, number)
            if current is None:
                span = [index + lo, index + hi]
                current = dict(type="Feature", properties=dict(p, osm_node_refs=[start[1]]),
                               geometry=dict(type="LineString", coordinates=[start[0]]))
                if heights is not None: current["properties"]["elevations_m"] = [start[2]]
                if "osm_loop_range" in p: current["properties"]["osm_loop_range"] = [p["osm_loop_range"][0]+span[0],0]
            span[1] = index + hi
            current["geometry"]["coordinates"].append(end[0])
            current["properties"]["osm_node_refs"].append(end[1])
            if heights is not None: current["properties"]["elevations_m"].append(end[2])
            if "osm_loop_range" in p: current["properties"]["osm_loop_range"][1] = p["osm_loop_range"][0]+span[1]
            if hi < 1:
                yield current, span
                current = None
    if current is not None: yield current, span


def bounds(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("OSM bbox requires west/south/east/north")
    w, s, e, n = [number(v, "OSM bbox", -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84) for i, v in enumerate(value)]
    if not w < e or not s < n:
        raise ValueError("OSM bbox needs west < east and south < north")
    return [w, s, e, n]


def projected_bounds(value, coordinates):
    """Validate admission before scanning a large source, using the existing CRS/radius."""
    from projection import Coordinates
    w, s, e, n = bounds(value)
    projection = Coordinates(coordinates)
    if projection.mode != "wgs84-utm": raise ValueError("OSM crop requires WGS84 projection")
    for point in ([w,s], [w,n], [e,s], [e,n]): projection.point(point)
    return [w,s,e,n]


def crop(collection, selected, *, feature_limit=20_000, point_limit=None, region=None, areas=None):
    """Clip to the rectangle, or to rectangle ∩ `region` (the exact union of selected
    administrative boundaries, `areas` naming them) when one is given."""
    selected = bounds(selected)
    point_limit = MAX_POINTS if point_limit is None else point_limit
    if version("shapely") != "2.1.2":
        raise ValueError("OSM crop requires shapely 2.1.2; install requirements-import.txt")
    import shapely
    from shapely.geometry import shape, mapping
    window = shapely.box(*selected)
    if region is not None:
        window = shapely.make_valid(window.intersection(region))
        if window.is_empty or window.area == 0: raise ValueError("Selected areas do not overlap the crop rectangle")
        shapely.prepare(window)
    output, budget = [], SpatialBudget() if feature_limit > 20000 else Budget()
    counts = dict(input_features=len(collection["features"]), outside_features=0, changed_features=0, output_features=0, boundary_contacts=0)
    points = 0
    has_explicit = any("elevations_m" in f["properties"] for f in collection["features"])
    vertical_counts = dict(clipped_ground_features=0, outside_explicit_features=0, retained_structure_features=0)
    retained_structures, incomplete_structures = set(), set()
    structure_sources = []
    kept_chains = {f["properties"]["_city_estimated_chain"] for f in collection["features"]
                   if "_city_estimated_chain" in f["properties"] and shape(f["geometry"]).intersects(window)}
    connections = collection.get("osm_connections", [])
    source_ends = Counter((f["properties"]["osm_way_id"], ref) for f in collection["features"]
        if f["properties"].get("road_kind") in ("bridge", "tunnel")
        for ref in (f["properties"]["osm_node_refs"][0], f["properties"]["osm_node_refs"][-1]))
    source_ground_refs = {ref for f in collection["features"] if f["properties"].get("road_kind") == "ground"
                          for ref in f["properties"]["osm_node_refs"]}

    def append(feature):
        nonlocal points
        def count(value):
            if isinstance(value[0], (int, float)): return 1
            return sum(count(v) for v in value)
        points += count(feature["geometry"]["coordinates"])
        if points > point_limit:
            soft_limit("crop_points", points, point_limit, "OSM crop output position budget exceeded")
        if len(output) >= feature_limit:
            soft_limit("crop_features", len(output) + 1, feature_limit, "OSM crop output feature budget exceeded")
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
            if complete:
                # Retain exact vertex order/profile and original graph node IDs.
                append(feature)
                spans = [[0, len(p["osm_node_refs"])-1]]
            else:
                spans = []
                for part, span in explicit_parts(feature, selected, index, window if region is not None else None):
                    if region is not None and geographic_length_m(part["geometry"]["coordinates"]) < MIN_REGION_PIECE_M:
                        counts["boundary_contacts"] += 1
                        continue
                    append(part)
                    spans.append(span)
                if len(output) > before:
                    counts["changed_features"] += 1
                    if not structure and "elevations_m" in p: vertical_counts["clipped_ground_features"] += 1
            if structure:
                for offset, span in enumerate(spans):
                    retained_structures.add(p["osm_way_id"])
                    vertical_counts["retained_structure_features"] += 1
                    structure_sources.append(dict(feature=before+offset, source_feature=index,
                        source_way=str(p["osm_way_id"]), source_range=span))
            if len(output) == before:
                counts["outside_features"] += 1
                counts["boundary_contacts"] += source.intersects(window)
                if "elevations_m" in p: vertical_counts["outside_explicit_features"] += 1
            continue
        expected = "LineString" if source.geom_type == "LineString" else "Polygon"
        if region is not None and window.covers(source):
            # GEOS overlay against a many-vertex area may node a covered line at
            # every vertex; a covered source keeps its exact geometry instead.
            # Polygons drop repeated adjacent positions, as overlay would.
            clipped = source if expected == "LineString" else shapely.remove_repeated_points(source)
        elif expected == "LineString" and "_city_estimated_m" in feature["properties"]:
            # An estimated structure stays whole, with every way of its chain:
            # a cut would leave a deck end in the air and separate its profile
            # from its vertices.
            chain = feature["properties"].get("_city_estimated_chain")
            clipped = source if source.intersects(window) or chain in kept_chains else shapely.LineString()
        elif region is not None and expected == "LineString":
            pieces = region_line_parts(feature["geometry"]["coordinates"], window)
            clipped = shapely.MultiLineString(pieces)
            if not pieces and source.intersects(window): counts["boundary_contacts"] += 1
        else:
            clipped = source.intersection(window)
        geometries = parts(clipped, expected)
        if not geometries:
            counts["outside_features"] += 1
            continue
        counts["changed_features"] += not source.equals(clipped)
        if expected == "Polygon":
            # Shared normalizer retains holes, islands and stable part ordering.
            def grouped(items):
                return dict(type="MultiPolygon", coordinates=group_rings([list(map(list, g.exterior.coords)) for g in items],
                    [list(map(list, ring.coords)) for g in items for ring in g.interiors], budget))
            try:
                geometries_json = [grouped(geometries)]
            except ValueError as exc:
                # A concave area boundary can pinch one source into parts that touch
                # at a point; keep them as separate features instead of joining them.
                if region is None or "touch" not in str(exc): raise
                geometries_json = [grouped([g]) for g in geometries]
        else:
            geometries_json = [json.loads(json.dumps(mapping(g))) for g in geometries]
        for geometry in geometries_json:
            properties = feature["properties"]
            if not source.equals(clipped) and "_city_refs" in properties:
                # Cut vertices do not acquire a source-node identity. Such
                # boundary pieces are protected from cross-way chain merging.
                properties = {k:v for k,v in properties.items() if k != "_city_refs"}
                original = feature["geometry"]["coordinates"]
                refs = feature["properties"]["_city_refs"]
                properties["_city_ends"] = [str(refs[i]) if geometry["coordinates"][i] == original[i] else None for i in (0,-1)]
            append(dict(type="Feature", properties=properties, geometry=geometry))
    # A boundary-only contact is not a drivable approach. Check the retained graph,
    # not the complete source's earlier connectivity proof.
    ground_ends = {ref for f in output if f["properties"].get("road_kind") == "ground"
                   for ref in (f["properties"]["osm_node_refs"][0], f["properties"]["osm_node_refs"][-1])}
    for feature in output:
        p = feature["properties"]
        if p.get("road_kind") in ("bridge", "tunnel") and any(ref in source_ground_refs and ref not in ground_ends for ref in (p["osm_node_refs"][0], p["osm_node_refs"][-1])):
            raise ValueError("OSM crop removes a required nonzero explicit-height ground approach; expand bbox or add the neighbouring area")
    if not output: raise ValueError("OSM bbox contains no supported nonzero geometry")
    retained_connection_ends = Counter(str(ref) for f in output
        if f["properties"].get("road_kind") in ("bridge", "tunnel")
        for ref in (f["properties"]["osm_node_refs"][0], f["properties"]["osm_node_refs"][-1]))
    connection_sections = {entry["ref"] for entry in connections
        if 0 < retained_connection_ends[entry["ref"]] < len(entry.get("source_arms", [None, None]))}
    counts["output_features"] = len(output)
    meta = dict(bbox=selected, policy="geometry-intersection-v1", shapely="2.1.2", geos=shapely.geos_version_string, counts=counts)
    if region is not None: meta.update(region="administrative-union-v1", areas=list(areas or []), region_area_deg2=window.area)
    # A source vertex cut is also a section end when its other source-way arm
    # was removed. Retained original junctions continue to use their own ID.
    retained_ends = Counter((f["properties"]["osm_way_id"], ref) for f in output
        if f["properties"].get("road_kind") in ("bridge", "tunnel")
        for ref in (f["properties"]["osm_node_refs"][0], f["properties"]["osm_node_refs"][-1]))
    section_ends = 0
    for entry in structure_sources:
        p = output[entry["feature"]]["properties"]
        entry["partial"] = p["osm_way_id"] in incomplete_structures
        entry["endpoints"] = []
        for ref in (p["osm_node_refs"][0], p["osm_node_refs"][-1]):
            key = (p["osm_way_id"], ref)
            section = isinstance(ref, str) or (source_ends[key] != 1 and retained_ends[key] == 1) or str(ref) in connection_sections
            entry["endpoints"].append(dict(ref=str(ref), role="boundary-section" if section else "source-node"))
            section_ends += section
    meta["vertical"] = dict(profile="explicit-connected-structure-crop-v1", **vertical_counts,
        section_endpoints=section_ends, partial_structure_ways=len(retained_structures & incomplete_structures),
        structures=structure_sources, connection_sections=sorted(connection_sections))
    result = dict(type="FeatureCollection", features=output)
    if connections: result["osm_connections"] = connections
    if "osm_ground_loops" in collection: result["osm_ground_loops"] = collection["osm_ground_loops"]
    return result, meta
