"""Public Overture building-area snapshot acquisition and strict typed normalization."""
import argparse
import contextlib
import datetime
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import re
import sys
from import_layer import MAX_INPUT, MAX_POINTS, number, text, strict_json
from polygon_geometry import Budget, group_rings

LICENSE = "ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; https://docs.overturemaps.org/attribution/#buildings"
CLIENT_VERSION = "1.0.2"
MAX_FEATURES = 20000


def plan(release, bbox):
    if not isinstance(release, str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]+", release):
        raise ValueError("Select an explicit dated Overture release, never latest")
    datetime.date.fromisoformat(release[:10])
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("Area requires west,south,east,north")
    w, s, e, n = [number(v, "bbox", -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84) for i, v in enumerate(bbox)]
    if not w < e or not s < n or e-w > 0.02 or n-s > 0.02:
        raise ValueError("Select a non-crossing area at most 0.02 degrees per side")
    return dict(provider="Overture", release=release, bbox=[w,s,e,n], theme="buildings", type="building", license=LICENSE)


def remote_features(query):
    try:
        if version("overturemaps") != CLIENT_VERSION: raise ImportError("version mismatch")
        from overturemaps.core import record_batch_reader
        from shapely import from_wkb, to_geojson
    except (ImportError, PackageNotFoundError) as exc:
        raise ValueError("Overture needs overturemaps 1.0.2; install requirements-import.txt in the selected Python") from exc
    # The provider client may print discovery messages; stdout is reserved for IPC.
    with contextlib.redirect_stdout(sys.stderr):
        reader = record_batch_reader("building", bbox=query["bbox"], release=query["release"], stac=True, connect_timeout=15, request_timeout=15)
    if reader is None: raise ValueError("No Overture building reader; area may be empty or provider unavailable")
    with reader:
        while True:
            with contextlib.redirect_stdout(sys.stderr):
                try: batch = next(reader)
                except StopIteration: break
            if batch.nbytes > MAX_INPUT or batch.num_rows > MAX_FEATURES:
                raise ValueError("Provider batch exceeds local admission; select a smaller area")
            for row in batch.to_pylist():
                geometry = row.pop("geometry")
                if not isinstance(geometry, bytes) or len(geometry) > 4 * 1024 * 1024:
                    raise ValueError("Invalid/oversized Overture WKB")
                shape = from_wkb(geometry)
                if shape.has_z or shape.has_m:
                    raise ValueError("Overture Z/M geometry is unsupported")
                yield dict(type="Feature", id=row.get("id"), geometry=json.loads(to_geojson(shape)), properties=row)


def _json_default(value):
    if isinstance(value, (datetime.date, datetime.datetime)): return value.isoformat()
    raise ValueError("Unsupported provider value")


def acquire(query, partial, destination, progress, features=remote_features):
    checked = plan(query.get("release"), query.get("bbox"))
    if query != checked: raise ValueError("Overture review contract changed")
    count, seen = 0, set()
    header = json.dumps(dict(snapshot_version=1, **query), sort_keys=True).encode()[:-1] + b',"features":['
    size = len(header)
    progress(0, MAX_INPUT)
    with partial.open("xb") as stream:
        stream.write(header)
        for feature in features(query):
            count += 1
            if count > MAX_FEATURES: raise ValueError("Overture feature budget exceeded")
            identity = text(feature.get("id"), "Overture ID", 128)
            if identity in seen: raise ValueError("Duplicate Overture ID")
            seen.add(identity)
            encoded = json.dumps(feature, sort_keys=True, allow_nan=False, default=_json_default, separators=(",", ":")).encode()
            size += len(encoded) + (1 if count > 1 else 0)
            if size + 2 > MAX_INPUT: raise ValueError("Overture snapshot exceeds 32 MiB")
            if count > 1: stream.write(b",")
            stream.write(encoded)
            if count % 100 == 0: progress(size, MAX_INPUT)
        if count == 0: raise ValueError("No buildings in selected area")
        stream.write(b"]}")
        stream.flush()
        os.fsync(stream.fileno())
    # Preserve the complete provider snapshot even if subsequent geometry conversion fails.
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    os.link(partial, destination)  # exclusive atomic create on same filesystem
    progress(size+2, MAX_INPUT)
    return dict(query, path=str(destination), sha256=digest, actual_bytes=size+2, features=count)


