#!/usr/bin/env python3
"""Explicit local-metre geometry adapter. Produces an unadopted ImportLayer."""
import argparse
import hashlib
import json
from osm_extract import PEDESTRIAN
from pathlib import Path
import sys
import uuid
import os
import threading
import time
from import_layer import ImportLayer, Source, MAX_INPUT, MAX_RECORDS, number, text, strict_json
from projection import Coordinates
from polygon_geometry import Budget, SpatialBudget, group_rings


MAX_COLLECTION_DEPTH = 16
MAX_COLLECTION_NODES = 40000
MAX_COLLECTION_LEAVES = 20000


def collection_features(features):
    """Preserve a bounded source tree while reusing the existing leaf adapters."""
    output, sources, leaves = [], [], []
    visited = 0
    def visit(geometry, properties, depth):
        nonlocal visited
        visited += 1
        if depth > MAX_COLLECTION_DEPTH or visited > MAX_COLLECTION_NODES:
            raise ValueError("GeometryCollection nesting/node budget exceeded")
        if not isinstance(geometry, dict) or "crs" in geometry:
            raise ValueError("GeometryCollection requires geometry objects without legacy CRS")
        kind = geometry.get("type")
        if kind == "GeometryCollection":
            children = geometry.get("geometries")
            if not isinstance(children, list) or not children or "coordinates" in geometry:
                raise ValueError("GeometryCollection requires a nonempty geometries array, without coordinates")
            # Admission precedes allocation and recursion into the children.
            if visited + len(children) > MAX_COLLECTION_NODES:
                raise ValueError("GeometryCollection node budget exceeded")
            return [visit(child, properties, depth+1) for child in children]
        if kind not in ("LineString", "MultiLineString", "Polygon", "MultiPolygon"):
            raise ValueError("GeometryCollection contains unsupported geometry; no partial import")
        if len(output) >= MAX_COLLECTION_LEAVES:
            raise ValueError("GeometryCollection leaf budget exceeded")
        index = len(output)
        output.append(dict(type="Feature", properties=properties, geometry=geometry))
        leaves.append(dict(feature=index, geometry=kind))
        return index
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or "crs" in feature:
            raise ValueError("GeometryCollection requires Features without legacy CRS")
        properties = feature.get("properties")
        if properties is None: properties = {}
        if not isinstance(properties, dict): raise ValueError("expected properties object")
        if any(key in properties for key in ("osm_node_refs", "elevations_m", "road_kind", "clearance_m")):
            raise ValueError("GeometryCollection does not support structural/OSM graph metadata")
        sources.append(dict(feature=index, tree=visit(feature.get("geometry"), properties, 0)))
    return output, dict(profile="feature-leaves-v1", sources=sources, leaves=leaves)


