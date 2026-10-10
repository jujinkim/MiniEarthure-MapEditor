"""Explicit local CSV column mapping; invalid rows are reviewable, never located by guesswork."""
import csv
import hashlib
import io
import json
from import_layer import ImportLayer, Source, MAX_INPUT, number, text
from projection import Coordinates

MAX_ROWS = 20_000
ENCODINGS = ("utf-8-sig", "cp949", "euc-kr")


def convert(raw, name, license_name, accuracy, layer_id, coordinates, options, progress=None):
    if len(raw) > MAX_INPUT: raise ValueError("CSV exceeds 32 MiB")
    required = {"encoding", "name_column", "latitude_column", "longitude_column", "category", "source_url", "bounds_cm", "source_denominator"}
    if not isinstance(options, dict) or set(options) - {"geographic_bbox"} != required: raise ValueError("Invalid CSV mapping options")
    selected = options.get("geographic_bbox")
    if selected is not None:
        from osm_area import bounds as geographic_bounds
        selected = geographic_bounds(selected)
    if options["encoding"] not in ENCODINGS: raise ValueError("Choose UTF-8, CP949 or EUC-KR explicitly")
    if type(options["source_denominator"]) is not int or options["source_denominator"] not in (1, 8): raise ValueError("CSV scale must match the map (1:1 or 1:8)")
    category = text(options["category"], "facility category", 128)
    url = text(options["source_url"], "source reference", 512)
    bounds = options["bounds_cm"]
    if not isinstance(bounds, list) or len(bounds) != 4 or any(type(n) is not int or abs(n)>10_000_000 for n in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
        raise ValueError("CSV requires current map bounds in centimetres")
    projection = Coordinates(coordinates)
    if projection.mode != "wgs84-utm": raise ValueError("CSV facilities require WGS84 coordinates")
    try: decoded = raw.decode(options["encoding"], errors="strict")
    except UnicodeError as exc: raise ValueError("CSV encoding does not match the selected encoding") from exc
    csv.field_size_limit(16384)
    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    try:
        headers = next(reader)
        if not 1 <= len(headers) <= 128 or any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
            raise ValueError("CSV header must contain unique nonempty column names")
        columns = [text(options[k], k, 256) for k in ("name_column", "latitude_column", "longitude_column")]
        if len(set(columns)) != 3 or any(c not in headers for c in columns): raise ValueError("CSV mapping requires three distinct existing columns: " + ", ".join(headers))
        indices = [headers.index(c) for c in columns]
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS: raise ValueError("CSV row budget exceeded (20,000)")
            rows.append((reader.line_num, row))
    except (csv.Error, StopIteration) as exc: raise ValueError("Malformed or empty CSV: " + str(exc)) from exc
    source = Source(name, hashlib.sha256(raw).hexdigest(), len(raw), license_name, accuracy)
    layer = ImportLayer(layer_id, source, dict(projection.metadata), adapter="facility-csv-v1")
    rejected, outside = [], []
    for index, (line, row) in enumerate(rows):
        if progress: progress(index, len(rows))
        try:
            if len(row) != len(headers): raise ValueError("column count differs from header")
            facility = text(row[indices[0]], "facility name", 256)
            lat = number(float(row[indices[1]]), "latitude", -80, 84)
            lon = number(float(row[indices[2]]), "longitude", -180, 180)
            if selected is not None and not (selected[0] <= lon <= selected[2] and selected[1] <= lat <= selected[3]):
                outside.append(line)
                continue
            position = [round(n / options["source_denominator"]) for n in projection.point([lon, lat])]
            if not bounds[0] <= position[0] <= bounds[2] or not bounds[1] <= position[1] <= bounds[3]:
                outside.append(line)
                continue
        except (ValueError, OverflowError) as exc:
            rejected.append({"line":line, "name": row[indices[0]][:256] if len(row)>indices[0] else "", "reason":str(exc)[:256]})
            continue
        layer.point(*position)
        layer.add("pois", {"id":f"import-{layer_id}-csv-{line}", "name":facility, "category":category, "position":position,
            "source":{"source":url, "license":license_name, "notice":json.dumps({"file":name, "sha256":source.sha256, "line":line, "longitude":lon, "latitude":lat, "accuracy":accuracy, "height":"unspecified"}, ensure_ascii=False, sort_keys=True)}})
        layer.feature_count += 1
    if progress: progress(len(rows), len(rows))
    if not layer.patches: raise ValueError(f"CSV contains no valid facilities inside the map; {len(rejected)} invalid rows; {len(outside)} outside. " + json.dumps(rejected[:3], ensure_ascii=False))
    layer.coordinates["csv"] = dict(options=options, headers=headers, rows=len(rows), accepted=layer.feature_count, rejected=rejected, outside=outside)
    if rejected: layer.warning(f"{len(rejected)} invalid CSV rows require explicit exclusion; exact line/name/reason in CSV review details.")
    if outside: layer.warning(f"{len(outside)} CSV rows are outside the selected geographic crop or current map bounds; not placed.")
    layer.warning("Facility heights are unspecified. Pins are informational; no collision or guessed geocoding.")
    return layer