def parse(raw):
    if len(raw) > MAX_INPUT: raise ValueError("Overture snapshot exceeds 32 MiB")
    value = strict_json(raw)
    if not isinstance(value, dict) or value.get("snapshot_version") != 1:
        raise ValueError("Expected an Overture area snapshot version 1")
    query = plan(value.get("release"), value.get("bbox"))
    if set(value) != set(query) | {"snapshot_version", "features"} or any(value[k] != v for k,v in query.items()):
        raise ValueError("Invalid Overture source contract/license")
    features = value["features"]
    if not isinstance(features, list) or not 1 <= len(features) <= MAX_FEATURES:
        raise ValueError("Expected 1..20000 Overture buildings")
    output, provenance, seen, total_points = [], [], set(), 0
    w,s,e,n = query["bbox"]
    topology_budget = Budget()
    for f in features:
        if not isinstance(f, dict) or f.get("type") != "Feature": raise ValueError("Expected Overture Feature")
        identity = text(f.get("id"), "Overture ID", 128)
        if identity in seen: raise ValueError("Duplicate Overture ID")
        seen.add(identity)
        p, g = f.get("properties"), f.get("geometry")
        if not isinstance(p, dict) or p.get("id") != identity or not isinstance(g, dict): raise ValueError("Invalid Overture properties/identity")
        if p.get("has_parts") not in (None, False) or p.get("is_underground") not in (None, False) or p.get("min_height") not in (None, 0) or p.get("min_floor") not in (None, 0) or p.get("level") not in (None, 0):
            raise ValueError("Partial/underground/elevated buildings require explicit authoring")
        kind, coordinates = g.get("type"), g.get("coordinates")
        if kind not in ("Polygon", "MultiPolygon") or not isinstance(coordinates, list):
            raise ValueError("Expected Polygon or MultiPolygon building footprint")
        polygons = [coordinates] if kind == "Polygon" else coordinates
        if not 1 <= len(polygons) <= 256:
            raise ValueError("Expected 1..256 footprint parts per Overture feature")
        positions = []
        for rings in polygons:
            if not isinstance(rings, list) or not 1 <= len(rings) <= 17:
                raise ValueError("Expected outer ring and at most 16 courtyard holes")
            vertices = 0
            for ring in rings:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Invalid closed building ring")
                total_points += len(ring)
                vertices += len(ring)-1
                if total_points > MAX_POINTS: raise ValueError("Overture point budget exceeded")
                for pos in ring:
                    if not isinstance(pos, list) or len(pos) != 2: raise ValueError("Expected 2D WGS84 position")
                    number(pos[0], "longitude", -180, 180)
                    number(pos[1], "latitude", -80, 84)
                positions.extend(ring)
            if len(rings) > 1 and vertices > 512:
                raise ValueError("Courtyard supports at most 512 total vertices")
        grouped = group_rings([rings[0] for rings in polygons], [hole for rings in polygons for hole in rings[1:]], topology_budget)
        if grouped != polygons:
            raise ValueError("Courtyard holes must belong to their declared outer")
        xs, ys = [pos[0] for pos in positions], [pos[1] for pos in positions]
        if min(xs) >= e or max(xs) <= w or min(ys) >= n or max(ys) <= s: raise ValueError("Feature does not intersect requested bbox")
        # Preserve every complete part, including parts outside the query envelope.
        # Keep historical single-member authored IDs stable.
        g = dict(type="Polygon", coordinates=polygons[0]) if len(polygons) == 1 else dict(type="MultiPolygon", coordinates=polygons)
        sources = p.get("sources")
        if not isinstance(sources, list) or not 1 <= len(sources) <= 128 or len(json.dumps(sources)) > 16384:
            raise ValueError("Missing/oversized Overture source attribution")
        for source in sources:
            if not isinstance(source, dict): raise ValueError("Invalid Overture source")
            text(source.get("dataset"), "source dataset")
            if source.get("license") is not None: text(source["license"], "source license")
        properties = {}
        if p.get("height") is not None: properties["height_m"] = number(p["height"], "height", 0.01, 1000)
        output.append(dict(type="Feature", geometry=g, properties=properties, id=identity))
        provenance.append(dict(id=identity, version=p.get("version"), sources=sources, footprint_count=len(polygons)))
    output.sort(key=lambda f:f["id"])
    provenance.sort(key=lambda p:p["id"])
    return dict(type="FeatureCollection", features=output), dict(query, feature_sources=provenance)


def finish(layer, metadata):
    # Explicit source-to-authored mapping survives attribution and project I/O.
    for index, feature in enumerate(metadata["feature_sources"]):
        prefix = f"import-{layer.layer_id}-{index}"
        count = feature["footprint_count"]
        feature["building_ids"] = [prefix] if count == 1 else [f"{prefix}-part-{part}" for part in range(count)]
    # Recipe 3+ requires an authored use even for solid multipart islands.
    # GeoJSON already counted unknown usage as an estimate; make the fallback
    # explicit without inventing a provider classification.
    for patch in layer.patches:
        if patch["after"]["usage"] == "unknown":
            patch["after"]["usage"] = "residential"
    layer.adapter = "overture-buildings-v1"
    layer.coordinates["overture"] = metadata
    layer.warning("Overture buildings only; crossing footprints retained without clipping. Other themes not queried.")
    layer.warning("Multipart footprints share source identity; parts are separate complete buildings, not inferred vertical building parts.")
    layer.warning("Base=0, unknown use represented as residential, flat roof/concrete and absent height are estimates; names/facade/roof/floors are not modeled.")
    layer.encode()
    return layer


def main():
    from geojson import watch_parent_lifetime
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--layer-id", required=True)
    parser.add_argument("--watch-parent", action="store_true")
    args = parser.parse_args()
    if args.watch_parent: watch_parent_lifetime()
    if args.request.stat().st_size > 8192: raise ValueError("Oversized Overture request")
    request = strict_json(args.request.read_bytes())
    sequence = 0
    def event(stage, completed, total, **extra):
        nonlocal sequence
        sequence += 1
        print(json.dumps(dict(request=args.layer_id, seq=sequence, stage=stage, completed=completed, total=total, unit="bytes", **extra)), flush=True)
    result = acquire(request["plan"], args.output.parent / "download.part", Path(request["destination"]), lambda c,t:event("acquire",c,t))
    encoded = json.dumps(result, sort_keys=True).encode()
    event("write",0,len(encoded))
    with args.output.open("xb") as stream: stream.write(encoded)
    event("write",len(encoded),len(encoded))
    event("complete",len(encoded),len(encoded),sha256=hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"error":str(exc)[:1024]}),file=sys.stderr)
        sys.exit(1)
