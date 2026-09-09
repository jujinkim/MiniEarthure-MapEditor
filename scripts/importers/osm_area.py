"""Bounded derived geometry crop; captured OSM bytes are never rewritten."""
from importlib.metadata import version
import json
from import_layer import number, MAX_POINTS
from polygon_geometry import Budget, group_rings


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
    def parts(geometry, expected):
        if geometry.is_empty: return []
        if geometry.geom_type == expected: return [geometry]
        if geometry.geom_type.startswith("Multi") or geometry.geom_type == "GeometryCollection":
            return [p for child in geometry.geoms for p in parts(child, expected)]
        # Point/line-only contacts have no road length / polygon area.
        counts["boundary_contacts"] += 1
        return []
    for feature in collection["features"]:
        source = shape(feature["geometry"])
        if not source.is_valid or source.is_empty:
            raise ValueError("Invalid OSM geometry before crop; no repair or silent filtering")
        if source.bounds[2]-source.bounds[0] > 180:
            raise ValueError("OSM antimeridian geometry is unsupported")
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
            def count(value):
                if isinstance(value[0], (int, float)): return 1
                return sum(count(v) for v in value)
            points += count(geometry["coordinates"])
            if points > MAX_POINTS or len(output) >= 20_000:
                raise ValueError("OSM crop output budget exceeded")
            output.append(dict(type="Feature", properties=feature["properties"], geometry=geometry))
    if not output: raise ValueError("OSM bbox contains no supported nonzero geometry")
    counts["output_features"] = len(output)
    meta = dict(bbox=selected, policy="geometry-intersection-v1", shapely="2.1.2", geos=shapely.geos_version_string, counts=counts)
    return dict(type="FeatureCollection", features=output), meta
