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


def convert(value, source, license_name, *, layer_id=None, source_bytes=None, accuracy="unknown", progress=None):
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection" or "crs" in value:
        raise ValueError("expected FeatureCollection without legacy CRS; coordinates must be explicitly selected")
    raw = source_bytes if source_bytes is not None else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    layer = ImportLayer(layer_id or uuid.uuid4().hex, Source(source, hashlib.sha256(raw).hexdigest(), len(raw), license_name, accuracy), {"mode": "local-metres", "quantization_cm": 1})
    features = value.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 20_000:
        raise ValueError("expected 1..20000 features")
    layer.feature_count = len(features)

    def point(raw):
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("expected exactly two coordinates; Z is not silently discarded")
        p = [round(number(raw[0], "x") * 100), round(number(raw[1], "y") * 100)]
        layer.point(*p)
        return p

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
            elevation = round(scalar("elevation_m", 0.2) * 100)
            points = [[p[0], elevation, p[1]] for p in map(point, coordinates)]
            if len(points) < 2:
                raise ValueError("road requires two points")
            level = scalar("level", 0, -100, 100)
            if int(level) != level:
                raise ValueError("level must be integral")
            for suffix, p in [("from", points[0]), ("to", points[-1])]:
                layer.add("nodes", {"id": identity + "-" + suffix, "position": p, "level": int(level)})
            width = round(scalar("width_m", 8, 0.01, 1000) * 100)
            surface = text(properties.get("surface", "asphalt"), "surface", 64)
            if "surface" not in properties: layer.estimate("surface")
            layer.add("roads", {"id": identity, "from": identity + "-from", "to": identity + "-to", "points": points,
                "widths_cm": [width] * (len(points) - 1), "surfaces": [surface] * (len(points) - 1), "kind": "ground", "clearance_cm": None, "sidewalk_cm": None})
            layer.warning(f"{index}: disconnected endpoints; connect explicitly in Editor")
        elif kind == "Polygon":
            if len(coordinates) != 1 or not isinstance(coordinates[0], list):
                raise ValueError("polygon holes require explicit exclusions; no silent flattening")
            ring = coordinates[0]
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("polygon ring must be closed with at least four positions")
            polygon = list(map(point, ring[:-1]))
            if properties.get("landuse") in ("forest", "orchard"):
                layer.add("zones", {"id": identity, "polygon": polygon, "kind": properties["landuse"], "spacing_cm": 800, "density_per_mille": 750, "exclusions": []})
                layer.estimate("vegetation_spacing_density")
            else:
                layer.add("buildings", {"id": identity, "footprint": polygon,
                    "base_cm": round(scalar("base_m", 0) * 100), "height_cm": round(scalar("height_m", 12, 0.01, 1000) * 100),
                    "usage": text(properties.get("usage", "unknown"), "usage", 64), "material": "concrete", "roof": "flat"})
                layer.estimate("material_roof")
                if "usage" not in properties: layer.estimate("usage")
        else:
            raise ValueError(f"unsupported geometry {kind}; no features imported")
        if progress and (index % 100 == 0 or index + 1 == len(features)):
            progress(index + 1, len(features))
    layer.encode()  # Bound the complete contract before handing it to any caller.
    return layer


def watch_parent_lifetime():
    # EOF terminates this helper if its owner exits/crashes. No grandchildren.
    def watch_parent():
        while os.read(sys.stdin.fileno(), 1):
            pass
        os._exit(3)
    threading.Thread(target=watch_parent, daemon=True).start()
    def watchdog():
        time.sleep(120)
        os._exit(4)
    threading.Thread(target=watchdog, daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--coordinates", required=True, choices=["local-metres"])
    parser.add_argument("--license", required=True)
    parser.add_argument("--accuracy", default="unknown")
    parser.add_argument("--layer-id", required=True)
    parser.add_argument("--watch-parent", action="store_true")
    args = parser.parse_args()
    if args.watch_parent:
        watch_parent_lifetime()
    sequence = 0
    def event(stage, completed, total, unit="bytes", **extra):
        nonlocal sequence
        sequence += 1
        print(json.dumps(dict(request=args.layer_id, seq=sequence, stage=stage, completed=completed, total=total, unit=unit, **extra)), flush=True)
    size = args.source.stat().st_size
    if size > MAX_INPUT: raise ValueError("input exceeds 32 MiB")
    event("read", 0, size)
    with args.source.open("rb") as stream:
        raw = stream.read(MAX_INPUT + 1)
    if len(raw) != size: raise ValueError("source size changed during read; retry")
    event("read", len(raw), size)
    event("parse", 0, size)
    value = strict_json(raw)
    event("parse", size, size)
    result = convert(value, args.source.name, args.license, layer_id=args.layer_id, source_bytes=raw, accuracy=args.accuracy,
        progress=lambda completed, total: event("convert", completed, total, "features"))
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
