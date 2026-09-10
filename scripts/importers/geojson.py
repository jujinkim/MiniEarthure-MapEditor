#!/usr/bin/env python3
"""Explicit local-metre geometry adapter. Produces an unadopted ImportLayer."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import os
import threading
import time
from import_layer import ImportLayer, Source, MAX_INPUT, number, text, strict_json
from projection import Coordinates
from polygon_geometry import Budget, group_rings


def convert(value, source, license_name, *, layer_id=None, source_bytes=None, accuracy="unknown", progress=None, coordinates=None, osm_graph=False, captured_source=None):
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection" or "crs" in value:
        raise ValueError("expected FeatureCollection without legacy CRS; coordinates must be explicitly selected")
    raw = b"" if captured_source is not None else source_bytes if source_bytes is not None else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    transform = Coordinates(coordinates)
    topology_budget = Budget()
    layer = ImportLayer(layer_id or uuid.uuid4().hex, captured_source or Source(source, hashlib.sha256(raw).hexdigest(), len(raw), license_name, accuracy), transform.metadata, adapter="geojson-v2")
    features = value.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 20_000:
        raise ValueError("expected 1..20000 features")
    layer.feature_count = len(features)

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
        identity = f"import-{layer.layer_id}-{index}"

        def scalar(key, default, minimum=-100_000, maximum=100_000):
            if key not in properties:
                layer.estimate(key)
            return number(properties.get(key, default), key, minimum, maximum)

        if kind == "LineString":
            if "osm_node_refs" in properties and not osm_graph:
                raise ValueError("OSM graph metadata requires the OSM conversion path; no silent flattening")
            explicit = osm_graph and "elevations_m" in properties
            elevations = properties.get("elevations_m") if explicit else [scalar("elevation_m", 0.2)] * len(coordinates)
            if not isinstance(elevations, list) or len(elevations) != len(coordinates):
                raise ValueError("road elevation profile must match coordinates")
            points = [[p[0], round(number(h, "road elevation", -10000 if explicit else -100000, 10000 if explicit else 100000) * 100), p[1]] for p,h in zip(map(point, coordinates), elevations)]
            if len(points) < 2:
                raise ValueError("road requires two points")
            level = scalar("level", 0, -100, 100)
            if int(level) != level:
                raise ValueError("level must be integral")
            endpoints = []
            for offset, suffix, p in [(0, "from", points[0]), (-1, "to", points[-1])]:
                node_id = f"import-{layer.layer_id}-osm-node-{properties['osm_node_refs'][offset]}" if explicit else identity + "-" + suffix
                record = {"id": node_id, "position": p, "level": int(level)}
                if node_id in graph_nodes and graph_nodes[node_id] != record:
                    raise ValueError("OSM shared node has conflicting geometry")
                if node_id not in graph_nodes:
                    layer.add("nodes", record)
                    graph_nodes[node_id] = record
                endpoints.append(node_id)
            width = round(scalar("width_m", 8, 0.01, 1000) * 100)
            surface = text(properties.get("surface", "asphalt"), "surface", 64)
            if "surface" not in properties: layer.estimate("surface")
            layer.add("roads", {"id": identity, "from": endpoints[0], "to": endpoints[1], "points": points,
                "widths_cm": [width] * (len(points) - 1), "surfaces": [surface] * (len(points) - 1), "kind": properties["road_kind"] if explicit else "ground", "clearance_cm": round(properties["clearance_m"] * 100) if explicit and "clearance_m" in properties else None, "sidewalk_cm": None})
            if not explicit: layer.warning(f"{index}: disconnected endpoints; connect explicitly in Editor")
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
                regrouped = group_rings([rings[0] for rings in projected], [hole for rings in projected for hole in rings[1:]], topology_budget)
                if regrouped != projected:
                    raise ValueError("polygon holes must belong to their declared outer after projection")
            zone = properties.get("landuse") in ("forest", "orchard")
            for part, rings in enumerate(projected):
                part_id = identity if kind == "Polygon" else f"{identity}-part-{part}"
                polygon = rings[0][:-1]
                if zone:
                    layer.add("zones", {"id": part_id, "polygon": polygon, "kind": properties["landuse"], "spacing_cm": 800, "density_per_mille": 750, "exclusions": [hole[:-1] for hole in rings[1:]]})
                    layer.estimate("vegetation_spacing_density")
                else:
                    usage = properties.get("usage", "unknown")
                    if len(rings) > 1:
                        if len(rings) > 17 or sum(len(r)-1 for r in rings) > 512:
                            raise ValueError("courtyard supports at most 16 holes and 512 total vertices")
                        if usage not in ("residential", "commercial", "industrial", "public"):
                            usage = "residential"
                            layer.estimate("courtyard_usage")
                        layer.warning("Building courtyard requires explicit recipe 5 and flat roof; choose recipe 5 before review/adoption.")
                    layer.add("buildings", {"id": part_id, "footprint": polygon,
                        **({"holes": [hole[:-1] for hole in rings[1:]]} if len(rings) > 1 else {}),
                        "base_cm": round(scalar("base_m", 0) * 100), "height_cm": round(scalar("height_m", 12, 0.01, 1000) * 100),
                        "usage": text(usage, "usage", 64), "material": "concrete", "roof": "flat"})
                    layer.estimate("material_roof")
                    if "usage" not in properties: layer.estimate("usage")
        else:
            raise ValueError(f"unsupported geometry {kind}; no features imported")
        if progress and (index % 100 == 0 or index + 1 == len(features)):
            progress(index + 1, len(features))
    if osm_graph and value.get("osm_connections"):
        # Keep original source joins even when neither arm survives the crop.
        # Map each retained arm to the exact normalized output feature/way.
        retained = {}
        for index, feature in enumerate(features):
            p = feature["properties"]
            if p.get("road_kind") not in ("bridge", "tunnel"): continue
            for ref in (p["osm_node_refs"][0], p["osm_node_refs"][-1]):
                retained.setdefault(str(ref), []).append(dict(feature=index, source_way=str(p["osm_way_id"])))
        layer.coordinates["osm_connections"] = dict(profile="same-kind-endpoints-v1", joins=[
            dict(entry, retained=retained.get(entry["ref"], [])) for entry in value["osm_connections"]])
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
    parser.add_argument("--input-format", choices=["geojson", "pbf", "osm", "overture", "overture-transportation", "overture-land-cover"], default="geojson")
    parser.add_argument("--osm-bbox", nargs=4, type=float)
    parser.add_argument("--osm-stream", action="store_true")
    parser.add_argument("--vertical-request", type=Path)
    args = parser.parse_args()
    if args.vertical_request is not None and args.input_format not in ("osm", "pbf"):
        raise ValueError("vertical conversion is only supported for explicit OSM heights")
    if args.osm_bbox is not None and args.input_format not in ("osm", "pbf"):
        raise ValueError("OSM bbox is only valid for OSM PBF/XML")
    if args.osm_stream and (args.input_format != "pbf" or args.osm_bbox is None):
        raise ValueError("PBF streaming requires PBF input and an explicit bbox")
    if args.watch_parent:
        watch_parent_lifetime(900 if args.osm_stream else 120)
    sequence = 0
    def event(stage, completed, total, unit="bytes", **extra):
        nonlocal sequence
        sequence += 1
        print(json.dumps(dict(request=args.layer_id, seq=sequence, stage=stage, completed=completed, total=total, unit=unit, **extra)), flush=True)
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
    captured_source = None
    vertical = None
    if args.input_format == "geojson":
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
            value, osm_counts, osm_stream = extract(args.source,args.osm_bbox,args.output.parent,event)
            captured_source = Source(args.source_name or args.source.name, osm_stream["source_sha256"], osm_stream["source_bytes"], args.license, args.accuracy)
        else:
            value, osm_counts = parse(raw, args.input_format)
        from vertical import Vertical, read_options
        vertical = Vertical(read_options(args.vertical_request) if args.vertical_request is not None else
            dict(target="EGM96", zero_m=0, grid=None))
        value = vertical.apply(value)
        if args.osm_bbox is not None:
            from osm_area import crop
            value, osm_crop = crop(value, args.osm_bbox)
    parse_bytes = osm_stream["selected"]["bytes"] if osm_stream else size
    event("parse", parse_bytes, parse_bytes)
    options = {"mode": args.coordinates}
    if args.coordinates == "wgs84-utm":
        options.update(origin=args.origin, local_origin_m=args.local_origin)
    elif args.origin is not None or args.local_origin is not None:
        raise ValueError("local-metre mode must not specify geographic origins")
    if args.input_format == "overture-transportation":
        from overture_transportation import convert as convert_transportation
        result = convert_transportation(value, args.source_name or args.source.name, raw,
            layer_id=args.layer_id, coordinates=options, accuracy=args.accuracy,
            progress=lambda c,t:event("convert",c,t,"features"))
    else:
        result = convert(value, args.source_name or args.source.name, args.license, layer_id=args.layer_id, source_bytes=raw, accuracy=args.accuracy,
            progress=lambda completed, total: event("convert", completed, total, "features"), coordinates=options, osm_graph=osm_counts is not None, captured_source=captured_source)
    if osm_counts is not None:
        from osm_extract import finish
        result.coordinates["vertical"] = vertical.metadata
        result = finish(result, osm_counts)
        if osm_stream is not None:
            result.coordinates["osm_stream"] = osm_stream
            result.warnings.insert(0,"PBF area streaming: complete candidate envelopes, relation members and connected structures with every incident highway precede crop. Closure transits structures only, within selection/index/work budgets; ground roads do not expand the graph. Other outside geometry is not normalized. Nested feature/area relations reject globally. Three disk-indexed passes; full captured source hash retained.")
            result.warning_count += 1
        if osm_crop is not None:
            result.coordinates["osm_crop"] = osm_crop
            if osm_crop["policy"] in ("geometry-intersection-v3", "geometry-intersection-v4"):
                result.warnings.insert(0, "Partial bridge/tunnel crop: boundary-section ends are open truncated cross-sections, not surveyed entrances or ground ramps. Width/deck/ceiling/walls use the existing native corridor and may extend beyond the centreline bbox. Original retained ground junctions still need nonzero approaches. Review source-way/range/endpoints in crop provenance; no outside continuation or datum alignment is inferred.")
                result.warning_count += 1
            elif "vertical" in osm_crop:
                result.warnings.insert(0, "OSM ground crop interpolates reviewed target-datum heights at WGS84 segment cuts; source heights are references, ground still follows map terrain. Original node IDs stay connected; new boundary cuts are separate endpoints. Complete bridge/tunnel spans and nonzero ground approaches are required; no extra terrain fitting is inferred.")
                result.warning_count += 1
            crop_summary = "OSM derived geometry crop: " + json.dumps(osm_crop, sort_keys=True) if osm_crop["policy"] not in ("geometry-intersection-v3", "geometry-intersection-v4") else "OSM partial structure crop counts: " + json.dumps({k:v for k,v in osm_crop["vertical"].items() if k not in ("structures", "connection_sections")}, sort_keys=True) + "; full source mapping is recorded in projection provenance."
            result.warnings.insert(0, crop_summary)
            result.warning_count += 1
            result.warnings = result.warnings[:50]
    if overture_metadata is not None:
        if args.input_format == "overture-land-cover":
            from overture_land_cover import finish
        else:
            from overture_area import finish
        result = finish(result, overture_metadata)
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
