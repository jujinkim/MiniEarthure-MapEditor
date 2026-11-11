"""Explicit, immutable-snapshot road corrections; no geographic special cases."""
from copy import deepcopy
import math
import re


def validate(value):
    if not isinstance(value, dict) or set(value) != {"osm_sha256", "ways"}:
        raise ValueError("road_overrides needs osm_sha256 and ways")
    if not isinstance(value["osm_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["osm_sha256"]):
        raise ValueError("road_overrides requires the exact source SHA-256")
    if not isinstance(value["ways"], list) or not 1 <= len(value["ways"]) <= 10000:
        raise ValueError("road_overrides ways must contain 1..10000 records")
    seen = set()
    for row in value["ways"]:
        if not isinstance(row, dict) or set(row) - {"source_id", "width_m", "lanes"} or not {"source_id", "width_m", "lanes"} <= set(row):
            raise ValueError("road override needs source_id, width_m and lanes")
        sid = row["source_id"]
        if not isinstance(sid, str) or not re.fullmatch(r"way/[1-9][0-9]*", sid) or sid in seen:
            raise ValueError("road override source IDs must be unique OSM ways")
        seen.add(sid)
        if type(row["lanes"]) not in (int, float) or not float(row["lanes"]).is_integer() or not 1 <= row["lanes"] <= 16:
            raise ValueError("road override lanes must be an integer in 1..16")
        if type(row["width_m"]) not in (int, float) or not math.isfinite(row["width_m"]) or not .2 <= row["width_m"] <= 200:
            raise ValueError("road override width_m must be finite and in .2..200")
    return value


def apply(collection, value, source_sha256):
    validate(value)
    if value["osm_sha256"] != source_sha256:
        raise ValueError("road_overrides OSM snapshot SHA-256 mismatch")
    edits = {r["source_id"]: r for r in value["ways"]}
    # Check every target before changing the collection; failure is atomic.
    found = {f["properties"].get("osm_source_id") for f in collection["features"]
             if f["geometry"]["type"] == "LineString" and "_city_road_tags" in f["properties"]}
    missing = sorted(set(edits) - found)
    if missing: raise ValueError("road_overrides target missing from selected source: " + ", ".join(missing))
    result = deepcopy(collection)
    report = []
    for feature in result["features"]:
        p = feature["properties"]
        sid = p.get("osm_source_id")
        if sid not in edits or feature["geometry"]["type"] != "LineString" or "_city_road_tags" not in p: continue
        row = edits[sid]
        report.append({"source_id": sid, "original_width_m": p.get("width_m"),
                       "original_lanes": p["_city_road_tags"].get("lanes"),
                       "width_m": row["width_m"], "lanes": row["lanes"]})
        p["width_m"] = float(row["width_m"])
        p["_city_road_tags"]["lanes"] = str(int(row["lanes"]))
        p.pop("_city_width_estimate", None)
        p["_city_author_override"] = True
    return result, {"request": deepcopy(value), "applied": sorted(report, key=lambda r: r["source_id"])}