def convert(value, source, license_name, *, layer_id=None, source_bytes=None, accuracy="unknown", progress=None, coordinates=None, osm_graph=False, captured_source=None, city=False):
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection" or "crs" in value:
        raise ValueError("expected FeatureCollection without legacy CRS; coordinates must be explicitly selected")
    raw = b"" if captured_source is not None else source_bytes if source_bytes is not None else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    transform = Coordinates(coordinates)
    topology_budget = Budget()
    layer = ImportLayer(layer_id or uuid.uuid4().hex, captured_source or Source(source, hashlib.sha256(raw).hexdigest(), len(raw), license_name, accuracy), transform.metadata, adapter="geojson-v1")
    features = value.get("features")
    from import_layer import CITY_FEATURES
    limit = CITY_FEATURES if city else 20_000
    if not isinstance(features, list) or not 1 <= len(features) <= limit:
        raise ValueError(f"expected 1..{limit} features")
    collections = any(isinstance(f, dict) and isinstance(f.get("geometry"), dict) and
                      f["geometry"].get("type") == "GeometryCollection" for f in features)
    if collections:
        if osm_graph: raise ValueError("GeometryCollection does not support the OSM graph conversion path")
        features, metadata = collection_features(features)
        layer.coordinates["geojson_collections"] = metadata
    layer.feature_count = len(features)
    city_sources = sorted({identity for feature in features for identity in feature.get("properties", {}).get("_city_sources", [])})
    city_indices = {identity:index for index,identity in enumerate(city_sources)}
    if city_sources:
        layer.coordinates["city_source_ids"] = city_sources
        topology_budget = SpatialBudget()

    def point(raw):
        p = transform.point(raw)
        layer.point(*p)
        return p

    graph_nodes = {}
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("expected Feature")
        geometry, properties = feature.get("geometry"), feature.get("properties")
        if properties is None:
            properties = {}
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            raise ValueError("expected geometry and properties objects")
        kind, coordinates = geometry.get("type"), geometry.get("coordinates")
        if not isinstance(coordinates, list):
            raise ValueError("expected coordinate array")
        identity = f"import-{layer.layer_id}-{index}" + ("-collection" if collections else "")
        first_record, first_point = len(layer.patches), layer.point_count

        def scalar(key, default, minimum=-100_000, maximum=100_000):
            if key not in properties:
                layer.estimate(key)
            return number(properties.get(key, default), key, minimum, maximum)

        if kind in ("LineString", "MultiLineString"):
            lines = [coordinates] if kind == "LineString" else coordinates
            if not lines:
                raise ValueError("MultiLineString requires at least one line")
            if kind == "MultiLineString":
                # This is authored ground geometry, never an implicit OSM graph.
                if osm_graph or any(key in properties for key in ("osm_node_refs", "elevations_m", "road_kind", "clearance_m")):
                    raise ValueError("MultiLineString does not support structural/OSM graph metadata")
                if len(layer.patches) + 3 * len(lines) > MAX_RECORDS:
                    raise ValueError("import record budget exceeded by MultiLineString parts")
                mapping = dict(feature=index, road_ids=[], point_counts=[])
                layer.coordinates.setdefault("geojson_multilines", dict(profile="disconnected-parts-v1", features=[]))["features"].append(mapping)
            for part, line in enumerate(lines):
                if not isinstance(line, list) or len(line) < 2:
                    raise ValueError("road requires an array of at least two positions")
                road_id = identity if kind == "LineString" else f"{identity}-part-{part}"
                if osm_graph and "osm_loop_range" in properties: road_id += "-loop"
                if not osm_graph and any(key in properties for key in ("osm_node_refs", "elevations_m", "road_kind", "clearance_m")):
                    raise ValueError("Structural/OSM graph metadata requires the OSM conversion path; no silent flattening")
                explicit = osm_graph and "elevations_m" in properties
                # City structures with estimated heights join ordinary ground roads.
                estimated = osm_graph and "_city_estimated_m" in properties
                connected = osm_graph and "osm_node_refs" in properties
                # City ground lies on the flat map plane, where estimated structure
                # anchors meet it; other profiles keep the 0.2 m estimate.
                elevations = properties["elevations_m"] if explicit else properties["_city_estimated_m"] if estimated else [scalar("elevation_m", 0.0 if city and osm_graph else 0.2)] * len(line)
                if not isinstance(elevations, list) or len(elevations) != len(line):
                    raise ValueError("road elevation profile must match coordinates")
                points = [[p[0], round(number(h, "road elevation", -10000 if explicit or estimated else -100000, 10000 if explicit or estimated else 100000) * 100), p[1]] for p,h in zip(map(point, line), elevations)]
                level = scalar("level", 0, -100, 100)
                if int(level) != level:
                    raise ValueError("level must be integral")
                walking = osm_graph and properties.get("_city_road_tags", {}).get("highway") in PEDESTRIAN and not estimated
                # Pedestrian ways keep independent ends; only vehicle roads share source junctions.
                ground_refs = properties.get("_city_ends") if osm_graph and not connected and not walking else None
                endpoints = []
                for offset, suffix, p in [(0, "from", points[0]), (-1, "to", points[-1])]:
                    node_id = f"import-{layer.layer_id}-osm-node-{properties['osm_node_refs'][offset]}" if connected else road_id + "-" + suffix
                    if ground_refs and ground_refs[offset]: node_id = f"import-{layer.layer_id}-osm-ground-node-{ground_refs[offset]}"
                    record = {"id": node_id, "position": p, "level": int(level)}
                    if node_id in graph_nodes and graph_nodes[node_id] != record:
                        raise ValueError(f"OSM shared node has conflicting geometry: {node_id} at {graph_nodes[node_id]['position']} and {record['position']}")
                    if node_id not in graph_nodes:
                        layer.add("nodes", record)
                        graph_nodes[node_id] = record
                    endpoints.append(node_id)
                width = round(scalar("width_m", 8, 0.01, 1000) * 100)
                surface = text(properties.get("surface", "asphalt"), "surface", 64)
                if "surface" not in properties: layer.estimate("surface")
                structure = properties["road_kind"] if explicit else properties["_city_estimated_kind"] if estimated else "ground"
                clearance = properties.get("clearance_m") if explicit else properties.get("_city_estimated_clearance_m") if estimated else None
                layer.add("roads", {"id": road_id, "from": endpoints[0], "to": endpoints[1], "points": points,
                    "widths_cm": [width] * (len(points) - 1), "surfaces": [surface] * (len(points) - 1), "kind": structure, "clearance_cm": round(clearance * 100) if clearance is not None else None, "sidewalk_cm": None})
                if estimated:
                    layer.coordinates.setdefault("osm_estimated_structures", []).append(road_id)
                if ground_refs:
                    layer.coordinates.setdefault("osm_ground_endpoints", []).append(dict(road_id=road_id,refs=ground_refs))
                if walking:
                    layer.coordinates.setdefault("osm_pedestrian_roads", []).append(road_id)
                if not connected and not ground_refs and not walking:
                    label = str(index) if kind == "LineString" else f"{index} part {part}"
                    layer.warning(f"{label}: disconnected endpoints; connect explicitly in Editor")
                if kind == "MultiLineString":
                    mapping["road_ids"].append(road_id)
                    mapping["point_counts"].append(len(points))
        elif kind in ("Polygon", "MultiPolygon"):
            polygons = [coordinates] if kind == "Polygon" else coordinates
            if not polygons:
                raise ValueError("polygon geometry must be nonempty")
            projected = []
            for rings in polygons:
                if not isinstance(rings, list) or not rings:
                    raise ValueError("polygon requires an outer ring")
                output = []
                for ring in rings:
                    if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                        raise ValueError("polygon ring must be closed with at least four positions")
                    points = list(map(point, ring[:-1]))
                    output.append(points + [points[0]])
                projected.append(output)
            if kind == "MultiPolygon" or any(len(rings) > 1 for rings in projected):
                try:
                    regrouped = group_rings([rings[0] for rings in projected], [hole for rings in projected for hole in rings[1:]], topology_budget)
                except ValueError as exc:
                    raise ValueError(f"{properties.get('osm_source_id', index)}: {exc}") from exc
                if regrouped != projected:
                    raise ValueError("polygon holes must belong to their declared outer after projection")
            zone = properties.get("landuse") in ("forest", "orchard")
            for part, rings in enumerate(projected):
                part_id = identity if kind == "Polygon" else f"{identity}-part-{part}"
                polygon = rings[0][:-1]
                if osm_graph and properties.get("osm_region"):
                    layer.coordinates.setdefault("generation_regions", []).append(dict(
                        id=part_id, source_id=properties["osm_source_id"], landuse=properties["landuse"],
                        polygon=polygon, holes=[hole[:-1] for hole in rings[1:]],
                        protected=properties.get("protected", False), tags=properties.get("region_tags", {})))
                    if not zone: continue
                if properties.get("_city_paint"):
                    if not (city and osm_graph) or len(rings) > 1 or properties["_city_paint"] not in ("asphalt", "concrete", "dirt", "gravel", "grass"):
                        raise ValueError("City ground paint must be one hole-free current-v1 surface polygon")
                    layer.add("surface_areas", {"id": part_id, "polygon": polygon, "surface": properties["_city_paint"]})
                elif zone:
                    layer.add("zones", {"id": part_id, "polygon": polygon, "kind": properties["landuse"], "spacing_cm": 3200 if city else 800, "density_per_mille": 750, "exclusions": [hole[:-1] for hole in rings[1:]]})
                    layer.estimate("vegetation_spacing_density")
                else:
                    usage = text(properties.get("usage", "unknown"), "usage", 64)
                    if usage not in ("residential", "commercial", "industrial", "public"):
                        usage = "residential"
                        layer.estimate("usage")
                        layer.warning("Unclassified building use is represented as residential; review before adoption. Original source classification is retained in the source file.")
                    if len(rings) > 1:
                        if len(rings) > 17 or sum(len(r)-1 for r in rings) > 512:
                            raise ValueError("courtyard supports at most 16 holes and 512 total vertices")
                        layer.warning("Building courtyard uses the current flat-roof profile.")
                    layer.add("buildings", {"id": part_id, "footprint": polygon,
                        **({"holes": [hole[:-1] for hole in rings[1:]]} if len(rings) > 1 else {}),
                        "base_cm": round(scalar("base_m", 0) * 100), "height_cm": round(scalar("height_m", 12, 0.01, 1000) * 100),
                        "usage": text(usage, "usage", 64), "material": "concrete", "roof": "flat"})
                    layer.estimate("material_roof")
        else:
            raise ValueError(f"unsupported geometry {kind}; no features imported")
        if osm_graph and properties.get("osm_source_id") and not properties.get("_city_sources"):
            layer.coordinates.setdefault("source_objects", []).append(dict(source_id=properties["osm_source_id"],
                record_ids=[p["id"] for p in layer.patches[first_record:]]))
        if osm_graph and properties.get("_city_sources"):
            # Patches for one feature are a contiguous range. Reference that
            # range and one shared source-ID table instead of repeating long
            # layer-qualified record IDs thousands of times in provenance.
            mapping = dict(sources=[city_indices[s] for s in properties["_city_sources"]], records=[first_record,len(layer.patches)-first_record])
            if properties.get("_city_name"): mapping["name"] = properties["_city_name"]
            if properties.get("_city_estimated_height"): mapping["estimated_height"] = True
            if properties.get("_city_names"): mapping["names"] = properties["_city_names"]
            layer.coordinates.setdefault("city_mappings", []).append(mapping)
            if properties.get("_city_estimated_height"):
                layer.estimate("aggregated_building_height")
        if collections:
            metadata["leaves"][index].update(record_ids=[p["id"] for p in layer.patches[first_record:]],
                                              point_count=layer.point_count-first_point)
        if progress and (index % 100 == 0 or index + 1 == len(features)):
            progress(index + 1, len(features))
    if collections:
        layer.warning("GeoJSON GeometryCollection leaves preserve source tree order and parent feature properties. Lines remain disconnected; polygons use existing building/vegetation profiles. Every source tree and exact output mapping is retained. Unsupported or empty leaves reject the whole candidate.")
    if osm_graph and value.get("osm_ground_loops"):
        retained = []
        for index, feature in enumerate(features):
            p = feature["properties"]
            if "osm_loop_range" not in p: continue
            retained.append(dict(road_id=f"import-{layer.layer_id}-{index}-loop", source_way=str(p["osm_way_id"]),
                source_range=p["osm_loop_range"], refs=list(map(str,p["osm_node_refs"])), explicit_height="elevations_m" in p))
            if "_city_loop_positions" in p: retained[-1]["source_positions"] = p["_city_loop_positions"]
        layer.coordinates["osm_ground_loops"] = dict(value["osm_ground_loops"], retained=retained)
    if osm_graph and value.get("osm_connections"):
        # Keep original source joins even when neither arm survives the crop.
        # Map each retained arm to the exact normalized output feature/way.
        retained = {}
        for index, feature in enumerate(features):
            p = feature["properties"]
            if p.get("road_kind") not in ("bridge", "tunnel"): continue
            for end, ref in (("from", p["osm_node_refs"][0]), ("to", p["osm_node_refs"][-1])):
                retained.setdefault(str(ref), []).append(dict(feature=index, source_way=str(p["osm_way_id"]), end=end))
        joins = []
        for entry in value["osm_connections"]:
            arms = retained.get(entry["ref"], [])
            joins.append(dict(entry, retained=arms))
        layer.coordinates["osm_connections"] = dict(profile="explicit-structural-junctions-v1", joins=joins)
    layer.encode()  # Bound the complete contract before handing it to any caller.
    return layer


