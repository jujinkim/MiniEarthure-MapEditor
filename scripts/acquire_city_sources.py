#!/usr/bin/env python3
"""Explicit authoring acquisition and coverage checks for real-city sources.

Besides acquire_regional_sources.py, only this command uses the network. It
writes immutable local snapshots; the offline importers then read those files
exactly as they read user-supplied ones. Subcommands:

  search     Nominatim place search (explicit query, cached, at most 1 request/s)
  osm        Overpass extract of a centred extent plus margin, written as a PBF
             with that header box, and the containing country's traffic tags
  dem        Copernicus GLO-30 tiles touching an extent into a shared tile folder
  preflight  Coverage of a local PBF and DEM folder for an extent (no network)

Progress is one JSON object per stdout line ({"stage", "done", "total"}); the
last line is {"result": ...}. Failures print {"error": ...} and exit 1. No
request carries user or machine details beyond the fixed client name.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent / "importers"))

USER_AGENT = "MiniEarthure-MapEditor/1 (real-city source acquisition)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
COPERNICUS = "https://copernicus-dem-30m.s3.amazonaws.com/"
OSM_LICENSE = "ODbL-1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright"
NOMINATIM_LICENSE = "Data © OpenStreetMap contributors, ODbL 1.0; search by Nominatim"
COPERNICUS_LICENSE = "Copernicus DEM GLO-30; © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA"
SEARCH_TTL_S = 30 * 24 * 3600
SEARCH_INTERVAL_S = 1.1
MAX_SEARCH_BYTES = 2 * 1024 * 1024
MAX_OSM_BYTES = 2 * 1024 * 1024 * 1024
WARN_OSM_BYTES = 512 * 1024 * 1024
MAX_TILE_BYTES = 256 * 1024 * 1024
MAX_RADIUS_KM = 2.5
DEFAULT_MARGIN_M = 1000.0
OVERPASS_TIMEOUT_S = 600
OVERPASS_MAXSIZE = 1024 * 1024 * 1024
# Busy (429) and gateway (502–504) answers are retried after these waits.
RETRY_WAITS_S = (20, 60)
M_PER_DEGREE = 111320.0


def emit(**value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def request(url, data=None, timeout=60):
    headers = {"User-Agent": USER_AGENT}
    if data is not None: headers["Content-Type"] = "application/x-www-form-urlencoded"
    return urlopen(Request(url, data=data, headers=headers), timeout=timeout)


def download(response, target, limit, stage, total=None):
    """Stream to `target` (created exclusively) within `limit` bytes; {bytes, sha256}."""
    digest, count, reported = hashlib.sha256(), 0, 0
    total = total or int(response.headers.get("Content-Length") or 0) or None
    with target.open("xb") as stream:
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > limit: raise ValueError(f"{stage} download exceeds {limit // (1024 * 1024)} MiB")
            digest.update(chunk)
            stream.write(chunk)
            if count - reported >= 8 * 1024 * 1024:
                reported = count
                emit(stage=stage, done=count, total=total or 0)
    if not count: raise ValueError(f"{stage} download is empty")
    return dict(bytes=count, sha256=digest.hexdigest())


def retire_stale(root, prefix, age_s=6 * 3600):
    """Remove this tool's own temporary folders left by a killed run (never others)."""
    import shutil
    for path in root.glob(prefix + "*"):
        try:
            if path.is_dir() and not path.is_symlink() and time.time() - path.stat().st_mtime > age_s: shutil.rmtree(path)
        except OSError:
            pass


def file_identity(path):
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            digest.update(chunk)
    return dict(bytes=count, sha256=digest.hexdigest())


# Extents ---------------------------------------------------------------------

def extent_value(value):
    """{center:[lon,lat], radius_km, shape} or {bbox:[w,s,e,n]} → (polygon, bounds)."""
    if not isinstance(value, dict): raise ValueError("extent must be an object")
    if "bbox" in value:
        from osm_area import bounds
        w, s, e, n = bounds(value["bbox"])
        from shapely.geometry import box
        return box(w, s, e, n), [w, s, e, n]
    from osm_area import extent_region
    radius = value.get("radius_km", 2.0)
    if not isinstance(radius, (int, float)) or not 0 < radius <= MAX_RADIUS_KM:
        raise ValueError(f"radius_km must be positive and at most {MAX_RADIUS_KM}")
    region = extent_region(value.get("center"), radius, value.get("shape", "circle"))
    return region, list(region.bounds)


