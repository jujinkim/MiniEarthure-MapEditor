"""Bounded Geofabrik snapshot acquisition. Public MIT; no automatic retries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request
from urllib.error import HTTPError
from urllib.parse import urljoin
from geojson import watch_parent_lifetime
from import_layer import MAX_INPUT, strict_json
from osm_extract import LICENSE

BASE = "https://download.geofabrik.de/"
CATALOG = BASE + "index-v1-nogeom.json"
CATALOG_LIMIT = 2 * 1024 * 1024
PATTERN = r"https://download\.geofabrik\.de/(?:[a-z0-9-]+/)*[a-z0-9-]+\.osm\.pbf"


def checked_url(url):
    if not isinstance(url, str) or len(url) > 400 or not re.fullmatch(PATTERN, url):
        raise ValueError("Choose a public HTTPS Geofabrik .osm.pbf URL without query, credentials or fragment")
    return url


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = checked_url(urljoin(req.full_url, newurl))
        count = getattr(req, "redirect_count", 0) + 1
        if count > 3:
            raise ValueError("Download exceeds three redirects")
        redirected = urllib.request.Request(target, headers=dict(req.header_items()), method=req.get_method())
        redirected.redirect_count = count
        return redirected


def open_remote(url, method, headers=None):
    request = urllib.request.Request(url if url == CATALOG else checked_url(url), method=method, headers={
        "User-Agent": "MiniEarthure-MapEditor/1.0 (bounded user-requested extract)",
        "Accept-Encoding": "identity", **(headers or {})})
    try:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirects()).open(request, timeout=15)
    except HTTPError as exc:
        raise ValueError(f"Provider HTTP {exc.code}; retry manually later or select a smaller extract. No automatic retry.") from exc


def metadata(response):
    if response.status != 200 or response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise ValueError("Expected complete uncompressed HTTP 200 response")
    sizes = response.headers.get_all("Content-Length", [])
    if len(sizes) > 1 or (sizes and not re.fullmatch(r"[0-9]{1,10}", sizes[0])):
        raise ValueError("Invalid Content-Length")
    size = int(sizes[0]) if sizes else None
    if size is not None and not 0 < size <= MAX_INPUT:
        raise ValueError("Extract exceeds the 32 MiB profile (or is empty); choose a smaller region")
    if response.headers.get("Transfer-Encoding") not in (None, "chunked") or (sizes and response.headers.get("Transfer-Encoding")):
        raise ValueError("Ambiguous transfer framing")
    etag = response.headers.get("ETag", "")
    modified = response.headers.get("Last-Modified", "")
    if any(len(x) > 256 or any(ord(c) < 32 for c in x) for x in (etag, modified)):
        raise ValueError("Invalid provider identity headers")
    return dict(url=checked_url(response.geturl()), bytes=size, etag=etag, modified=modified)


def catalog(opener=open_remote):
    with opener(CATALOG, "GET") as response:
        if response.status != 200 or response.geturl() != CATALOG or response.headers.get("Content-Encoding", "identity") != "identity":
            raise ValueError("Expected official uncompressed region catalog")
        raw = response.read(CATALOG_LIMIT + 1)
        if len(raw) > CATALOG_LIMIT: raise ValueError("Region catalog exceeds 2 MiB")
    value = strict_json(raw)
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection" or not isinstance(value.get("features"), list) or len(value["features"]) > 5000:
        raise ValueError("Invalid region catalog")
    regions, seen = [], set()
    for feature in value["features"]:
        properties = feature.get("properties", {})
        identity, name = properties.get("id"), properties.get("name")
        parent = properties.get("parent") or ""
        if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9/-]{1,200}", identity) or identity in seen:
            raise ValueError("Invalid/duplicate region ID")
        if not isinstance(name, str) or not 0 < len(name) <= 200 or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid region name")
        if not isinstance(parent, str) or len(parent) > 200: raise ValueError("Invalid region parent")
        seen.add(identity)
        url = properties.get("urls", {}).get("pbf")
        if url is not None: regions.append(dict(id=identity, name=name, parent=parent, url=checked_url(url)))
    if not regions: raise ValueError("Catalog has no public PBF regions")
    return dict(regions=sorted(regions, key=lambda r: (r["name"].casefold(), r["id"])), source=CATALOG,
                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def probe(url, opener=open_remote):
    with opener(checked_url(url), "HEAD") as response:
        result = metadata(response)
    return dict(result, requested_url=url, provider="Geofabrik", region=url.removeprefix(BASE).removesuffix(".osm.pbf"),
                license=LICENSE, checked_at=int(time.time()), limit=MAX_INPUT)


def download(plan, partial, destination, progress, opener=open_remote):
    if not isinstance(plan, dict) or plan.get("license") != LICENSE or plan.get("limit") != MAX_INPUT:
        raise ValueError("Invalid reviewed download plan")
    checked_url(plan.get("requested_url"))
    url = checked_url(plan.get("url"))
    if type(plan.get("checked_at")) not in (int, float) or not 0 <= time.time() - plan["checked_at"] <= 600:
        raise ValueError("Download review expired; check the region again")
    headers = {}
    if plan.get("etag") and not plan["etag"].startswith("W/"):
        headers["If-Match"] = plan["etag"]
    elif plan.get("modified"):
        headers["If-Unmodified-Since"] = plan["modified"]
    else:
        raise ValueError("Provider supplied no stable validator; download locally and import the snapshot")
    digest, count = hashlib.sha256(), 0
    with opener(url, "GET", headers) as response:
        actual = metadata(response)
        if any(actual[key] != plan.get(key) for key in ("url", "bytes", "etag", "modified")):
            raise ValueError("Provider snapshot changed after review; check the region again")
        total = actual["bytes"] or MAX_INPUT
        progress(0, total)
        with partial.open("xb") as output:
            while True:
                chunk = response.read(min(65536, MAX_INPUT + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_INPUT or (actual["bytes"] is not None and count > actual["bytes"]):
                    raise ValueError("Download exceeds reviewed size/32 MiB")
                output.write(chunk)
                digest.update(chunk)
                progress(count, total)
            if count == 0 or (actual["bytes"] is not None and count != actual["bytes"]):
                raise ValueError("Truncated/empty download; retry starts a fresh snapshot")
            output.flush()
            os.fsync(output.fileno())
    receipt = dict(plan, actual_bytes=count, sha256=digest.hexdigest(), path=str(destination))
    # Same user-data filesystem: atomic create without replacement. Complete sources
    # and receipts are never deleted, even if conversion/cancellation happens later.
    with destination.with_suffix(".json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True)
    os.link(partial, destination)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--layer-id", required=True)
    parser.add_argument("--watch-parent", action="store_true")
    args = parser.parse_args()
    if args.watch_parent: watch_parent_lifetime()
    if args.request.stat().st_size > 8192: raise ValueError("Download request too large")
    request = strict_json(args.request.read_bytes())
    seq = 0
    def event(stage, completed, total, **extra):
        nonlocal seq
        seq += 1
        print(json.dumps(dict(request=args.layer_id, seq=seq, stage=stage, completed=completed, total=total, unit="bytes", **extra)), flush=True)
    event("acquire", 0, 0 if request["mode"] in ("probe", "catalog") else request["plan"]["bytes"] or MAX_INPUT)
    if request["mode"] == "catalog":
        result = catalog()
    elif request["mode"] == "probe":
        result = probe(request["url"])
    elif request["mode"] == "download":
        result = download(request["plan"], args.output.parent / "download.part", Path(request["destination"]),
                          lambda done, total: event("acquire", done, total))
    else: raise ValueError("Invalid acquisition mode")
    encoded = json.dumps(result, sort_keys=True).encode()
    event("write", 0, len(encoded))
    with args.output.open("xb") as stream: stream.write(encoded)
    event("write", len(encoded), len(encoded))
    event("complete", len(encoded), len(encoded), sha256=hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:1024]}), file=sys.stderr)
        sys.exit(1)