def watch_parent_lifetime(timeout=120):
    # EOF terminates this helper if its owner exits/crashes. No grandchildren.
    def watch_parent():
        while os.read(sys.stdin.fileno(), 1):
            pass
        os._exit(3)
    threading.Thread(target=watch_parent, daemon=True).start()
    def watchdog():
        time.sleep(timeout)
        os._exit(4)
    threading.Thread(target=watchdog, daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--coordinates", required=True, choices=["local-metres", "wgs84-utm"])
    parser.add_argument("--license", required=True)
    parser.add_argument("--origin", nargs=2, type=float)
    parser.add_argument("--local-origin", nargs=2, type=float)
    parser.add_argument("--accuracy", default="unknown")
    parser.add_argument("--source-name")
    parser.add_argument("--layer-id", required=True)
    parser.add_argument("--watch-parent", action="store_true")
    parser.add_argument("--input-format", choices=["geojson", "pbf", "osm", "overture", "overture-transportation", "overture-land-cover", "csv"], default="geojson")
    parser.add_argument("--csv-request", type=Path)
    parser.add_argument("--osm-bbox", nargs=4, type=float)
    parser.add_argument("--osm-stream", action="store_true")
    parser.add_argument("--osm-city", action="store_true")
    parser.add_argument("--osm-areas", nargs="+", type=int)
    parser.add_argument("--osm-review-exclusions", action="store_true")
    parser.add_argument("--vertical-request", type=Path)
    parser.add_argument("--height-supplement", type=Path)
    args = parser.parse_args()
    if args.height_supplement is not None and args.input_format not in ("osm", "pbf"):
        raise ValueError("height supplements require OSM input")
    if args.vertical_request is not None and args.input_format not in ("osm", "pbf"):
        raise ValueError("vertical conversion is only supported for explicit OSM heights")
    if args.osm_bbox is not None and args.input_format not in ("osm", "pbf"):
        raise ValueError("OSM bbox is only valid for OSM PBF/XML")
    if args.osm_stream and (args.input_format != "pbf" or args.osm_bbox is None):
        raise ValueError("PBF streaming requires PBF input and an explicit bbox")
    if args.osm_review_exclusions and not args.osm_stream:
        raise ValueError("Object exclusion review requires PBF streaming")
    if args.osm_areas and not args.osm_stream:
        raise ValueError("Administrative area crops require PBF streaming")
    if args.osm_city and not args.osm_stream:
        raise ValueError("Automatic city optimization requires PBF streaming")
    from osm_review import Review
    review = Review(args.osm_review_exclusions)
    if args.osm_bbox is not None:
        from osm_area import projected_bounds
        projected_bounds(args.osm_bbox, dict(mode=args.coordinates, origin=args.origin, local_origin_m=args.local_origin))
    if args.watch_parent:
        watch_parent_lifetime(900 if args.osm_stream else 120)
    sequence = 0
    def event(stage, completed, total, unit="bytes", **extra):
        nonlocal sequence
        sequence += 1
        print(json.dumps(dict(request=args.layer_id, seq=sequence, stage=stage, completed=completed, total=total, unit=unit, **extra)), flush=True)
    supplement = None
    if args.height_supplement is not None:
        from osm_heights import Supplement, read_source
        supplement = Supplement(read_source(args.height_supplement))
    size = args.source.stat().st_size
    raw = None
    if not args.osm_stream:
        if size > MAX_INPUT: raise ValueError("input exceeds 32 MiB; select PBF streaming with a bbox")
        event("read", 0, size)
        with args.source.open("rb") as stream:
            raw = stream.read(MAX_INPUT + 1)
        if len(raw) != size: raise ValueError("source size changed during read; retry")
        event("read", len(raw), size)
        event("parse", 0, size)
    osm_crop = None
    osm_counts = None
    overture_metadata = None
    osm_stream = None
    region = None
    captured_source = None
    vertical = None
    if args.input_format == "csv":
        value = None
    elif args.input_format == "geojson":
        value = strict_json(raw)
    elif args.input_format == "overture-transportation":
        from overture_transportation import parse, LICENSE
        if args.coordinates != "wgs84-utm" or args.license != LICENSE:
            raise ValueError("Transportation requires WGS84 origins and source attribution")
        value = parse(raw)
    elif args.input_format == "overture-land-cover":
        from overture_land_cover import parse, LICENSE
        if args.coordinates != "wgs84-utm" or args.license != LICENSE:
            raise ValueError("Land cover requires WGS84 origins and source attribution")
        value, overture_metadata = parse(raw)
    elif args.input_format == "overture":
        from overture_area import parse, LICENSE
        if args.coordinates != "wgs84-utm" or args.license != LICENSE:
            raise ValueError("Overture requires WGS84 origins and source attribution")
        value, overture_metadata = parse(raw)
    else:
        from osm_extract import parse, LICENSE
        if args.coordinates != "wgs84-utm":
            raise ValueError("OSM requires explicit WGS84 origin and local map origin")
        if args.license != LICENSE:
            raise ValueError("OSM attribution must retain OpenStreetMap contributors and ODbL-1.0")
        if args.osm_stream:
            from osm_stream import extract
            value, osm_counts, osm_stream = extract(args.source,args.osm_bbox,args.output.parent,event,supplement,review,city=args.osm_city,areas=args.osm_areas)
            region = osm_stream.pop("_region", None)
            captured_source = Source(args.source_name or args.source.name, osm_stream["source_sha256"], osm_stream["source_bytes"], args.license, args.accuracy)
        else:
            value, osm_counts = parse(raw, args.input_format, supplement)
        from vertical import Vertical, read_options
        vertical = Vertical(read_options(args.vertical_request) if args.vertical_request is not None else
            dict(target="EGM96", zero_m=0, grid=None))
        value = vertical.apply(value)
        if args.osm_bbox is not None:
            from osm_area import crop
            if args.osm_city:
                from osm_stream import CITY_FEATURES, CITY_POINTS
                value, osm_crop = crop(value, args.osm_bbox, feature_limit=CITY_FEATURES, point_limit=CITY_POINTS, region=region, areas=osm_stream.get("areas"))
            else:
                value, osm_crop = crop(value, args.osm_bbox, region=region, areas=osm_stream.get("areas") if osm_stream else None)
    parse_bytes = osm_stream["selected"]["bytes"] if osm_stream else size
    event("parse", parse_bytes, parse_bytes)
    options = {"mode": args.coordinates}
    if args.coordinates == "wgs84-utm":
        options.update(origin=args.origin, local_origin_m=args.local_origin)
    elif args.origin is not None or args.local_origin is not None:
        raise ValueError("local-metre mode must not specify geographic origins")
    city_meta = None
    encoded = None
    if args.osm_city:
        from copy import deepcopy
        from osm_generalize import candidates, LEVELS
        from import_layer import CITY_FEATURES as OUTPUT_FEATURES, CITY_POINTS as OUTPUT_POINTS, CITY_OUTPUT
        from osm_extract import finish
        for index, feature in enumerate(value["features"]):
            feature["properties"]["_city_crop_feature"] = index
        error = "City geometry cannot fit the current output budget while preserving protected objects"
        event("optimize", 0, len(LEVELS), "steps")
        result = None
        for attempt, (candidate, metadata) in enumerate(candidates(value, options, review)):
            event("optimize", attempt+1, len(LEVELS), "steps", features=metadata["after"]["features"], positions=metadata["after"]["positions"], gap_m=metadata["gap_m"], categories=metadata["after"])
            if metadata["after"]["features"] > OUTPUT_FEATURES or metadata["after"]["positions"] > OUTPUT_POINTS:
                continue
            try:
                trial = convert(candidate, args.source_name or args.source.name, args.license, layer_id=args.layer_id,
                    accuracy=args.accuracy, coordinates=options, osm_graph=True, captured_source=captured_source, city=True)
                metadata["groups"] = trial.coordinates.pop("city_mappings")
                if metadata["source_ids"] != trial.coordinates.pop("city_source_ids"):
                    raise ValueError("City source table changed during conversion")
                trial.coordinates["osm_city"] = metadata
                trial.coordinates["vertical"] = vertical.metadata
                trial.coordinates["osm_stream"] = osm_stream
                if supplement is not None: trial.coordinates["osm_height_supplement"] = supplement.metadata
                if review.enabled: trial.coordinates["osm_review"] = review.metadata()
                trial_crop = deepcopy(osm_crop)
                remap = {f["properties"].get("_city_crop_feature"): i for i,f in enumerate(candidate["features"]) if "osm_node_refs" in f["properties"]}
                for structure in trial_crop["vertical"]["structures"]:
                    structure["feature"] = remap[structure["feature"]]
                trial_crop["counts"]["pre_optimization_output_features"] = trial_crop["counts"]["output_features"]
                trial_crop["counts"]["output_features"] = trial.feature_count
                trial.coordinates["osm_crop"] = trial_crop
                trial = finish(trial, osm_counts)
                trial.warning(f"Automatic city optimization at 1:8: {metadata['before']['features']} → {metadata['after']['features']} features; {metadata['before']['positions']} → {metadata['after']['positions']} positions. Gap filling up to {metadata['gap_m']} source metres; inspect approximated blocks and heights.")
                if len(osm_stream.get("areas", [])) > 1:
                    trial.warning(f"Combined {len(osm_stream['areas'])} administrative areas at their exact boundaries. DEM terrain is optional; Copernicus tiles beyond 64 MiB, four tiles or 1025² samples are refused and the map stays flat.")
                trial.warning("City source-block indexing retains complete selected ways, relation members and source graph closure. Original PBF hash, every retained source ID and output mapping are preserved; unsupported exclusions are separate. Crop ends are artificial; no bridge/tunnel heights are inferred.")
                encoded_trial = trial.encode()
                # Godot's JSON representation includes separator spaces. Its
                # boundary budget applies to that representation as well as
                # the compact wire file, so measure both before selecting.
                editor_bytes = len(json.dumps(trial.data(), sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
                if editor_bytes > CITY_OUTPUT - 65536:
                    raise ValueError(f"City Editor representation budget exceeded ({editor_bytes} bytes)")
            except ValueError as exc:
                if not any(reason in str(exc).lower() for reason in ("budget", "multipolygon", "polygon ring", "boundaries intersect", "ring is")):
                    raise
                error = str(exc)
                continue
            result, city_meta, encoded = trial, metadata, encoded_trial
            # Leave room for bounded source provenance and the atomic command.
            # Object merging alone can retain nearly every bend/vertex and
            # still overload native city cells. Prefer a candidate which also
            # reduces geometric detail, within the disclosed fixed tolerances.
            if len(encoded_trial) <= 24 * 1024**2 and metadata["after"]["features"] <= metadata["before"]["features"] * 0.8 and metadata["after"]["positions"] <= metadata["before"]["positions"] * 0.7:
                break
        if result is None:
            raise ValueError(error + "; no supported object was silently dropped")
        event("optimize", len(LEVELS), len(LEVELS), "steps")
        event("convert", result.feature_count, result.feature_count, "features")
    elif args.input_format == "csv":
        from facility_csv import convert as convert_csv
        if args.csv_request is None or args.csv_request.stat().st_size > 65536: raise ValueError("CSV mapping is required and must be bounded")
        result = convert_csv(raw, args.source_name or args.source.name, args.license, args.accuracy,
            args.layer_id, options, strict_json(args.csv_request.read_bytes()), lambda c,t:event("convert",c,t,"features"))
    elif args.input_format == "overture-transportation":
        from overture_transportation import convert as convert_transportation
        result = convert_transportation(value, args.source_name or args.source.name, raw,
            layer_id=args.layer_id, coordinates=options, accuracy=args.accuracy,
            progress=lambda c,t:event("convert",c,t,"features"))
    else:
        result = convert(value, args.source_name or args.source.name, args.license, layer_id=args.layer_id, source_bytes=raw, accuracy=args.accuracy,
            progress=lambda completed, total: event("convert", completed, total, "features"), coordinates=options, osm_graph=osm_counts is not None, captured_source=captured_source)
    if osm_counts is not None and not args.osm_city:
        from osm_extract import finish
        result.coordinates["vertical"] = vertical.metadata
        if supplement is not None:
            result.coordinates["osm_height_supplement"] = supplement.metadata
        result = finish(result, osm_counts)
        if osm_stream is not None:
            result.coordinates["osm_stream"] = osm_stream
            result.warnings.insert(0,"PBF area streaming: complete candidate envelopes, relation members and connected structures precede crop. Source/index/work quotas stay enforced. Unselected metadata is not interpreted. Unsupported selected or unlocated feature relations require explicit exclusion review. Three disk-indexed passes; full captured source hash retained.")
            result.warning_count += 1
        if review.enabled:
            result.coordinates["osm_review"] = review.metadata()
            result.warning(f"Explicit exclusion review: {len(review.excluded)} source objects are not imported. See every source ID and reason in exact details.")
        if osm_crop is not None:
            result.coordinates["osm_crop"] = osm_crop
            if osm_crop["vertical"]["section_endpoints"] > 0:
                result.warnings.insert(0, "Partial bridge/tunnel crop: boundary-section ends are open truncated cross-sections, not surveyed entrances or ground ramps. Width/deck/ceiling/walls use the existing native corridor and may extend beyond the centreline bbox. Original retained ground junctions still need nonzero approaches. Review source-way/range/endpoints in crop provenance; no outside continuation or datum alignment is inferred.")
                result.warning_count += 1
            elif "vertical" in osm_crop:
                result.warnings.insert(0, "OSM ground crop interpolates reviewed target-datum heights at WGS84 segment cuts; source heights are references, ground still follows map terrain. Original node IDs stay connected; new boundary cuts are separate endpoints. Complete bridge/tunnel spans and nonzero ground approaches are required; no extra terrain fitting is inferred.")
                result.warning_count += 1
            crop_summary = "OSM crop counts: " + json.dumps({"features":osm_crop["counts"],"vertical":{k:v for k,v in osm_crop["vertical"].items() if k not in ("structures","connection_sections","profile")}},sort_keys=True) + "; source mappings in projection provenance."
            result.warnings.insert(0, crop_summary)
            result.warning_count += 1
            result.warnings = result.warnings[:50]
    if overture_metadata is not None:
        if args.input_format == "overture-land-cover":
            from overture_land_cover import finish
        else:
            from overture_area import finish
        result = finish(result, overture_metadata)
    if encoded is None:  # The selected city trial was encoded unchanged.
        encoded = result.encode()
    event("write", 0, len(encoded))
    with args.output.open("xb") as stream:
        stream.write(encoded)
    event("write", len(encoded), len(encoded))
    event("complete", len(encoded), len(encoded), sha256=hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)[:1024]}), file=sys.stderr)
        sys.exit(1)