def grow(bounds, margin_m):
    w, s, e, n = bounds
    lat = margin_m / M_PER_DEGREE
    lon = lat / max(math.cos(math.radians((s + n) / 2)), 0.01)
    return [max(-180, w - lon), max(-80, s - lat), min(180, e + lon), min(84, n + lat)]


def covers(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


# Search ----------------------------------------------------------------------

def search(query, cache, language="", limit=10):
    query = " ".join(str(query).split())
    if not query: raise ValueError("Enter a place to search")
    if len(query) > 256: raise ValueError("Search text is longer than 256 characters")
    limit = max(1, min(int(limit), 20))
    folder = cache / "search"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(canonical(dict(q=query, language=language, limit=limit))).hexdigest()
    cached = folder / f"{key}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < SEARCH_TTL_S:
        value = json.loads(cached.read_text())
        value["cached"] = True
        return value
    # Nominatim policy: an identified client, explicit searches, at most one per second.
    stamp = folder / ".last-request"
    if stamp.exists():
        wait = SEARCH_INTERVAL_S - (time.time() - stamp.stat().st_mtime)
        if wait > 0: time.sleep(wait)
    stamp.touch()
    params = dict(q=query, format="jsonv2", limit=limit, addressdetails=1)
    if language: params["accept-language"] = language
    emit(stage="search", done=0, total=1)
    with request(NOMINATIM + "?" + urlencode(params), timeout=30) as response:
        raw = response.read(MAX_SEARCH_BYTES + 1)
    if len(raw) > MAX_SEARCH_BYTES: raise ValueError("Search response exceeds 2 MiB")
    rows = json.loads(raw)
    if not isinstance(rows, list): raise ValueError("Unexpected search response")
    value = dict(version=1, query=query, fetched_at=now(), license=NOMINATIM_LICENSE, results=[parse_place(row) for row in rows])
    value["results"] = [row for row in value["results"] if row is not None]
    with tempfile.NamedTemporaryFile("wb", dir=folder, delete=False) as stream:
        stream.write(canonical(value))
    os.replace(stream.name, cached)
    value["cached"] = False
    return value


def parse_place(row):
    try:
        lon, lat = float(row["lon"]), float(row["lat"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90): return None
    box = None
    if isinstance(row.get("boundingbox"), list) and len(row["boundingbox"]) == 4:
        s, n, w, e = (float(v) for v in row["boundingbox"])
        box = [w, s, e, n]
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    kind = "/".join(str(row.get(k, "")) for k in ("category", "type") if row.get(k))
    osm = f"{row.get('osm_type')}/{row.get('osm_id')}" if row.get("osm_type") and row.get("osm_id") else ""
    return dict(name=str(row.get("name") or row.get("display_name", ""))[:256], display_name=str(row.get("display_name", ""))[:512],
                point=[lon, lat], kind=kind, source_id=osm, bbox=box, country=str(address.get("country_code", "")).upper()[:2],
                supported=-80 <= lat <= 84)


# OSM -------------------------------------------------------------------------

def overpass_query(box):
    w, s, e, n = box
    # Overpass schedules by the declared timeout/maxsize; modest values queue sooner.
    head = f"[out:xml][timeout:{OVERPASS_TIMEOUT_S}][maxsize:{OVERPASS_MAXSIZE}][bbox:{s:.7f},{w:.7f},{n:.7f},{e:.7f}];"
    # Every node and way in the box, the multipolygon/protected-area/site relations
    # the importer reads, then every member and way node they reference (also
    # outside the box) so crossing geometry and source topology stay complete.
    body = ("(node;way;rel[type=multipolygon];rel[type=boundary][boundary=protected_area];rel[type=site];);"
            "(._;>;);out meta;")
    return head + body


def country_query(point):
    lon, lat = point
    return (f"[out:json][timeout:60];is_in({lat:.7f},{lon:.7f})->.a;"
            "rel(pivot.a)[boundary=administrative][admin_level~\"^[2-4]$\"];out tags;")


def country(point, endpoint):
    """{code, driving_side, basis} from the administrative areas containing point."""
    with request(endpoint, data=urlencode(dict(data=country_query(point))).encode(), timeout=90) as response:
        raw = response.read(MAX_SEARCH_BYTES + 1)
    if len(raw) > MAX_SEARCH_BYTES: raise ValueError("Country lookup response exceeds 2 MiB")
    elements = json.loads(raw).get("elements", [])
    found = {}
    for element in elements:
        tags = element.get("tags", {})
        level = tags.get("admin_level")
        code = tags.get("ISO3166-1:alpha2") or tags.get("ISO3166-1") or ""
        if level == "2" and re.fullmatch(r"[A-Z]{2}", code):
            found = dict(code=code, driving_side=tags.get("driving_side", ""), basis="boundary")
            break
        sub = tags.get("ISO3166-2", "")
        if not found and re.fullmatch(r"[A-Z]{2}-.+", sub):
            found = dict(code=sub[:2], driving_side="", basis="subdivision")
    return found


def osm(center, radius_km, shape, cache, endpoint=OVERPASS, margin_m=DEFAULT_MARGIN_M, reuse=True):
    region, inner = extent_value(dict(center=center, radius_km=radius_km, shape=shape))
    box = [round(v, 7) for v in grow(inner, margin_m)]
    query = overpass_query(box)
    key = hashlib.sha256(canonical(dict(endpoint=endpoint, query=query))).hexdigest()[:16]
    root = cache / "osm"
    root.mkdir(parents=True, exist_ok=True)
    if reuse:
        for folder in sorted(root.glob(key + "-*"), reverse=True):
            manifest = folder / "manifest.json"
            if manifest.is_file() and (folder / "extract.osm.pbf").is_file():
                value = json.loads(manifest.read_text())
                value["path"] = str(folder / "extract.osm.pbf")
                value["cached"] = True
                return value
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = root / f"{key}-{stamp}"
    if destination.exists(): raise ValueError("snapshot destination exists; retry in a second")
    retire_stale(root, ".osm-acquire-")
    emit(stage="country", done=0, total=1)
    context = country(center, endpoint)
    with tempfile.TemporaryDirectory(prefix=".osm-acquire-", dir=root) as scratch:
        work = Path(scratch)
        xml = work / "extract.osm"
        raw_identity = None
        for attempt in range(len(RETRY_WAITS_S) + 1):
            emit(stage="osm_download", done=0, total=0)
            try:
                with request(endpoint, data=urlencode(dict(data=query)).encode(), timeout=OVERPASS_TIMEOUT_S + 120) as response:
                    raw_identity = download(response, xml, MAX_OSM_BYTES, "osm_download")
                break
            except HTTPError as exc:
                if exc.code not in (429, 502, 503, 504) or attempt == len(RETRY_WAITS_S):
                    raise ValueError(f"Overpass refused the extract (HTTP {exc.code}); try again later or use a local PBF") from exc
                emit(stage="osm_wait", done=attempt + 1, total=len(RETRY_WAITS_S))
                time.sleep(RETRY_WAITS_S[attempt])
        osm_base = check_overpass_xml(xml)
        emit(stage="osm_convert", done=0, total=raw_identity["bytes"])
        snapshot = work / "snapshot"
        snapshot.mkdir()
        pbf = snapshot / "extract.osm.pbf"
        counts = to_pbf(xml, pbf, box)
        if not counts["ways"]: raise ValueError("The extract has no ways; check the location")
        identity = file_identity(pbf)
        value = dict(version=1, kind="osm", endpoint=endpoint, query=query, query_key=key, fetched_at=now(), osm_base=osm_base,
                     center=center, radius_km=radius_km, shape=shape, margin_m=margin_m, bbox=box, extent_bounds=inner,
                     counts=counts, xml_bytes=raw_identity["bytes"], bytes=identity["bytes"], sha256=identity["sha256"],
                     license=OSM_LICENSE, country=context, warnings=[])
        if raw_identity["bytes"] > WARN_OSM_BYTES:
            value["warnings"].append(f"Large extract: {raw_identity['bytes'] // (1024 * 1024)} MiB of OSM XML")
        (snapshot / "manifest.json").write_bytes(canonical(value))
        if destination.exists(): raise ValueError("snapshot destination appeared during acquisition")
        snapshot.rename(destination)
    value["path"] = str(destination / "extract.osm.pbf")
    value["cached"] = False
    return value


def check_overpass_xml(path):
    """The extract's osm_base; Overpass reports runtime errors inside a 200 response."""
    with path.open("rb") as stream:
        head = stream.read(4096).decode("utf-8", "replace")
        stream.seek(max(0, path.stat().st_size - 4096))
        tail = stream.read().decode("utf-8", "replace")
    if "<osm" not in head: raise ValueError("Overpass returned no OSM data: " + re.sub(r"<[^>]+>", " ", head)[:300].strip())
    for text in (head, tail):
        remark = re.search(r"<remark>(.*?)</remark>", text, re.S)
        if remark: raise ValueError("Overpass did not finish the extract: " + remark.group(1).strip()[:300])
    if "</osm>" not in tail: raise ValueError("Overpass extract is truncated")
    base = re.search(r'osm_base="([^"]+)"', head)
    return base.group(1) if base else ""


def to_pbf(xml, pbf, box):
    import osmium
    header = osmium.io.Header()
    header.add_box(osmium.osm.Box(osmium.osm.Location(box[0], box[1]), osmium.osm.Location(box[2], box[3])))
    header.set("generator", "MiniEarthure MapEditor Overpass snapshot")
    counts = dict(nodes=0, ways=0, relations=0)
    writer = osmium.SimpleWriter(str(pbf), header=header)
    try:
        for item in osmium.FileProcessor(str(xml)):
            if item.is_node():
                writer.add_node(item); counts["nodes"] += 1
            elif item.is_way():
                writer.add_way(item); counts["ways"] += 1
            elif item.is_relation():
                writer.add_relation(item); counts["relations"] += 1
            total = counts["nodes"] + counts["ways"] + counts["relations"]
            if total % 500000 == 0: emit(stage="osm_convert", done=total, total=0)
    finally:
        writer.close()
    return counts


# DEM -------------------------------------------------------------------------

def dem_tiles(bounds, margin_m):
    w, s, e, n = grow(bounds, margin_m)
    # Same envelope as copernicus_dem._plan for 30m tiles: interpolation support
    # may reach just past an integer degree.
    west, east = math.floor(w), math.floor(e + 1 / 120)
    south, north = math.floor(s - 1 / 1200), math.floor(n)
    return [[x, y] for y in range(south, north + 1) for x in range(west, east + 1)]


def dem(bounds, folder, margin_m=DEFAULT_MARGIN_M):
    from copernicus_dem import tile_filename
    folder.mkdir(parents=True, exist_ok=True)
    retire_stale(folder, ".dem-acquire-")
    tiles = dem_tiles(bounds, margin_m)
    if len(tiles) > 16: raise ValueError("The extent needs more than 16 Copernicus tiles")
    result = dict(version=1, kind="dem", folder=str(folder), tiles=[], absent=[], license=COPERNICUS_LICENSE)
    for index, tile in enumerate(tiles):
        name = tile_filename(tile)
        target = folder / name
        manifest = folder / (name + ".json")
        absent = folder / (name + ".absent.json")
        emit(stage="dem_download", done=index, total=len(tiles))
        if target.is_file() and manifest.is_file():
            result["tiles"].append(json.loads(manifest.read_text()))
            continue
        if absent.is_file():
            result["absent"].append(name)
            continue
        if target.exists(): raise ValueError(f"{name} exists without its acquisition record; choose another tile folder")
        url = COPERNICUS + name[:-4] + "/" + name
        with tempfile.TemporaryDirectory(prefix=".dem-acquire-", dir=folder) as scratch:
            part = Path(scratch) / name
            try:
                with request(url, timeout=600) as response:
                    etag = response.headers.get("ETag", "")
                    identity = download(response, part, MAX_TILE_BYTES, "dem_download")
            except HTTPError as exc:
                if exc.code in (403, 404):
                    # Copernicus publishes no tile over open sea.
                    absent.write_bytes(canonical(dict(version=1, name=name, url=url, status=exc.code, checked_at=now())))
                    result["absent"].append(name)
                    continue
                raise ValueError(f"Copernicus tile download failed (HTTP {exc.code}): {name}") from exc
            check_tile(part, tile)
            record = dict(version=1, name=name, url=url, etag=etag, fetched_at=now(), license=COPERNICUS_LICENSE, **identity)
            if target.exists(): raise ValueError(f"{name} appeared during acquisition")
            os.replace(part, target)
            manifest.write_bytes(canonical(record))
            result["tiles"].append(record)
    emit(stage="dem_download", done=len(tiles), total=len(tiles))
    return result


def check_tile(path, tile):
    import rasterio
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(path) as source:
            left, bottom, right, top = source.bounds
            if source.count != 1 or abs(left - tile[0]) > 0.01 or abs(bottom - tile[1]) > 0.01 or abs(right - tile[0] - 1) > 0.01 or abs(top - tile[1] - 1) > 0.01:
                raise ValueError(f"Downloaded Copernicus tile does not cover {tile}")


# Preflight -------------------------------------------------------------------

def pbf_bounds(path):
    """Header box, else the scanned node extent; (bounds, basis)."""
    import osmium
    reader = osmium.io.Reader(str(path), osmium.osm.NOTHING)
    try:
        box = reader.header().box()
        if box.valid():
            return [box.bottom_left.lon, box.bottom_left.lat, box.top_right.lon, box.top_right.lat], "header"
    finally:
        reader.close()
    w = s = math.inf
    e = n = -math.inf
    count = 0
    for node in osmium.FileProcessor(str(path), osmium.osm.NODE):
        if not node.location.valid(): continue
        lon, lat = node.location.lon, node.location.lat
        w, s, e, n = min(w, lon), min(s, lat), max(e, lon), max(n, lat)
        count += 1
        if count % 5000000 == 0: emit(stage="pbf_scan", done=count, total=0)
    if not count: raise ValueError("The PBF has no located nodes")
    return [w, s, e, n], "nodes"


def preflight(extent, pbf=None, dem_folder=None, margin_m=DEFAULT_MARGIN_M):
    from copernicus_dem import tile_filename
    region, inner = extent_value(extent)
    result = dict(version=1, ok=True, extent_bounds=inner, errors=[], warnings=[])
    if pbf is not None:
        path = Path(pbf)
        if not path.is_file():
            result["errors"].append(f"PBF not found: {path.name}")
        else:
            emit(stage="pbf_coverage", done=0, total=1)
            box, basis = pbf_bounds(path)
            result["pbf"] = dict(bounds=box, basis=basis, bytes=path.stat().st_size, covers=covers(box, inner))
            if not result["pbf"]["covers"]:
                result["errors"].append("The PBF does not cover the requested extent: PBF %s, extent %s" % (fmt(box), fmt(inner)))
            elif basis == "nodes":
                result["warnings"].append("The PBF has no header box; coverage comes from its node extent")
    if dem_folder is not None:
        folder = Path(dem_folder)
        needed = [tile_filename(tile) for tile in dem_tiles(inner, margin_m)]
        missing = [name for name in needed if not (folder / name).is_file()]
        absent = [name for name in missing if (folder / (name + ".absent.json")).is_file()]
        result["dem"] = dict(needed=needed, missing=[m for m in missing if m not in absent], absent=absent)
        if result["dem"]["missing"]:
            result["errors"].append("The DEM folder needs these Copernicus tiles: " + ", ".join(result["dem"]["missing"]))
        if absent:
            result["warnings"].append("Copernicus has no tile (open sea) for: " + ", ".join(absent))
    result["ok"] = not result["errors"]
    return result


def fmt(box):
    return "[" + ", ".join(f"{v:.5f}" for v in box) + "]"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("search")
    one.add_argument("--query", required=True)
    one.add_argument("--language", default="")
    one.add_argument("--limit", type=int, default=10)
    one.add_argument("--cache", type=Path, required=True)
    two = sub.add_parser("osm")
    two.add_argument("--center", nargs=2, type=float, required=True)
    two.add_argument("--radius-km", type=float, default=2.0)
    two.add_argument("--shape", choices=("circle", "square"), default="circle")
    two.add_argument("--cache", type=Path, required=True)
    two.add_argument("--endpoint", default=OVERPASS)
    two.add_argument("--margin-m", type=float, default=DEFAULT_MARGIN_M)
    two.add_argument("--fresh", action="store_true", help="download again instead of reusing a matching snapshot")
    three = sub.add_parser("dem")
    three.add_argument("--extent", required=True, help="extent JSON")
    three.add_argument("--folder", type=Path, required=True)
    four = sub.add_parser("preflight")
    four.add_argument("--extent", required=True, help="extent JSON")
    four.add_argument("--pbf", type=Path)
    four.add_argument("--dem", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "search":
            result = search(args.query, args.cache.absolute(), args.language, args.limit)
        elif args.command == "osm":
            if not 0 <= args.margin_m <= 5000: raise ValueError("margin must be 0–5000 m")
            result = osm(list(args.center), args.radius_km, args.shape, args.cache.absolute(), args.endpoint, args.margin_m, not args.fresh)
        elif args.command == "dem":
            result = dem(extent_value(json.loads(args.extent))[1], args.folder.absolute())
        else:
            result = preflight(json.loads(args.extent), args.pbf, args.dem)
    except Exception as exc:  # Reported to the Editor; the traceback is not user-facing.
        emit(error=str(exc) or type(exc).__name__)
        return 1
    emit(result=result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
