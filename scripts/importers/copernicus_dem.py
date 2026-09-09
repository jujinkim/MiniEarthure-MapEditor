"""Bounded public Copernicus 2021 COG to explicitly authored local PNG16 terrain."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import urllib.request
from urllib.error import HTTPError
import zlib
from import_layer import number, strict_json
from projection import Coordinates

MAX_SOURCE = 64 * 1024 * 1024
LICENSE_URL = "https://copernicus-dem-30m.s3.amazonaws.com/readme.html#license"
NOTICE = "produced using Copernicus WorldDEM-{resolution} © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"


def integer(value, name, low, high):
    value = number(value, name, low, high)
    if value != int(value): raise ValueError(name + " must be an integer")
    return int(value)


def grid(options, mosaic=False):
    if not isinstance(options, dict) or set(options) != {"coordinates", "cell", "cell_size_cm", "map_min_cm", "spacing_cm", "vertical_zero_m", "source", "allow_download", "fallback90"}:
        raise ValueError("Invalid DEM options")
    if type(options["allow_download"]) is not bool or type(options["fallback90"]) is not bool:
        raise ValueError("Explicit download/fallback choice required")
    if not isinstance(options["source"], str) or len(options["source"]) > 4096:
        raise ValueError("Invalid local COG path")
    coordinates = Coordinates(options["coordinates"])
    if coordinates.mode != "wgs84-utm": raise ValueError("DEM requires explicit WGS84/local origins")
    size = integer(options["cell_size_cm"], "cell size", 200, 102400)
    spacing = integer(options["spacing_cm"], "spacing", 200, size)
    if size % spacing or size // spacing + 1 > 513: raise ValueError("Spacing must divide cell; maximum 513 samples/side")
    for key in ("cell", "map_min_cm"):
        if not isinstance(options[key], list) or len(options[key]) != 2: raise ValueError("Invalid " + key)
        for value in options[key]: integer(value, key, 0 if key == "cell" else -100000000, 100000000)
    zero = number(options["vertical_zero_m"], "EGM2008 height at local zero", -10000, 10000)
    from pyproj.enums import TransformDirection
    side = size // spacing + 1
    # All sample positions are checked, not just an approximate geographic bbox.
    points = []
    for row in range(side):
        for col in range(side):
            local = [(options["map_min_cm"][i] + options["cell"][i] * size + (col if i == 0 else row) * spacing) / 100 for i in range(2)]
            dx, dy = [local[i] - coordinates.local[i] for i in range(2)]
            if math.hypot(dx, dy) > 20000: raise ValueError("DEM exceeds 20 km projection radius")
            lon, lat = coordinates.transformer.transform(coordinates.origin_xy[0]+dx, coordinates.origin_xy[1]+dy, direction=TransformDirection.INVERSE, errcheck=True)
            coordinates.point([lon, lat])  # same strip/hemisphere guard as vectors
            points.append((lon, lat))
    west, south = math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points))
    if not mosaic and (max(p[0] for p in points) >= west+1 or max(p[1] for p in points) >= south+1):
        raise ValueError("Cell crosses source tiles; multi-tile DEM mosaics require separate implementation")
    return coordinates, side, points, [west, south], zero


def tile_url(tile, resolution):
    lon, lat = tile
    name = f"Copernicus_DSM_COG_{'10' if resolution == 30 else '30'}_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM"
    return f"https://copernicus-dem-{resolution}m.s3.amazonaws.com/{name}/{name}.tif"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise ValueError("Unexpected DEM redirect; no redirected download")


def open_remote(url, method, headers=None):
    request = urllib.request.Request(url, method=method, headers={"Accept-Encoding":"identity", **(headers or {})})
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=15)


def headers(response, url):
    if response.status != 200 or response.geturl() != url or response.headers.get("Content-Encoding", "identity") != "identity":
        raise ValueError("Expected unchanged complete DEM HTTP 200")
    sizes = response.headers.get_all("Content-Length", [])
    if len(sizes) != 1 or not sizes[0].isascii() or not sizes[0].isdigit() or len(sizes[0]) > 10 or response.headers.get("Transfer-Encoding"):
        raise ValueError("DEM needs an unambiguous known size")
    size = int(sizes[0])
    etag = response.headers.get("ETag", "")
    if not 0 < size <= MAX_SOURCE or not 2 <= len(etag) <= 256 or not etag.startswith('"') or not etag.endswith('"') or any(ord(c) < 32 for c in etag):
        raise ValueError("DEM needs a strong ETag and 1..64 MiB source size")
    return {"url":url, "bytes":size, "etag":etag}


def identity(path):
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            count += len(chunk)
            if count > MAX_SOURCE: raise ValueError("DEM source exceeds 64 MiB")
            digest.update(chunk)
    if not count: raise ValueError("Empty DEM")
    return {"bytes":count, "sha256":digest.hexdigest()}


def plan(options, opener=open_remote):
    if "cell_count" in options: return mosaic_plan(options, opener)
    coordinates, side, points, tile, _ = grid(options)
    resolution, fallback = 30, False
    if options["source"]:
        source = Path(options["source"])
        if not source.is_absolute() or not source.is_file(): raise ValueError("Select a local Copernicus COG file")
        # A local file is an explicit user-declared 2021 GLO-30 COG, not authenticated provenance.
        source_info = dict(identity(source), path=str(source))
    else:
        if not options["allow_download"]: raise ValueError("Select a local COG or explicitly allow downloading")
        url = tile_url(tile, 30)
        try:
            with opener(url, "HEAD") as response: source_info = headers(response, url)
        except HTTPError as exc:
            if exc.code != 404 or not options["fallback90"]: raise ValueError(f"GLO-30 HTTP {exc.code}; no source selected") from exc
            resolution, fallback = 90, True
            url = tile_url(tile, 90)
            with opener(url, "HEAD") as response: source_info = headers(response, url)
    return dict(adapter="copernicus-dem-v1", release="2021", resolution_m=resolution, fallback90=fallback,
                license=LICENSE_URL, notice=NOTICE.format(resolution=resolution), vertical_crs="EPSG:3855 / EGM2008 metres",
                surface="DSM including buildings and vegetation; not bare-earth DTM", projection=coordinates.metadata,
                tile=tile, bbox=[round(v,9) for v in [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]],
                side=side, options=options, source=source_info, checked_at=int(time.time()))


def capture(review, partial, destination, progress, opener=open_remote):
    source = review["source"]
    expected = source["bytes"]
    digest, count = hashlib.sha256(), 0
    if "path" in source:
        stream = Path(source["path"]).open("rb")
    else:
        if source["url"] != tile_url(review["tile"], review["resolution_m"]): raise ValueError("Changed DEM URL")
        stream = opener(source["url"], "GET", {"If-Match": source["etag"]})
    with stream:
        if "url" in source and headers(stream, source["url"]) != source: raise ValueError("DEM changed after review")
        progress(0, expected)
        with partial.open("xb") as output:
            while chunk := stream.read(min(65536, expected+1-count)):
                count += len(chunk)
                if count > expected: raise ValueError("DEM exceeds reviewed bytes")
                output.write(chunk)
                digest.update(chunk)
                progress(count, expected)
            if count != expected or ("sha256" in source and digest.hexdigest() != source["sha256"]): raise ValueError("Truncated/changed DEM; review again")
            output.flush()
            os.fsync(output.fileno())
    os.link(partial, destination)  # exclusive; originals and completed captures survive errors
    return dict(source, captured_path=str(destination), sha256=digest.hexdigest(), bytes=count)


def raster_dependencies():
    try:
        import rasterio
        if rasterio.__version__ != "1.4.4": raise ImportError("version mismatch")
        import numpy as np
    except ImportError as exc:
        raise ValueError("DEM needs rasterio 1.4.4; install requirements-import.txt in selected Python") from exc
    return rasterio, np


def sample(path, review, progress):
    rasterio, np = raster_dependencies()
    _, side, points, tile, zero = grid(review["options"])
    from rasterio.windows import Window
    # Only local captured GTiff; no VRT/sidecars/network, no overview/downsampling inference.
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_PAM_ENABLED="NO", GDAL_CACHEMAX=16*1024*1024), rasterio.open(path, driver="GTiff") as dataset:
        t = dataset.transform
        resolution = review["resolution_m"]
        expected_height = 3600 if resolution == 30 else 1200
        if dataset.driver != "GTiff" or dataset.crs != rasterio.crs.CRS.from_epsg(4326) or dataset.count != 1 or dataset.dtypes != ("float32",) or dataset.height != expected_height or not 120 <= dataset.width <= expected_height or t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0 or dataset.scales != (1.0,) or dataset.offsets != (0.0,):
            raise ValueError("Expected unscaled north-up WGS84 float32 single-band 2021 COG")
        if abs(t.a*dataset.width-1) > 1e-8 or abs(-t.e*dataset.height-1) > 1e-8 or abs(t.c+t.a/2-tile[0]) > 1e-8 or abs(t.f+t.e/2-(tile[1]+1)) > 1e-8:
            raise ValueError("COG sample-centre/tile alignment mismatch")
        xy = np.asarray(points, dtype=np.float64)
        cols = (xy[:,0]-t.c)/t.a-0.5
        rows = (xy[:,1]-t.f)/t.e-0.5
        c0, r0 = np.floor(cols).astype(int), np.floor(rows).astype(int)
        if c0.min() < 0 or r0.min() < 0 or c0.max()+1 >= dataset.width or r0.max()+1 >= dataset.height:
            raise ValueError("Bilinear support crosses COG edge; no padding or silent neighbor substitution")
        left, top, width, height = int(c0.min()), int(r0.min()), int(c0.max()-c0.min()+2), int(r0.max()-r0.min()+2)
        if width*height > 1024*1024 or any(h*w > 2048*2048 for h,w in dataset.block_shapes): raise ValueError("DEM decode window/block budget exceeded")
        window = Window(left,top,width,height)
        data = dataset.read(1, window=window)
        mask = dataset.read_masks(1, window=window)
        cc, rr, dx, dy = c0-left, r0-top, cols-c0, rows-r0
        samples = [data[rr,cc], data[rr,cc+1], data[rr+1,cc], data[rr+1,cc+1]]
        if any(not np.isfinite(v).all() for v in samples) or any((m == 0).any() for m in [mask[rr,cc],mask[rr,cc+1],mask[rr+1,cc],mask[rr+1,cc+1]]): raise ValueError("Missing/non-finite DEM support; no ocean/land zero filling")
        values = sum(v.astype(np.float64)*weight for v,weight in zip(samples,[(1-dx)*(1-dy),dx*(1-dy),(1-dx)*dy,dx*dy]))
        if (values < -1000).any() or (values > 10000).any(): raise ValueError("DEM elevation outside supported physical range")
        heights = np.rint((values-zero)*100).astype(np.int64)
        low, high = int(heights.min()), int(heights.max())
        step = max(1, math.ceil((high-low)/65535))
        if abs(low) > 1000000 or step > 100 or high > 1000000: raise ValueError("Local height/PNG16 range exceeded; choose explicit vertical origin")
        encoded = np.rint((heights-low)/step).astype('>u2').reshape(side,side)
        raw = b"".join(b'\0'+row.tobytes() for row in encoded)
        def chunk(kind, content): return struct.pack('>I',len(content))+kind+content+struct.pack('>I',zlib.crc32(kind+content))
        png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',side,side,16,0,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
        progress(side*side, side*side)
        return png, dict(offset_cm=low, step_cm=step, source_accuracy_cm=None,
                         resampling="bilinear at full-resolution COG sample centres; local rows +northing", vertical_zero_m=zero,
                         quantization="nearest ties-to-even cm, then nearest PNG step", max_quantization_error_cm=0.5+step/2,
                         source_window=[left,top,width,height], source_pixel_degrees=[t.a,-t.e], rasterio=rasterio.__version__, gdal=rasterio.__gdal_version__)


def execute(request, scratch, progress, opener=open_remote):
    if request["mode"] == "dem-plan":
        progress("acquire",0,0)
        result = plan(request["options"], opener)
        progress("sample",0,0)
        return result
    review = request["plan"]
    if review.get("adapter") == "copernicus-dem-v2": return execute_mosaic(request, scratch, progress, opener)
    if not 0 <= time.time()-review["checked_at"] <= 600: raise ValueError("DEM review expired")
    # Recompute all derived contract fields. Remote HEAD is conditional only at capture.
    current = plan(review["options"], opener)
    if {k:v for k,v in current.items() if k != "checked_at"} != {k:v for k,v in review.items() if k != "checked_at"}:
        raise ValueError("DEM options/source changed; review again")
    current["checked_at"] = review["checked_at"]
    review = current  # JSON consumers may serialize integral values as floats.
    raster_dependencies()  # actionable failure before any download
    destination = Path(request["destination"])
    source = capture(review, scratch/"download.part", destination, lambda c,t:progress("acquire",c,t), opener)
    receipt = dict(review, source=source)
    with Path(str(destination)+".json").open("x") as stream: json.dump(receipt,stream,sort_keys=True)
    total = review["side"]**2
    progress("sample",0,total)
    png, metadata = sample(destination, review, lambda c,t:progress("sample",c,t))
    png_path = Path(str(destination)+".png")
    part = scratch/"dem.png.part"
    with part.open("xb") as stream:
        stream.write(png)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(part,png_path)
    return dict(review=receipt, raster=metadata, png_path=str(png_path), png_sha256=hashlib.sha256(png).hexdigest(), png_bytes=len(png))



MAX_MOSAIC_SAMPLES = 1025 * 1025
MAX_MOSAIC_SOURCES = 4


def mosaic_grid(options):
    base = dict(options)
    counts = base.pop("cell_count")
    if not isinstance(counts, list) or len(counts) != 2:
        raise ValueError("DEM cell_count must be [columns, rows]")
    nx, ny = [integer(v, "cell count", 1, 4) for v in counts]
    size = integer(base["cell_size_cm"], "cell size", 200, 102400)
    spacing = integer(base["spacing_cm"], "spacing", 200, size)
    sample_count = nx * ny * (size // spacing + 1) ** 2
    if sample_count > MAX_MOSAIC_SAMPLES: raise ValueError("DEM mosaic sample budget exceeded")
    cells, points = [], []
    for y in range(ny):
        for x in range(nx):
            cell_options = dict(base, cell=[base["cell"][0]+x, base["cell"][1]+y])
            coordinates, side, cell_points, _, zero = grid(cell_options, mosaic=True)
            cells.append(cell_options["cell"])
            points.append(cell_points)
    # Conservative support envelope for the smallest admitted COG width (120).
    # Every listed source is reviewed; decoding later verifies exact support.
    flat = [p for group in points for p in group]
    west, east = math.floor(min(p[0] for p in flat)), math.floor(max(p[0] for p in flat)+1/120)
    south, north = math.floor(min(p[1] for p in flat)-1/1200), math.floor(max(p[1] for p in flat))
    tiles = [[x,y] for y in range(south,north+1) for x in range(west,east+1)]
    if len(tiles) > MAX_MOSAIC_SOURCES: raise ValueError("DEM supports at most four source tiles including interpolation support")
    return coordinates, side, cells, points, tiles, zero


def mosaic_plan(options, opener=open_remote):
    coordinates, side, cells, groups, tiles, zero = mosaic_grid(options)
    sources = []
    for tile in tiles:
        resolution, fallback = 30, False
        if options["source"]:
            folder = Path(options["source"])
            if not folder.is_absolute() or not folder.is_dir(): raise ValueError("Mosaic local source must be a folder of named 2021 GLO-30 COGs")
            path = folder / tile_url(tile,30).split("/")[-1]
            source = dict(identity(path), path=str(path))
        else:
            if not options["allow_download"]: raise ValueError("Select a local COG folder or explicitly allow downloading")
            url = tile_url(tile,30)
            try:
                with opener(url,"HEAD") as response: source = headers(response,url)
            except HTTPError as exc:
                if exc.code != 404 or not options["fallback90"]: raise ValueError(f"GLO-30 HTTP {exc.code}; no source selected") from exc
                resolution, fallback = 90, True
                url = tile_url(tile,90)
                with opener(url,"HEAD") as response: source = headers(response,url)
        sources.append(dict(tile=tile,resolution_m=resolution,fallback90=fallback,source=source,notice=NOTICE.format(resolution=resolution)))
    if sum(s["source"]["bytes"] for s in sources) > MAX_SOURCE:
        raise ValueError("Combined DEM sources exceed 64 MiB")
    flat = [p for group in groups for p in group]
    return dict(adapter="copernicus-dem-v2",release="2021",license=LICENSE_URL,
                vertical_crs="EPSG:3855 / EGM2008 metres",surface="DSM including buildings and vegetation; not bare-earth DTM",
                projection=coordinates.metadata, bbox=[round(v,9) for v in [min(p[0] for p in flat),min(p[1] for p in flat),max(p[0] for p in flat),max(p[1] for p in flat)]],
                side=side,cells=cells,options=options,sources=sources,checked_at=int(time.time()))


def mosaic_heights(paths, review, progress):
    from contextlib import ExitStack
    from rasterio.windows import Window
    rasterio, np = raster_dependencies()
    _, side, cells, groups, tiles, zero = mosaic_grid(review["options"])
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_PAM_ENABLED="NO", GDAL_CACHEMAX=16*1024*1024))
        datasets = {}
        for path, item in zip(paths,review["sources"]):
            ds = stack.enter_context(rasterio.open(path,driver="GTiff"))
            t = ds.transform
            h = 3600 if item["resolution_m"] == 30 else 1200
            tile = item["tile"]
            if ds.driver != "GTiff" or ds.crs != rasterio.crs.CRS.from_epsg(4326) or ds.count != 1 or ds.dtypes != ("float32",) or ds.height != h or not 120 <= ds.width <= h or t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0 or ds.scales != (1.0,) or ds.offsets != (0.0,):
                raise ValueError("Expected unscaled north-up WGS84 float32 single-band 2021 COG")
            if abs(t.a*ds.width-1)>1e-8 or abs(-t.e*ds.height-1)>1e-8 or abs(t.c+t.a/2-tile[0])>1e-8 or abs(t.f+t.e/2-(tile[1]+1))>1e-8:
                raise ValueError("COG sample-centre/tile alignment mismatch")
            if any(h*w>2048*2048 for h,w in ds.block_shapes): raise ValueError("DEM decode block budget exceeded")
            datasets[tuple(tile)] = ds
        windows = []
        def nodes(tile, cols, rows, depth=0):
            if depth>4: raise ValueError("DEM interpolation support exceeds reviewed mosaic")
            ds=datasets.get(tile)
            if ds is None: raise ValueError("Missing DEM interpolation source")
            if (cols<0).any() or (rows<0).any(): raise ValueError("Invalid DEM interpolation index")
            out=np.empty(len(cols),dtype=np.float64)
            inside=(cols<ds.width)&(rows<ds.height)
            if inside.any():
                cc,rr=cols[inside],rows[inside]
                left,top=int(cc.min()),int(rr.min())
                w,h=int(cc.max()-left+1),int(rr.max()-top+1)
                if w*h>1024*1024: raise ValueError("DEM decode window budget exceeded")
                data=ds.read(1,window=Window(left,top,w,h));valid=ds.read_masks(1,window=Window(left,top,w,h))
                windows.append([*tile,left,top,w,h])
                values=data[rr-top,cc-left]
                if not np.isfinite(values).all() or (valid[rr-top,cc-left]==0).any(): raise ValueError("Missing/non-finite DEM support; no zero filling")
                out[inside]=values
            # Across an edge, interpolate on the neighbor's own lattice. A
            # mixed-resolution corner can in turn require its south/east source;
            # recursion moves only east/south and never pads or wraps a tile.
            for ex,sy in [(1,0),(0,1),(1,1)]:
                selected=(cols//ds.width==ex)&(rows//ds.height==sy)
                if not selected.any(): continue
                neighbor=(tile[0]+ex,tile[1]-sy)
                nd=datasets.get(neighbor)
                if nd is None: raise ValueError("Missing DEM interpolation source")
                lon=tile[0]+cols[selected]/ds.width
                lat=tile[1]+1-rows[selected]/ds.height
                out[selected]=interpolate(neighbor,(lon-neighbor[0])*nd.width,(neighbor[1]+1-lat)*nd.height,depth+1)
            return out
        def interpolate(tile, cols, rows, depth=0):
            # Snap only floating reconstruction noise around an integer lattice
            # index (1e-8 pixel); retain all geographic sample precision.
            cols=np.where(abs(cols-np.rint(cols))<1e-8,np.rint(cols),cols)
            rows=np.where(abs(rows-np.rint(rows))<1e-8,np.rint(rows),rows)
            c0,r0=np.floor(cols).astype(int),np.floor(rows).astype(int)
            dx,dy=cols-c0,rows-r0
            c1=c0+(dx>0);r1=r0+(dy>0)
            support=[nodes(tile,c0,r0,depth),nodes(tile,c1,r0,depth),nodes(tile,c0,r1,depth),nodes(tile,c1,r1,depth)]
            return sum(v*w for v,w in zip(support,[(1-dx)*(1-dy),dx*(1-dy),(1-dx)*dy,dx*dy]))
        flat = np.asarray([p for group in groups for p in group],dtype=np.float64)
        values = np.empty(len(flat),dtype=np.float64)
        for tile, ds in datasets.items():
            selected=np.flatnonzero((np.floor(flat[:,0])==tile[0])&(np.floor(flat[:,1])==tile[1]))
            if not len(selected): continue
            xy=flat[selected]
            values[selected]=interpolate(tile,(xy[:,0]-tile[0])*ds.width,(tile[1]+1-xy[:,1])*ds.height)
        if not np.isfinite(values).all() or (values < -1000).any() or (values > 10000).any(): raise ValueError("DEM elevation outside supported physical range")
        heights=np.rint((values-zero)*100).astype(np.int64).reshape(len(cells),side,side)
        low,high=int(heights.min()),int(heights.max())
        step=max(1,math.ceil((high-low)/65535))
        if abs(low)>1000000 or high>1000000 or step>100: raise ValueError("Local height/PNG16 range exceeded")
        progress(len(flat),len(flat))
        return heights,dict(offset_cm=low,step_cm=step,source_accuracy_cm=None,vertical_zero_m=zero,
            resampling="bilinear across full-resolution COG sample centres; local rows +northing",
            quantization="shared nearest ties-to-even cm, then nearest PNG step",max_quantization_error_cm=0.5+step/2,
            source_windows=windows,rasterio=rasterio.__version__,gdal=rasterio.__gdal_version__)


def execute_mosaic(request,scratch,progress,opener=open_remote):
    review=request["plan"]
    if not 0<=time.time()-review["checked_at"]<=600: raise ValueError("DEM review expired")
    current=mosaic_plan(review["options"],opener)
    if {k:v for k,v in current.items() if k!="checked_at"}!={k:v for k,v in review.items() if k!="checked_at"}: raise ValueError("DEM options/source changed; review again")
    current["checked_at"]=review["checked_at"]
    review=current
    raster_dependencies()
    destination=Path(request["destination"])
    paths=[];captured=[];done=0;total=sum(s["source"]["bytes"] for s in review["sources"])
    for index,item in enumerate(review["sources"]):
        path=Path(str(destination)+f".source-{index}.tif")
        part=scratch/"download.part"
        source=capture(item,part,path,lambda c,t:progress("acquire",done+c,total),opener)
        part.unlink() # only this owned partial, completed hard link remains
        captured.append(dict(item,source=source));paths.append(path);done+=source["bytes"]
        with Path(str(path)+".json").open("x") as stream: json.dump(dict(review=review,source=captured[-1]),stream,sort_keys=True)
    receipt=dict(review,sources=captured)
    total=len(review["cells"])*review["side"]**2
    progress("sample",0,total)
    heights,metadata=mosaic_heights(paths,review,lambda c,t:progress("sample",c,t))
    import numpy as np
    outputs=[]
    def chunk(kind,content): return struct.pack('>I',len(content))+kind+content+struct.pack('>I',zlib.crc32(kind+content))
    for index,cell in enumerate(review["cells"]):
        encoded=np.rint((heights[index]-metadata["offset_cm"])/metadata["step_cm"]).astype('>u2')
        raw=b"".join(b'\0'+row.tobytes() for row in encoded)
        side=review["side"]
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',side,side,16,0,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
        path=Path(str(destination)+f".cell-{index}.png")
        part=scratch/"dem.png.part"
        with part.open("xb") as stream:
            stream.write(png);stream.flush();os.fsync(stream.fileno())
        os.link(part,path);part.unlink()
        outputs.append(dict(cell=cell,png_path=str(path),png_sha256=hashlib.sha256(png).hexdigest(),png_bytes=len(png)))
    return dict(review=receipt,raster=metadata,outputs=outputs)

def main():
    from geojson import watch_parent_lifetime
    parser = argparse.ArgumentParser()
    parser.add_argument("request",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--layer-id",required=True)
    parser.add_argument("--watch-parent",action="store_true")
    args = parser.parse_args()
    if args.watch_parent: watch_parent_lifetime()
    if args.request.stat().st_size > 16384: raise ValueError("DEM request too large")
    request = strict_json(args.request.read_bytes())
    if request.get("mode") not in ("dem-plan","dem"): raise ValueError("Invalid DEM mode")
    sequence = 0
    def event(stage, completed, total, **extra):
        nonlocal sequence
        sequence += 1
        print(json.dumps(dict(request=args.layer_id,seq=sequence,stage=stage,completed=completed,total=total,unit="samples" if stage == "sample" else "bytes",**extra)),flush=True)
    result = execute(request,args.output.parent,event)
    encoded = json.dumps(result,sort_keys=True,allow_nan=False).encode()
    event("write",0,len(encoded))
    with args.output.open("xb") as stream: stream.write(encoded)
    event("write",len(encoded),len(encoded))
    event("complete",len(encoded),len(encoded),sha256=hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"error":str(exc)[:1024]}),file=sys.stderr)
        sys.exit(1)
